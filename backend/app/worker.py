from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import timedelta

from sqlalchemy import select

from app.config import get_settings
from app.database import get_session_factory
from app.jobs import claim_job, complete_job, fail_job, heartbeat, recover_expired_leases
from app.models import (
    Analysis,
    Asset,
    Garment,
    GarmentObservation,
    ProviderTask,
    TryOnRequest,
    UsageLedger,
    utcnow,
)
from app.services.analysis import run_analysis
from app.services.gemini import GeminiError, extract_garments
from app.services.images import crop_box, sha256_hex
from app.services.storage import get_bytes, new_key, put_bytes
from app.services.youcam import YouCamAdapter, YouCamError, request_digest
from app.services.workspace import latest_consent

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("closest-chemistry-worker")


def _reserve_units(session, owner_id, workspace_id, provider: str, units: int, task) -> None:
    settings = get_settings()
    since = utcnow() - timedelta(hours=24)
    spent = sum(
        row.units
        for row in session.scalars(
            select(UsageLedger).where(
                UsageLedger.owner_id == owner_id,
                UsageLedger.provider == provider,
                UsageLedger.created_at >= since,
                UsageLedger.kind.in_(["reserve", "settle"]),
            )
        )
        if row.kind == "reserve"
    )
    if spent + units > settings.daily_spend_cap_units:
        raise RuntimeError(
            f"Daily {provider} spend cap ({settings.daily_spend_cap_units} units) would be exceeded. "
            "HTTP calls are not the same as billable units; this reserve is an estimate."
        )
    session.add(
        UsageLedger(
            owner_id=owner_id,
            workspace_id=workspace_id,
            provider=provider,
            units=units,
            kind="reserve",
            provider_task_id=task.id if task else None,
            note="Atomic reserve before provider submission",
            estimated=True,
        )
    )
    session.commit()


def process_extract(session, job) -> dict:
    asset = session.get(Asset, uuid.UUID(job.payload["asset_id"]))
    if asset is None or asset.owner_id != job.owner_id:
        raise RuntimeError("Asset missing or not owned.")
    data = get_bytes(asset.storage_key)
    payload = extract_garments(data, asset.mime_type)
    created = []
    for item in payload["garments"]:
        crop = crop_box(data, item["bbox"], asset.mime_type)
        crop_key = put_bytes(job.owner_id, new_key("crop"), crop, "image/jpeg")
        crop_asset = Asset(
            owner_id=job.owner_id,
            workspace_id=job.workspace_id,
            kind="crop",
            storage_key=crop_key,
            content_sha256=sha256_hex(crop),
            mime_type="image/jpeg",
            byte_size=len(crop),
            width=0,
            height=0,
            provenance={"parent_asset_id": str(asset.id), "bbox": item["bbox"]},
            rights_status=asset.rights_status,
            parent_asset_id=asset.id,
        )
        session.add(crop_asset)
        session.flush()
        garment = Garment(
            owner_id=job.owner_id,
            workspace_id=job.workspace_id,
            canonical_key=str(uuid.uuid4()),
            display_name=item.get("subtype") or item.get("category") or "garment",
            category=item.get("category") if item.get("category") in {"top", "bottom", "dress", "outerwear", "footwear"} else "top",
            subtype=item.get("subtype"),
            colour=item.get("colour"),
            colour_family=item.get("colour_family"),
            pattern=item.get("pattern"),
            pattern_family=item.get("pattern_family"),
            formality_min=item.get("formality_min"),
            formality_max=item.get("formality_max"),
            status="draft",
            needs_review=True,
            analysis_eligible=False,
            crop_asset_id=crop_asset.id,
            source_kind="wardrobe",
            notes=item.get("visible_evidence"),
        )
        if item.get("incomplete") or item.get("occlusion") not in {None, "none", "minimal"}:
            garment.needs_review = True
            garment.notes = (garment.notes or "") + " Incomplete or occluded; confirm or exclude before counting."
        session.add(garment)
        session.flush()
        session.add(
            GarmentObservation(
                owner_id=job.owner_id,
                workspace_id=job.workspace_id,
                garment_id=garment.id,
                asset_id=asset.id,
                bbox=item["bbox"],
                occlusion=item.get("occlusion") or "none",
                visible_evidence=item.get("visible_evidence") or "",
                model_confidence=item.get("model_confidence"),
                provider=payload["provider"],
                model_id=payload["model_id"],
                prompt_version=payload["prompt_version"],
                raw_payload=item,
            )
        )
        created.append(str(garment.id))
    session.commit()
    return {"garment_ids": created, "model_id": payload["model_id"], "prompt_version": payload["prompt_version"]}


def process_analyse(session, job) -> dict:
    analysis = session.get(Analysis, uuid.UUID(job.payload["analysis_id"]))
    if analysis is None or analysis.owner_id != job.owner_id:
        raise RuntimeError("Analysis missing or not owned.")
    return run_analysis(session, analysis)


def process_tryon(session, job) -> dict:
    settings = get_settings()
    request = session.get(TryOnRequest, uuid.UUID(job.payload["tryon_id"]))
    if request is None or request.owner_id != job.owner_id:
        raise RuntimeError("Try-on request missing or not owned.")
    from app.models import Workspace

    workspace = session.get(Workspace, request.workspace_id)
    if workspace and latest_consent(session, workspace) is None:
        raise RuntimeError("Consent missing for YouCam submission.")

    garments = [session.get(Garment, uuid.UUID(gid)) for gid in request.garment_ids]
    garments = [item for item in garments if item and item.owner_id == job.owner_id]
    if not garments:
        raise RuntimeError("No owned garments supplied for try-on.")

    adapter = YouCamAdapter()
    category_map = {"top": "upper_body", "bottom": "lower_body", "dress": "full_body", "outerwear": "outer", "footwear": "shoes"}
    supported = []
    skipped = []
    for garment in garments:
        mapped = category_map.get(garment.category)
        if mapped in settings.youcam_category_list and garment.youcam_eligible and garment.crop_asset_id:
            supported.append((garment, mapped))
        else:
            skipped.append(garment.category)

    if not supported:
        request.status = "failed"
        request.limitation = (
            "This combination cannot be rendered faithfully with currently live-verified YouCam categories. "
            f"Skipped: {', '.join(skipped) or 'none'}. Enable only verified paths in YOU_CAM_ENABLED_CATEGORIES."
        )
        session.commit()
        return {"limitation": request.limitation}

    if len(supported) < len(garments):
        request.limitation = (
            "Only supported single-item or verified-category steps were submitted. "
            "Unsupported garments were not substituted with unrelated items. "
            f"Skipped categories: {', '.join(sorted(set(skipped)))}."
        )

    source_asset = session.get(Asset, request.source_asset_id)
    source_bytes = get_bytes(source_asset.storage_key)
    current_source = source_bytes
    steps = []
    parent_hash = None
    for garment, category in supported:
        ref_asset = session.get(Asset, garment.crop_asset_id)
        ref_bytes = get_bytes(ref_asset.storage_key)
        digest = request_digest(
            owner=job.owner_id,
            src=sha256_hex(current_source),
            ref=ref_asset.content_sha256,
            engine=settings.youcam_engine_version,
            category=category,
            parent=parent_hash or "",
        )
        cached = session.scalar(
            select(ProviderTask).where(
                ProviderTask.owner_id == job.owner_id,
                ProviderTask.request_digest == digest,
                ProviderTask.status == "succeeded",
                ProviderTask.result_asset_id.is_not(None),
            )
        )
        task_row = ProviderTask(
            owner_id=job.owner_id,
            workspace_id=job.workspace_id,
            job_id=job.id,
            provider="youcam",
            operation="cloth-v4",
            request_digest=digest,
            units_reserved=settings.youcam_unit_cost,
            parameters={"category": category, "garment_id": str(garment.id)},
        )
        session.add(task_row)
        session.flush()
        if cached and not job.payload.get("force_live"):
            task_row.status = "succeeded"
            task_row.cache_hit = True
            task_row.result_asset_id = cached.result_asset_id
            task_row.provider_task_id = cached.provider_task_id
            task_row.unit_status = "cache_hit"
            session.commit()
            steps.append({"garment_id": str(garment.id), "cache_hit": True, "result_asset_id": str(cached.result_asset_id)})
            current_source = get_bytes(session.get(Asset, cached.result_asset_id).storage_key)
            parent_hash = sha256_hex(current_source)
            continue

        _reserve_units(session, job.owner_id, job.workspace_id, "youcam", settings.youcam_unit_cost, task_row)
        started = time.time()
        try:
            result = adapter.run_single(job.owner_id, current_source, ref_bytes, category)
        except YouCamError as exc:
            task_row.status = "failed"
            task_row.error_safe = str(exc)
            task_row.unit_status = "needs_reconcile" if exc.reconcile else "released"
            request.status = "failed"
            request.error_safe = str(exc)
            session.commit()
            raise
        latency = int((time.time() - started) * 1000)
        result_asset = Asset(
            owner_id=job.owner_id,
            workspace_id=job.workspace_id,
            kind="tryon_result",
            storage_key=result["storage_key"],
            content_sha256=sha256_hex(result["bytes"]),
            mime_type="image/jpeg",
            byte_size=len(result["bytes"]),
            width=0,
            height=0,
            provenance={
                "provider": "youcam",
                "engine": settings.youcam_engine_version,
                "task_id_redacted": (result["provider_task_id"] or "")[:8],
            },
            rights_status="derived",
        )
        session.add(result_asset)
        session.flush()
        task_row.provider_task_id = result["provider_task_id"]
        task_row.status = "succeeded"
        task_row.latency_ms = latency
        task_row.result_asset_id = result_asset.id
        task_row.unit_status = "estimated"
        task_row.units_observed = result.get("units_estimated")
        session.add(
            UsageLedger(
                owner_id=job.owner_id,
                workspace_id=job.workspace_id,
                provider="youcam",
                units=settings.youcam_unit_cost,
                kind="settle",
                provider_task_id=task_row.id,
                note="Estimated from documented unit table; observed provider invoice not available.",
                estimated=True,
            )
        )
        steps.append(
            {
                "garment_id": str(garment.id),
                "cache_hit": False,
                "live": True,
                "result_asset_id": str(result_asset.id),
                "latency_ms": latency,
                "task_id_redacted": (result["provider_task_id"] or "")[:8],
            }
        )
        current_source = result["bytes"]
        parent_hash = sha256_hex(current_source)
        request.result_asset_id = result_asset.id
        session.commit()

    request.status = "succeeded"
    request.step_assets = steps
    request.cache_hit = all(step.get("cache_hit") for step in steps) if steps else False
    request.live = not request.cache_hit
    session.commit()
    return {"tryon_id": str(request.id), "steps": steps, "live": request.live, "cache_hit": request.cache_hit}


HANDLERS = {
    "extract": process_extract,
    "analyse": process_analyse,
    "tryon": process_tryon,
}

WORKER_STATE = {"alive": False, "worker_id": None}


def run_once(worker_id: str) -> bool:
    session = get_session_factory()()
    try:
        recover_expired_leases(session)
        job = claim_job(session, worker_id)
        if not job:
            return False
        log.info("claimed job", extra={"job_id": str(job.id), "kind": job.kind, "attempt": job.attempts})
        handler = HANDLERS.get(job.kind)
        if handler is None:
            fail_job(session, job, f"Unknown job kind {job.kind}.")
            return True
        try:
            heartbeat(session, job, worker_id)
            result = handler(session, job)
            complete_job(session, job, result)
        except (GeminiError, YouCamError, RuntimeError, ValueError) as exc:
            fail_job(session, job, str(exc))
            log.warning("job failed", extra={"job_id": str(job.id), "error": str(exc)})
        except Exception:
            fail_job(session, job, "Internal worker error. Photo and token contents were not logged.")
            log.exception("job crashed", extra={"job_id": str(job.id)})
        return True
    finally:
        session.close()


def run_loop() -> None:
    settings = get_settings()
    settings.require_database()
    worker_id = f"worker-{uuid.uuid4().hex[:10]}"
    WORKER_STATE["alive"] = True
    WORKER_STATE["worker_id"] = worker_id
    log.info("worker starting", extra={"worker_id": worker_id})
    while True:
        try:
            worked = run_once(worker_id)
            if not worked:
                time.sleep(1)
        except Exception:
            log.exception("worker loop error", extra={"worker_id": worker_id})
            time.sleep(2)


def main() -> None:
    run_loop()


if __name__ == "__main__":
    main()
