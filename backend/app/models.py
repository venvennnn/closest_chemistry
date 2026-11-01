from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GUID(TypeDecorator):
    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class JSONType(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class TimestampedOwner:
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class Workspace(Base, TimestampedOwner):
    __tablename__ = "workspaces"

    display_name: Mapped[str] = mapped_column(String(200), default="Closest Chemistry")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    footwear_required_default: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Consent(Base, TimestampedOwner):
    __tablename__ = "consents"

    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspaces.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, default=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Asset(Base, TimestampedOwner):
    __tablename__ = "assets"

    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspaces.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), default="")
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    rights_status: Mapped[str] = mapped_column(String(32), default="user_uploaded")
    consent_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("consents.id"), nullable=True)
    parent_asset_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("assets.id"), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Garment(Base, TimestampedOwner):
    __tablename__ = "garments"

    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspaces.id"), nullable=False)
    canonical_key: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    subtype: Mapped[str | None] = mapped_column(String(64), nullable=True)
    colour: Mapped[str | None] = mapped_column(String(64), nullable=True)
    colour_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pattern: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pattern_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    formality_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    formality_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    needs_review: Mapped[bool] = mapped_column(Boolean, default=True)
    analysis_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    youcam_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("garments.id"), nullable=True)
    crop_asset_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("assets.id"), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(16), default="wardrobe")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    observations: Mapped[list[GarmentObservation]] = relationship(back_populates="garment")


class GarmentObservation(Base, TimestampedOwner):
    __tablename__ = "garment_observations"

    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspaces.id"), nullable=False)
    garment_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("garments.id"), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("assets.id"), nullable=False)
    bbox: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    occlusion: Mapped[str] = mapped_column(String(32), default="none")
    visible_evidence: Mapped[str] = mapped_column(Text, default="")
    model_confidence: Mapped[float | None] = mapped_column(nullable=True)
    provider: Mapped[str] = mapped_column(String(32), default="gemini")
    model_id: Mapped[str] = mapped_column(String(64), default="")
    prompt_version: Mapped[str] = mapped_column(String(64), default="")
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    user_corrected: Mapped[bool] = mapped_column(Boolean, default=False)

    garment: Mapped[Garment] = relationship(back_populates="observations")


class Product(Base, TimestampedOwner):
    __tablename__ = "products"

    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspaces.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_kind: Mapped[str] = mapped_column(String(32), default="manual")
    image_asset_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("assets.id"), nullable=False)
    price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    subtype: Mapped[str | None] = mapped_column(String(64), nullable=True)
    colour: Mapped[str | None] = mapped_column(String(64), nullable=True)
    colour_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pattern: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pattern_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    formality_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    formality_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_origin: Mapped[str] = mapped_column(String(32), default="user_entered")
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shipping_tax_included: Mapped[bool] = mapped_column(Boolean, default=False)
    fetch_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    youcam_eligible: Mapped[bool] = mapped_column(Boolean, default=False)


class CartItem(Base, TimestampedOwner):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("workspace_id", "product_id", name="uq_cart_product"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspaces.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("products.id"), nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    garment_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("garments.id"), nullable=True)


class Analysis(Base, TimestampedOwner):
    __tablename__ = "analyses"

    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspaces.id"), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("jobs.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    occasion: Mapped[str] = mapped_column(String(32), default="any")
    budget_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    footwear_required: Mapped[bool] = mapped_column(Boolean, default=False)
    max_items: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_snapshot_hash: Mapped[str] = mapped_column(String(64), default="")
    algorithm_version: Mapped[str] = mapped_column(String(32), default="exact-v1")
    rule_version: Mapped[str] = mapped_column(String(32), default="compat-v1")
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    error_safe: Mapped[str | None] = mapped_column(Text, nullable=True)


class OutfitCandidate(Base, TimestampedOwner):
    __tablename__ = "outfit_candidates"
    __table_args__ = (Index("ix_outfit_combination", "workspace_id", "combination_id"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspaces.id"), nullable=False)
    analysis_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("analyses.id"), nullable=False)
    combination_id: Mapped[str] = mapped_column(String(64), nullable=False)
    garment_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    template: Mapped[str] = mapped_column(String(64), nullable=False)
    cluster_id: Mapped[str] = mapped_column(String(64), nullable=False)
    qualified: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    youcam_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    rule_contributions: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    rejection_reasons: Mapped[list[str]] = mapped_column(JSONType, default=list)
    cart_mask: Mapped[int] = mapped_column(Integer, default=0)


class OutfitCluster(Base, TimestampedOwner):
    __tablename__ = "outfit_clusters"

    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspaces.id"), nullable=False)
    analysis_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("analyses.id"), nullable=False)
    cluster_id: Mapped[str] = mapped_column(String(64), nullable=False)
    signature: Mapped[str] = mapped_column(String(512), nullable=False)
    member_combination_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    wardrobe_unlocked: Mapped[bool] = mapped_column(Boolean, default=False)
    unlock_masks: Mapped[list[int]] = mapped_column(JSONType, default=list)


class Basket(Base, TimestampedOwner):
    __tablename__ = "baskets"

    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspaces.id"), nullable=False)
    analysis_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("analyses.id"), nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    product_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    cost_minor: Mapped[int] = mapped_column(Integer, default=0)
    objective_value: Mapped[int] = mapped_column(Integer, default=0)
    runtime_ms: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class Feedback(Base, TimestampedOwner):
    __tablename__ = "feedback"

    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspaces.id"), nullable=False)
    analysis_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("analyses.id"), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class Job(Base, TimestampedOwner):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_claim", "status", "available_at"),
        UniqueConstraint("owner_id", "kind", "idempotency_key", name="uq_job_idempotency"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspaces.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    error_safe: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)


class ProviderTask(Base, TimestampedOwner):
    __tablename__ = "provider_tasks"

    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspaces.id"), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("jobs.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_task_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="created")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_safe: Mapped[str | None] = mapped_column(Text, nullable=True)
    units_reserved: Mapped[int] = mapped_column(Integer, default=0)
    units_observed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_status: Mapped[str] = mapped_column(String(32), default="reserved")
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    result_asset_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("assets.id"), nullable=True)
    parent_output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class UsageLedger(Base, TimestampedOwner):
    __tablename__ = "usage_ledger"

    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspaces.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_task_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("provider_tasks.id"), nullable=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    estimated: Mapped[bool] = mapped_column(Boolean, default=True)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("owner_id", "key", "method", "path", name="uq_idempotency"),)


class TryOnRequest(Base, TimestampedOwner):
    __tablename__ = "tryon_requests"

    workspace_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("workspaces.id"), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("jobs.id"), nullable=True)
    source_asset_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("assets.id"), nullable=False)
    combination_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    garment_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    category_path: Mapped[list[str]] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    live: Mapped[bool] = mapped_column(Boolean, default=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    result_asset_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("assets.id"), nullable=True)
    step_assets: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    limitation: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_safe: Mapped[str | None] = mapped_column(Text, nullable=True)
