from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Analysis,
    Asset,
    Basket,
    CartItem,
    Consent,
    Feedback,
    Garment,
    GarmentObservation,
    IdempotencyRecord,
    Job,
    OutfitCandidate,
    OutfitCluster,
    Product,
    ProviderTask,
    TryOnRequest,
    UsageLedger,
    Workspace,
    utcnow,
)


def get_or_create_workspace(session: Session, owner_id: str) -> Workspace:
    workspace = session.scalar(
        select(Workspace).where(Workspace.owner_id == owner_id, Workspace.deleted_at.is_(None))
    )
    if workspace:
        return workspace
    workspace = Workspace(owner_id=owner_id, display_name="Closest Chemistry")
    session.add(workspace)
    session.commit()
    session.refresh(workspace)
    return workspace


def record_consent(session: Session, workspace: Workspace, kind: str, version: str, granted: bool, notes: str | None) -> Consent:
    settings = get_settings()
    consent = Consent(
        owner_id=workspace.owner_id,
        workspace_id=workspace.id,
        kind=kind,
        policy_version=version,
        granted=granted,
        notes=notes,
        retention_until=utcnow() + timedelta(days=settings.retention_days),
    )
    session.add(consent)
    session.commit()
    session.refresh(consent)
    return consent


def latest_consent(session: Session, workspace: Workspace, kind: str = "external_image_processing") -> Consent | None:
    return session.scalar(
        select(Consent)
        .where(Consent.workspace_id == workspace.id, Consent.kind == kind, Consent.granted.is_(True))
        .order_by(Consent.created_at.desc())
    )


def wipe_owner(session: Session, owner_id: str) -> None:
    """Delete every owned row with bulk SQL so ORM relationship nulling cannot 500."""
    session.execute(
        update(Garment)
        .where(Garment.owner_id == owner_id)
        .values(merged_into_id=None, crop_asset_id=None)
    )
    session.execute(
        update(Asset).where(Asset.owner_id == owner_id).values(parent_asset_id=None, consent_id=None)
    )
    session.execute(update(Analysis).where(Analysis.owner_id == owner_id).values(job_id=None))
    session.execute(
        update(TryOnRequest)
        .where(TryOnRequest.owner_id == owner_id)
        .values(job_id=None, result_asset_id=None)
    )
    session.execute(
        update(ProviderTask)
        .where(ProviderTask.owner_id == owner_id)
        .values(job_id=None, result_asset_id=None)
    )
    session.execute(update(CartItem).where(CartItem.owner_id == owner_id).values(garment_id=None))
    session.flush()
    for model in (
        UsageLedger,
        ProviderTask,
        Feedback,
        Basket,
        OutfitCandidate,
        OutfitCluster,
        TryOnRequest,
        Analysis,
        CartItem,
        Product,
        GarmentObservation,
        Garment,
        Asset,
        Consent,
        Job,
        IdempotencyRecord,
        Workspace,
    ):
        session.execute(delete(model).where(model.owner_id == owner_id))
    session.flush()
