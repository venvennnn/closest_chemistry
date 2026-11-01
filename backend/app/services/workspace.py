from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Consent, Workspace, utcnow


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
