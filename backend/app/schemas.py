from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ConsentIn(BaseModel):
    kind: str = "external_image_processing"
    policy_version: str = "2026-11-01"
    granted: bool
    notes: str | None = None


class AssetOut(BaseModel):
    id: UUID
    kind: str
    mime_type: str
    width: int
    height: int
    byte_size: int
    rights_status: str
    created_at: datetime


class GarmentUpdate(BaseModel):
    display_name: str | None = None
    category: str | None = None
    subtype: str | None = None
    colour: str | None = None
    colour_family: str | None = None
    pattern: str | None = None
    pattern_family: str | None = None
    formality_min: int | None = Field(default=None, ge=0, le=100)
    formality_max: int | None = Field(default=None, ge=0, le=100)
    notes: str | None = None
    confirm: bool = False
    exclude: bool = False


class MergeIn(BaseModel):
    source_ids: list[UUID]
    target_id: UUID
    confirmed: bool


class ProductManualIn(BaseModel):
    title: str
    price_major: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=8)
    category: str
    subtype: str | None = None
    colour: str | None = None
    colour_family: str | None = None
    pattern: str | None = None
    pattern_family: str | None = None
    formality_min: int | None = None
    formality_max: int | None = None
    source_url: str | None = None
    shipping_tax_included: bool = False


class ProductUrlIn(BaseModel):
    url: str
    category: str
    title: str | None = None
    price_major: float | None = None
    currency: str | None = None


class CartPatch(BaseModel):
    pinned: bool | None = None
    excluded: bool | None = None


class AnalysisIn(BaseModel):
    occasion: str = "any"
    budget_minor: int = Field(gt=0)
    currency: str = "USD"
    footwear_required: bool = False
    max_items: int | None = Field(default=None, ge=1, le=10)


class FeedbackIn(BaseModel):
    analysis_id: UUID
    target_kind: str
    target_id: str
    verdict: str
    note: str | None = None


class TryOnIn(BaseModel):
    combination_id: str | None = None
    garment_ids: list[UUID] = []
    force_live: bool = True
