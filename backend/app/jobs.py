from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select, text, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Job, utcnow


def enqueue_job(
    session: Session,
    *,
    owner_id: str,
    workspace_id: uuid.UUID,
    kind: str,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
) -> Job:
    if idempotency_key:
        existing = session.scalar(
            select(Job).where(
                Job.owner_id == owner_id,
                Job.kind == kind,
                Job.idempotency_key == idempotency_key,
            )
        )
        if existing:
            return existing
    settings = get_settings()
    job = Job(
        owner_id=owner_id,
        workspace_id=workspace_id,
        kind=kind,
        payload=payload,
        max_attempts=settings.job_max_attempts,
        idempotency_key=idempotency_key,
        status="queued",
        available_at=utcnow(),
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def recover_expired_leases(session: Session) -> int:
    now = utcnow()
    result = session.execute(
        update(Job)
        .where(Job.status == "leased", Job.lease_expires_at.is_not(None), Job.lease_expires_at < now)
        .values(
            status="queued",
            locked_by=None,
            lease_expires_at=None,
            available_at=now,
            error_safe="Lease expired; job returned to queue after worker crash or missed heartbeat.",
        )
    )
    session.commit()
    return result.rowcount or 0


def claim_job(session: Session, worker_id: str) -> Job | None:
    settings = get_settings()
    now = utcnow()
    lease = now + timedelta(seconds=settings.job_lease_seconds)
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        row = session.execute(
            text(
                """
                SELECT id FROM jobs
                WHERE status = 'queued' AND available_at <= :now
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            ),
            {"now": now},
        ).first()
        if not row:
            return None
        job = session.get(Job, row[0])
    else:
        job = session.scalar(
            select(Job)
            .where(Job.status == "queued", Job.available_at <= now)
            .order_by(Job.created_at)
            .with_for_update()
        )
        if not job:
            return None
    if job is None:
        return None
    job.status = "leased"
    job.locked_by = worker_id
    job.lease_expires_at = lease
    job.heartbeat_at = now
    job.attempts += 1
    session.commit()
    session.refresh(job)
    return job


def heartbeat(session: Session, job: Job, worker_id: str) -> None:
    settings = get_settings()
    if job.locked_by != worker_id:
        return
    job.heartbeat_at = utcnow()
    job.lease_expires_at = utcnow() + timedelta(seconds=settings.job_lease_seconds)
    session.commit()


def complete_job(session: Session, job: Job, result: dict[str, Any]) -> None:
    job.status = "succeeded"
    job.result = result
    job.locked_by = None
    job.lease_expires_at = None
    session.commit()


def fail_job(session: Session, job: Job, error: str) -> None:
    if job.attempts >= job.max_attempts:
        job.status = "failed"
        job.error_safe = error
        job.locked_by = None
        job.lease_expires_at = None
    else:
        job.status = "queued"
        job.error_safe = error
        job.locked_by = None
        job.lease_expires_at = None
        job.available_at = utcnow() + timedelta(seconds=min(30 * job.attempts, 300))
    session.commit()
