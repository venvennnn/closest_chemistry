from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal, current_principal
from app.config import get_settings
from app.database import get_db
from app.jobs import enqueue_job
from app.models import (
    Analysis,
    Asset,
    Basket,
    CartItem,
    Feedback,
    Garment,
    GarmentObservation,
    Job,
    OutfitCandidate,
    Product,
    TryOnRequest,
    UsageLedger,
    Workspace,
    utcnow,
)
from app.schemas import (
    AnalysisIn,
    CartPatch,
    ConsentIn,
    FeedbackIn,
    GarmentUpdate,
    MergeIn,
    ProductUrlIn,
    TryOnIn,
)
from app.services.images import ImageValidationError, normalise_image
from app.services.ingestion import ingest_product_url, parse_price_minor
from app.services.storage import StorageError, get_bytes, new_key, put_bytes
from app.services.workspace import get_or_create_workspace, latest_consent, record_consent

router = APIRouter(prefix="/v1", tags=["v1"])
log = logging.getLogger("closest_chemistry")


def _kick_job(session: Session, job: Job) -> None:
    """Process one queued job now so extract does not wait on a separate worker process."""
    try:
        from app.worker import run_once

        run_once(f"{job.kind}-kick-{str(job.id)[:8]}")
        session.refresh(job)
    except Exception:
        log.exception("%s kick failed; in-process worker will retry", job.kind)


def _workspace(session: Session, principal: Principal) -> Workspace:
    return get_or_create_workspace(session, principal.owner_id)


def _owned(row: Any, principal: Principal) -> Any:
    if row is None or row.owner_id != principal.owner_id:
        raise HTTPException(status_code=404, detail="Not found.")
    return row


def _idempotency(key: str | None) -> str | None:
    return key.strip() if key else None


def _price_minor(price_major: float, currency: str) -> int:
    try:
        return parse_price_minor(price_major, currency)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _require_consent(session: Session, workspace: Workspace) -> None:
    if latest_consent(session, workspace) is None:
        raise HTTPException(
            status_code=403,
            detail="External image processing consent is required before uploads or provider calls.",
        )


@router.get("/workspace")
def read_workspace(
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
) -> dict:
    workspace = _workspace(session, principal)
    consent = latest_consent(session, workspace)
    garments = session.scalars(
        select(Garment).where(
            Garment.workspace_id == workspace.id,
            Garment.merged_into_id.is_(None),
            Garment.source_kind == "wardrobe",
        )
    ).all()
    products = session.scalars(select(Product).where(Product.workspace_id == workspace.id)).all()
    cart = session.scalars(select(CartItem).where(CartItem.workspace_id == workspace.id)).all()
    analyses = session.scalars(
        select(Analysis).where(Analysis.workspace_id == workspace.id).order_by(Analysis.created_at.desc())
    ).all()
    tryon = session.scalar(select(Asset).where(Asset.workspace_id == workspace.id, Asset.kind == "tryon_source"))
    return {
        "workspace_id": str(workspace.id),
        "currency": workspace.currency,
        "consent": None
        if consent is None
        else {
            "id": str(consent.id),
            "kind": consent.kind,
            "policy_version": consent.policy_version,
            "granted_at": consent.granted_at.isoformat(),
            "retention_until": consent.retention_until.isoformat() if consent.retention_until else None,
        },
        "onboarding_required": not garments and not products,
        "counts": {
            "garments": len(garments),
            "confirmed": sum(1 for item in garments if item.status == "confirmed"),
            "products": len(products),
            "cart": len(cart),
            "analyses": len(analyses),
        },
        "has_tryon_photo": tryon is not None,
        "latest_analysis_id": str(analyses[0].id) if analyses else None,
        "latest_analysis_status": analyses[0].status if analyses else None,
    }


@router.post("/consents")
def create_consent(
    body: ConsentIn,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
) -> dict:
    if not body.granted:
        raise HTTPException(status_code=400, detail="Consent must be granted to process photographs externally.")
    workspace = _workspace(session, principal)
    consent = record_consent(session, workspace, body.kind, body.policy_version, True, body.notes)
    return {"id": str(consent.id), "retention_until": consent.retention_until.isoformat() if consent.retention_until else None}


@router.post("/assets", status_code=201)
async def upload_asset(
    kind: str = Form(...),
    file: UploadFile = File(...),
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
) -> dict:
    if kind not in {"outfit", "tryon_source", "product"}:
        raise HTTPException(status_code=400, detail="kind must be outfit, tryon_source, or product.")
    workspace = _workspace(session, principal)
    _require_consent(session, workspace)
    settings = get_settings()
    if kind == "outfit":
        existing = session.scalars(
            select(Asset).where(Asset.workspace_id == workspace.id, Asset.kind == "outfit", Asset.deleted_at.is_(None))
        ).all()
        if len(existing) >= settings.max_outfit_photos:
            raise HTTPException(status_code=400, detail=f"At most {settings.max_outfit_photos} outfit photographs.")
    data = await file.read()
    try:
        normalised, meta = normalise_image(data)
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        key = put_bytes(principal.owner_id, new_key(kind), normalised, meta["mime_type"])
    except StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    asset = Asset(
        owner_id=principal.owner_id,
        workspace_id=workspace.id,
        kind=kind,
        storage_key=key,
        content_sha256=meta["content_sha256"],
        mime_type=meta["mime_type"],
        byte_size=meta["byte_size"],
        width=meta["width"],
        height=meta["height"],
        original_filename=file.filename or "",
        provenance={"source": "user_upload", "exif_stripped": True},
        rights_status="user_uploaded",
        consent_id=latest_consent(session, workspace).id if latest_consent(session, workspace) else None,
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return {"id": str(asset.id), **meta, "kind": kind}


@router.get("/assets")
def list_assets(
    kind: str | None = None,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
) -> dict:
    workspace = _workspace(session, principal)
    stmt = select(Asset).where(Asset.workspace_id == workspace.id, Asset.deleted_at.is_(None))
    if kind:
        stmt = stmt.where(Asset.kind == kind)
    rows = session.scalars(stmt.order_by(Asset.created_at.desc())).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "kind": row.kind,
                "original_filename": row.original_filename,
                "mime_type": row.mime_type,
                "width": row.width,
                "height": row.height,
            }
            for row in rows
        ]
    }


@router.get("/assets/{asset_id}/content")
def asset_content(
    asset_id: UUID,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
):
    from fastapi.responses import Response

    asset = _owned(session.get(Asset, asset_id), principal)
    data = get_bytes(asset.storage_key)
    return Response(content=data, media_type=asset.mime_type)


@router.post("/assets/{asset_id}/extract", status_code=202)
def extract_asset(
    asset_id: UUID,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    workspace = _workspace(session, principal)
    _require_consent(session, workspace)
    asset = _owned(session.get(Asset, asset_id), principal)
    missing = get_settings().missing_gemini()
    if missing:
        raise HTTPException(status_code=503, detail=missing)
    job = enqueue_job(
        session,
        owner_id=principal.owner_id,
        workspace_id=workspace.id,
        kind="extract",
        payload={"asset_id": str(asset.id)},
        idempotency_key=_idempotency(idempotency_key),
    )
    _kick_job(session, job)
    return {"job_id": str(job.id), "status": job.status}


@router.get("/jobs/{job_id}")
def read_job(
    job_id: UUID,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
) -> dict:
    job = _owned(session.get(Job, job_id), principal)
    return {
        "id": str(job.id),
        "kind": job.kind,
        "status": job.status,
        "attempts": job.attempts,
        "error_safe": job.error_safe,
        "result": job.result,
    }


@router.get("/garments")
def list_garments(
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
) -> dict:
    workspace = _workspace(session, principal)
    rows = session.scalars(
        select(Garment).where(Garment.workspace_id == workspace.id, Garment.merged_into_id.is_(None))
    ).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "display_name": row.display_name,
                "category": row.category,
                "subtype": row.subtype,
                "colour": row.colour,
                "colour_family": row.colour_family,
                "pattern": row.pattern,
                "pattern_family": row.pattern_family,
                "formality_min": row.formality_min,
                "formality_max": row.formality_max,
                "status": row.status,
                "needs_review": row.needs_review,
                "analysis_eligible": row.analysis_eligible,
                "youcam_eligible": row.youcam_eligible,
                "source_kind": row.source_kind,
                "crop_asset_id": str(row.crop_asset_id) if row.crop_asset_id else None,
            }
            for row in rows
        ]
    }


@router.patch("/garments/{garment_id}")
def update_garment(
    garment_id: UUID,
    body: GarmentUpdate,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
) -> dict:
    garment = _owned(session.get(Garment, garment_id), principal)
    for field in (
        "display_name",
        "category",
        "subtype",
        "colour",
        "colour_family",
        "pattern",
        "pattern_family",
        "formality_min",
        "formality_max",
        "notes",
    ):
        value = getattr(body, field)
        if value is not None:
            setattr(garment, field, value)
    if body.exclude:
        garment.status = "excluded"
        garment.analysis_eligible = False
    if body.confirm:
        missing = [
            name
            for name, value in {
                "category": garment.category,
                "colour_family": garment.colour_family,
                "pattern_family": garment.pattern_family,
                "formality_min": garment.formality_min,
                "formality_max": garment.formality_max,
            }.items()
            if value in (None, "")
        ]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot confirm until these fields are set: {', '.join(missing)}.",
            )
        garment.status = "confirmed"
        garment.needs_review = False
        garment.analysis_eligible = True
        garment.youcam_eligible = garment.category in {"top", "dress", "outerwear"}
    garment.version += 1
    garment.updated_at = utcnow()
    session.commit()
    return {"id": str(garment.id), "status": garment.status, "analysis_eligible": garment.analysis_eligible}


@router.post("/garments/merge")
def merge_garments(
    body: MergeIn,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
) -> dict:
    if not body.confirmed:
        raise HTTPException(status_code=400, detail="Merges require explicit user confirmation. Colour similarity never auto-merges.")
    target = _owned(session.get(Garment, body.target_id), principal)
    for source_id in body.source_ids:
        source = _owned(session.get(Garment, source_id), principal)
        if source.id == target.id:
            continue
        source.merged_into_id = target.id
        source.status = "merged"
        source.analysis_eligible = False
        for observation in session.scalars(select(GarmentObservation).where(GarmentObservation.garment_id == source.id)):
            observation.garment_id = target.id
    session.commit()
    return {"target_id": str(target.id), "merged": [str(item) for item in body.source_ids]}


@router.post("/products/url")
async def ingest_url(
    body: ProductUrlIn,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
) -> dict:
    workspace = _workspace(session, principal)
    fetched = await ingest_product_url(body.url)
    if not fetched.get("ok"):
        if body.price_major is None or not body.title:
            return fetched
        fetched = {
            **fetched,
            "ok": True,
            "title": body.title,
            "price_minor": parse_price_minor(body.price_major, body.currency or workspace.currency),
            "currency": (body.currency or workspace.currency).upper(),
            "metadata_origin": "user_entered_after_fetch_failure",
            "entered_at": utcnow().isoformat(),
        }
    return fetched


@router.post("/products", status_code=201)
async def create_product(
    title: str = Form(...),
    price_major: float = Form(...),
    currency: str = Form(...),
    category: str = Form(...),
    file: UploadFile = File(...),
    subtype: str | None = Form(default=None),
    colour: str | None = Form(default=None),
    colour_family: str | None = Form(default=None),
    pattern: str | None = Form(default=None),
    pattern_family: str | None = Form(default=None),
    formality_min: int | None = Form(default=None),
    formality_max: int | None = Form(default=None),
    source_url: str | None = Form(default=None),
    shipping_tax_included: bool = Form(default=False),
    metadata_origin: str = Form(default="user_entered"),
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
) -> dict:
    workspace = _workspace(session, principal)
    _require_consent(session, workspace)
    existing = session.scalars(select(Product).where(Product.workspace_id == workspace.id)).all()
    settings = get_settings()
    if len(existing) >= settings.max_candidates:
        raise HTTPException(status_code=400, detail=f"At most {settings.max_candidates} candidate products.")
    data = await file.read()
    try:
        normalised, meta = normalise_image(data)
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        key = put_bytes(principal.owner_id, new_key("product"), normalised, meta["mime_type"])
    except StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    asset = Asset(
        owner_id=principal.owner_id,
        workspace_id=workspace.id,
        kind="product",
        storage_key=key,
        content_sha256=meta["content_sha256"],
        mime_type=meta["mime_type"],
        byte_size=meta["byte_size"],
        width=meta["width"],
        height=meta["height"],
        original_filename=file.filename or "",
        provenance={"source": "user_upload", "role": "product"},
        rights_status="user_uploaded",
    )
    session.add(asset)
    session.flush()
    product = Product(
        owner_id=principal.owner_id,
        workspace_id=workspace.id,
        title=title,
        source_url=source_url,
        source_kind="manual",
        image_asset_id=asset.id,
        price_minor=_price_minor(price_major, currency),
        currency=currency.upper(),
        category=category,
        subtype=subtype,
        colour=colour,
        colour_family=colour_family,
        pattern=pattern,
        pattern_family=pattern_family,
        formality_min=formality_min,
        formality_max=formality_max,
        metadata_origin=metadata_origin,
        entered_at=utcnow(),
        shipping_tax_included=shipping_tax_included,
        youcam_eligible=category in {"top", "dress", "outerwear"},
    )
    session.add(product)
    session.flush()
    session.add(
        CartItem(
            owner_id=principal.owner_id,
            workspace_id=workspace.id,
            product_id=product.id,
        )
    )
    session.commit()
    session.refresh(product)
    return {"id": str(product.id), "price_minor": product.price_minor, "currency": product.currency}


@router.get("/products")
def list_products(
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
) -> dict:
    workspace = _workspace(session, principal)
    products = session.scalars(select(Product).where(Product.workspace_id == workspace.id)).all()
    cart_rows = {row.product_id: row for row in session.scalars(select(CartItem).where(CartItem.workspace_id == workspace.id))}
    return {
        "items": [
            {
                "id": str(product.id),
                "title": product.title,
                "price_minor": product.price_minor,
                "currency": product.currency,
                "category": product.category,
                "subtype": product.subtype,
                "colour": product.colour,
                "image_asset_id": str(product.image_asset_id),
                "metadata_origin": product.metadata_origin,
                "shipping_tax_included": product.shipping_tax_included,
                "pinned": cart_rows[product.id].pinned if product.id in cart_rows else False,
                "excluded": cart_rows[product.id].excluded if product.id in cart_rows else False,
                "cart_item_id": str(cart_rows[product.id].id) if product.id in cart_rows else None,
            }
            for product in products
        ]
    }


@router.patch("/cart/{cart_item_id}")
def patch_cart(
    cart_item_id: UUID,
    body: CartPatch,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
) -> dict:
    item = _owned(session.get(CartItem, cart_item_id), principal)
    if body.pinned is not None:
        item.pinned = body.pinned
        if body.pinned:
            item.excluded = False
    if body.excluded is not None:
        item.excluded = body.excluded
        if body.excluded:
            item.pinned = False
    session.commit()
    return {"id": str(item.id), "pinned": item.pinned, "excluded": item.excluded}


@router.post("/analyses", status_code=202)
def create_analysis(
    body: AnalysisIn,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    workspace = _workspace(session, principal)
    confirmed = session.scalars(
        select(Garment).where(
            Garment.workspace_id == workspace.id,
            Garment.status == "confirmed",
            Garment.source_kind == "wardrobe",
        )
    ).all()
    cart = session.scalars(
        select(CartItem).where(CartItem.workspace_id == workspace.id, CartItem.excluded.is_(False))
    ).all()
    settings = get_settings()
    if len(cart) < settings.min_candidates or len(cart) > settings.max_candidates:
        raise HTTPException(
            status_code=400,
            detail=f"Add between {settings.min_candidates} and {settings.max_candidates} non-excluded cart candidates.",
        )
    if not confirmed:
        raise HTTPException(status_code=400, detail="Confirm at least one wardrobe garment before analysis.")
    currencies = set()
    for item in cart:
        product = session.get(Product, item.product_id)
        if product:
            currencies.add(product.currency)
    if len(currencies) != 1 or body.currency.upper() not in currencies:
        raise HTTPException(status_code=400, detail="Use one currency per optimisation.")
    analysis = Analysis(
        owner_id=principal.owner_id,
        workspace_id=workspace.id,
        occasion=body.occasion,
        budget_minor=body.budget_minor,
        currency=body.currency.upper(),
        footwear_required=body.footwear_required,
        max_items=body.max_items,
        parameters=body.model_dump(),
        status="queued",
    )
    session.add(analysis)
    session.flush()
    job = enqueue_job(
        session,
        owner_id=principal.owner_id,
        workspace_id=workspace.id,
        kind="analyse",
        payload={"analysis_id": str(analysis.id)},
        idempotency_key=_idempotency(idempotency_key),
    )
    analysis.job_id = job.id
    session.commit()
    _kick_job(session, job)
    return {"analysis_id": str(analysis.id), "job_id": str(job.id), "status": job.status}


@router.get("/analyses/{analysis_id}")
def read_analysis(
    analysis_id: UUID,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
) -> dict:
    analysis = _owned(session.get(Analysis, analysis_id), principal)
    return {
        "id": str(analysis.id),
        "status": analysis.status,
        "occasion": analysis.occasion,
        "budget_minor": analysis.budget_minor,
        "currency": analysis.currency,
        "footwear_required": analysis.footwear_required,
        "input_snapshot_hash": analysis.input_snapshot_hash,
        "algorithm_version": analysis.algorithm_version,
        "rule_version": analysis.rule_version,
        "error_safe": analysis.error_safe,
        "result": analysis.result,
    }


@router.get("/analyses/{analysis_id}/outfits/{combination_id}")
def read_outfit(
    analysis_id: UUID,
    combination_id: str,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
) -> dict:
    analysis = _owned(session.get(Analysis, analysis_id), principal)
    outfit = session.scalar(
        select(OutfitCandidate).where(
            OutfitCandidate.analysis_id == analysis.id,
            OutfitCandidate.combination_id == combination_id,
        )
    )
    if not outfit:
        raise HTTPException(status_code=404, detail="Outfit not found in this analysis.")
    return {
        "combination_id": outfit.combination_id,
        "garment_ids": outfit.garment_ids,
        "template": outfit.template,
        "cluster_id": outfit.cluster_id,
        "qualified": outfit.qualified,
        "needs_review": outfit.needs_review,
        "youcam_eligible": outfit.youcam_eligible,
        "rule_contributions": outfit.rule_contributions,
        "rejection_reasons": outfit.rejection_reasons,
    }


@router.post("/feedback")
def create_feedback(
    body: FeedbackIn,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
) -> dict:
    analysis = _owned(session.get(Analysis, body.analysis_id), principal)
    if body.verdict not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="verdict must be approve or reject.")
    row = Feedback(
        owner_id=principal.owner_id,
        workspace_id=analysis.workspace_id,
        analysis_id=analysis.id,
        target_kind=body.target_kind,
        target_id=body.target_id,
        verdict=body.verdict,
        note=body.note,
    )
    session.add(row)
    session.flush()
    job = enqueue_job(
        session,
        owner_id=principal.owner_id,
        workspace_id=analysis.workspace_id,
        kind="analyse",
        payload={"analysis_id": str(analysis.id), "reason": "feedback_recompute"},
    )
    session.commit()
    return {"id": str(row.id), "recompute_job_id": str(job.id)}


@router.get("/feedback/summary")
def feedback_summary(
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
) -> dict:
    workspace = _workspace(session, principal)
    rows = session.scalars(select(Feedback).where(Feedback.workspace_id == workspace.id)).all()
    approved = sum(1 for row in rows if row.verdict == "approve")
    rejected = sum(1 for row in rows if row.verdict == "reject")
    return {
        "approved": approved,
        "rejected": rejected,
        "denominator": len(rows),
        "note": "Rates use actual collected denominators only.",
    }


@router.post("/tryon", status_code=202)
def submit_tryon(
    body: TryOnIn,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    workspace = _workspace(session, principal)
    _require_consent(session, workspace)
    missing = get_settings().missing_youcam()
    if missing:
        raise HTTPException(status_code=503, detail=missing)
    source = session.scalar(select(Asset).where(Asset.workspace_id == workspace.id, Asset.kind == "tryon_source"))
    if source is None:
        raise HTTPException(status_code=400, detail="Upload a separate suitable try-on photograph first.")
    request = TryOnRequest(
        owner_id=principal.owner_id,
        workspace_id=workspace.id,
        source_asset_id=source.id,
        combination_id=body.combination_id,
        garment_ids=[str(item) for item in body.garment_ids],
        live=True,
        status="queued",
    )
    session.add(request)
    session.flush()
    job = enqueue_job(
        session,
        owner_id=principal.owner_id,
        workspace_id=workspace.id,
        kind="tryon",
        payload={"tryon_id": str(request.id), "force_live": body.force_live},
        idempotency_key=_idempotency(idempotency_key),
    )
    request.job_id = job.id
    session.commit()
    return {"tryon_id": str(request.id), "job_id": str(job.id), "status": "queued", "live": True}


@router.get("/tryon/{tryon_id}")
def read_tryon(
    tryon_id: UUID,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
) -> dict:
    row = _owned(session.get(TryOnRequest, tryon_id), principal)
    return {
        "id": str(row.id),
        "status": row.status,
        "live": row.live,
        "cache_hit": row.cache_hit,
        "result_asset_id": str(row.result_asset_id) if row.result_asset_id else None,
        "step_assets": row.step_assets,
        "limitation": row.limitation,
        "error_safe": row.error_safe,
        "label": "cached" if row.cache_hit else "live",
    }


@router.delete("/workspace")
def delete_workspace(
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_db),
) -> dict:
    from app.services.storage import delete_prefix

    workspace = _workspace(session, principal)
    owner = principal.owner_id
    for model in (
        TryOnRequest,
        UsageLedger,
        Feedback,
        Basket,
        OutfitCandidate,
        Analysis,
        CartItem,
        Product,
        GarmentObservation,
        Garment,
        Asset,
        Job,
        Workspace,
    ):
        for row in session.scalars(select(model).where(model.owner_id == owner)).all():
            session.delete(row)
    delete_prefix(owner)
    session.commit()
    return {
        "deleted": True,
        "limitations": (
            "Owned application rows and private-storage objects were deleted. "
            "Supabase backups, provider-side logs, and YouCam retention are outside this control plane "
            "and follow those vendors' policies."
        ),
    }
