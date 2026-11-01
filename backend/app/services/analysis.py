from __future__ import annotations

import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Analysis,
    Basket,
    CartItem,
    Feedback,
    Garment,
    OutfitCandidate,
    OutfitCluster,
    Product,
)
from app.services.compatibility import Item
from app.services.optimizer import ALGORITHM_VERSION, optimise, result_to_dict
from app.services.compatibility import RULE_VERSION


def _snapshot_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _garment_item(garment: Garment, source: str, cart_bit: int | None = None, price: int = 0) -> Item:
    return Item(
        id=str(garment.id),
        category=garment.category,
        subtype=garment.subtype,
        colour=garment.colour,
        colour_family=garment.colour_family,
        pattern=garment.pattern,
        pattern_family=garment.pattern_family,
        formality_min=garment.formality_min,
        formality_max=garment.formality_max,
        source=source,
        cart_bit=cart_bit,
        price_minor=price,
        display_name=garment.display_name or garment.category,
        analysis_eligible=garment.analysis_eligible and garment.status == "confirmed",
        youcam_eligible=garment.youcam_eligible,
        excluded=garment.status == "excluded",
    )


def run_analysis(session: Session, analysis: Analysis) -> dict:
    wardrobe_rows = session.scalars(
        select(Garment).where(
            Garment.workspace_id == analysis.workspace_id,
            Garment.owner_id == analysis.owner_id,
            Garment.source_kind == "wardrobe",
            Garment.merged_into_id.is_(None),
        )
    ).all()
    cart_rows = session.scalars(
        select(CartItem).where(
            CartItem.workspace_id == analysis.workspace_id,
            CartItem.owner_id == analysis.owner_id,
        )
    ).all()
    rejected = {
        row.target_id
        for row in session.scalars(
            select(Feedback).where(
                Feedback.workspace_id == analysis.workspace_id,
                Feedback.verdict == "reject",
                Feedback.target_kind == "outfit",
            )
        )
    }

    wardrobe = [_garment_item(row, "wardrobe") for row in wardrobe_rows]
    cart_items: list[Item] = []
    pinned: set[str] = set()
    excluded: set[str] = set()
    currencies: set[str] = set()
    for cart in cart_rows:
        product = session.get(Product, cart.product_id)
        if not product:
            continue
        currencies.add(product.currency)
        garment = session.get(Garment, cart.garment_id) if cart.garment_id else None
        if garment is None:
            garment = Garment(
                owner_id=analysis.owner_id,
                workspace_id=analysis.workspace_id,
                canonical_key=str(product.id),
                display_name=product.title,
                category=product.category,
                subtype=product.subtype,
                colour=product.colour,
                colour_family=product.colour_family,
                pattern=product.pattern,
                pattern_family=product.pattern_family,
                formality_min=product.formality_min,
                formality_max=product.formality_max,
                status="confirmed",
                needs_review=False,
                analysis_eligible=True,
                youcam_eligible=product.youcam_eligible,
                crop_asset_id=product.image_asset_id,
                source_kind="cart",
            )
            session.add(garment)
            session.flush()
            cart.garment_id = garment.id
        item = _garment_item(garment, "cart", price=product.price_minor)
        cart_items.append(item)
        if cart.pinned:
            pinned.add(item.id)
        if cart.excluded:
            excluded.add(item.id)

    if len(currencies) > 1:
        raise ValueError("A single currency is required per optimisation. Mixed cart currencies were rejected.")
    if analysis.currency and currencies and analysis.currency not in currencies:
        raise ValueError("Analysis currency does not match cart currency.")

    snapshot = {
        "wardrobe": [item.id for item in wardrobe],
        "cart": [item.id for item in cart_items],
        "occasion": analysis.occasion,
        "budget_minor": analysis.budget_minor,
        "footwear_required": analysis.footwear_required,
        "max_items": analysis.max_items,
        "rejected": sorted(rejected),
        "rule_version": RULE_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
    }
    analysis.input_snapshot_hash = _snapshot_hash(snapshot)
    analysis.algorithm_version = ALGORITHM_VERSION
    analysis.rule_version = RULE_VERSION

    result = optimise(
        wardrobe=wardrobe,
        cart=cart_items,
        occasion=analysis.occasion,
        budget_minor=analysis.budget_minor,
        footwear_required=analysis.footwear_required,
        pinned_ids=pinned,
        excluded_ids=excluded,
        max_items=analysis.max_items,
        rejected_combination_ids=rejected,
    )
    payload = result_to_dict(result)
    analysis.result = payload
    analysis.status = "failed" if result.rejected_infeasible else "succeeded"
    analysis.error_safe = result.rejected_infeasible

    session.query(OutfitCandidate).filter(OutfitCandidate.analysis_id == analysis.id).delete()
    session.query(OutfitCluster).filter(OutfitCluster.analysis_id == analysis.id).delete()
    session.query(Basket).filter(Basket.analysis_id == analysis.id).delete()

    for outfit in result.outfits:
        session.add(
            OutfitCandidate(
                owner_id=analysis.owner_id,
                workspace_id=analysis.workspace_id,
                analysis_id=analysis.id,
                combination_id=outfit.combination_id,
                garment_ids=list(outfit.garment_ids),
                template=outfit.template,
                cluster_id=outfit.cluster_id,
                qualified=outfit.qualified,
                needs_review=outfit.needs_review,
                youcam_eligible=outfit.youcam_eligible,
                rule_contributions=outfit.to_dict()["rule_contributions"],
                rejection_reasons=outfit.rejection_reasons,
                cart_mask=outfit.cart_mask,
            )
        )
    for cluster in result.clusters:
        session.add(
            OutfitCluster(
                owner_id=analysis.owner_id,
                workspace_id=analysis.workspace_id,
                analysis_id=analysis.id,
                cluster_id=cluster.cluster_id,
                signature=cluster.signature,
                member_combination_ids=cluster.member_combination_ids,
                wardrobe_unlocked=cluster.wardrobe_unlocked,
                unlock_masks=cluster.unlock_masks,
            )
        )
    for method in (result.exact, result.greedy, result.cheapest, result.standalone_rank):
        session.add(
            Basket(
                owner_id=analysis.owner_id,
                workspace_id=analysis.workspace_id,
                analysis_id=analysis.id,
                method=method.method,
                product_ids=method.product_ids,
                cost_minor=method.cost_minor,
                objective_value=method.objective_value,
                runtime_ms=method.runtime_ms,
                details=method.details,
            )
        )
    session.commit()
    return payload
