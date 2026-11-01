"""Transparent compatibility rules. Configuration, not a trained recommender."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

RULE_VERSION = "compat-v1"

CATEGORIES = ("top", "bottom", "dress", "outerwear", "footwear")
MAIN_CATEGORIES = {"top", "bottom", "dress"}

OCCASION_RANGES: dict[str, tuple[int, int]] = {
    "casual": (0, 40),
    "smart_casual": (25, 65),
    "office": (50, 85),
    "business": (50, 85),
    "evening": (60, 100),
    "any": (0, 100),
}

NEUTRAL_FAMILIES = {
    "black",
    "white",
    "grey",
    "gray",
    "beige",
    "navy",
    "cream",
    "ivory",
    "taupe",
    "camel",
    "brown",
    "denim",
    "stone",
}

ADJACENT_FAMILIES = {
    frozenset({"navy", "blue"}),
    frozenset({"blue", "teal"}),
    frozenset({"green", "teal"}),
    frozenset({"green", "olive"}),
    frozenset({"olive", "brown"}),
    frozenset({"brown", "camel"}),
    frozenset({"red", "burgundy"}),
    frozenset({"pink", "red"}),
    frozenset({"pink", "purple"}),
    frozenset({"yellow", "camel"}),
}

COMPLEMENTARY_MAINS = {
    frozenset({"red", "green"}),
    frozenset({"orange", "blue"}),
    frozenset({"yellow", "purple"}),
    frozenset({"pink", "green"}),
}

SOLID_PATTERNS = {"solid", "none", "heather", "melange"}
BUSY_PATTERNS = {"plaid", "check", "floral", "animal", "graphic", "paisley", "geometric", "stripe"}


@dataclass(frozen=True)
class Item:
    id: str
    category: str
    subtype: str | None
    colour: str | None
    colour_family: str | None
    pattern: str | None
    pattern_family: str | None
    formality_min: int | None
    formality_max: int | None
    source: str
    cart_bit: int | None = None
    price_minor: int = 0
    display_name: str = ""
    analysis_eligible: bool = True
    youcam_eligible: bool = False
    excluded: bool = False
    rejected_looks: tuple[str, ...] = ()


@dataclass
class RuleContribution:
    rule: str
    passed: bool
    detail: str


@dataclass
class Outfit:
    combination_id: str
    garment_ids: tuple[str, ...]
    items: tuple[Item, ...]
    template: str
    cluster_signature: str
    cluster_id: str
    qualified: bool
    needs_review: bool
    youcam_eligible: bool
    rule_contributions: list[RuleContribution] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    cart_mask: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "combination_id": self.combination_id,
            "garment_ids": list(self.garment_ids),
            "template": self.template,
            "cluster_signature": self.cluster_signature,
            "cluster_id": self.cluster_id,
            "qualified": self.qualified,
            "needs_review": self.needs_review,
            "youcam_eligible": self.youcam_eligible,
            "rule_contributions": [asdict(item) for item in self.rule_contributions],
            "rejection_reasons": self.rejection_reasons,
            "cart_mask": self.cart_mask,
            "items": [
                {
                    "id": item.id,
                    "category": item.category,
                    "display_name": item.display_name,
                    "source": item.source,
                    "colour": item.colour,
                    "subtype": item.subtype,
                }
                for item in self.items
            ],
        }


def _norm(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lower()
    return cleaned or None


def combination_id(ids: Iterable[str]) -> str:
    joined = "|".join(sorted(ids))
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


def cluster_signature(template: str, items: Iterable[Item]) -> str:
    parts = [template]
    for item in sorted(items, key=lambda value: (value.category, value.id)):
        parts.append(
            ":".join(
                [
                    item.category,
                    _norm(item.subtype) or "*",
                    _norm(item.pattern_family) or "*",
                    _norm(item.colour_family) or "*",
                ]
            )
        )
    return "|".join(parts)


def cluster_id_for(signature: str) -> str:
    return hashlib.sha256(signature.encode()).hexdigest()[:16]


def _range_overlap(left: tuple[int, int] | None, right: tuple[int, int] | None) -> bool | None:
    if left is None or right is None:
        return None
    return left[0] <= right[1] and right[0] <= left[1]


def _item_formality(item: Item) -> tuple[int, int] | None:
    if item.formality_min is None or item.formality_max is None:
        return None
    return (item.formality_min, item.formality_max)


def _colour_result(a: Item, b: Item) -> tuple[bool | None, str]:
    fa, fb = _norm(a.colour_family), _norm(b.colour_family)
    if fa is None or fb is None:
        return None, "Unknown colour family requires review; no invented pairing."
    if fa == fb:
        return True, f"Same colour family ({fa})."
    if fa in NEUTRAL_FAMILIES or fb in NEUTRAL_FAMILIES:
        return True, "Neutral colour family pairs with any known family."
    if frozenset({fa, fb}) in ADJACENT_FAMILIES:
        return True, f"Adjacent colour families ({fa}, {fb})."
    if {a.category, b.category} <= MAIN_CATEGORIES and frozenset({fa, fb}) in COMPLEMENTARY_MAINS:
        return False, f"Complementary saturated mains ({fa}, {fb}) are excluded by rule."
    return True, f"No blocking colour rule for ({fa}, {fb})."


def _pattern_result(a: Item, b: Item) -> tuple[bool | None, str]:
    pa, pb = _norm(a.pattern_family), _norm(b.pattern_family)
    if pa is None or pb is None:
        return None, "Unknown pattern family requires review; no invented pairing."
    if pa in SOLID_PATTERNS or pb in SOLID_PATTERNS:
        return True, "Solid/heather pairs with any known pattern family."
    if pa == pb:
        return True, f"Same pattern family ({pa})."
    if pa in BUSY_PATTERNS and pb in BUSY_PATTERNS and pa != pb:
        if {a.category, b.category} <= MAIN_CATEGORIES:
            return False, f"Two busy pattern families on main garments ({pa}, {pb})."
    return True, f"No blocking pattern rule for ({pa}, {pb})."


def evaluate_outfit(
    items: list[Item],
    occasion: str,
    footwear_required: bool,
    rejected_combination_ids: set[str] | None = None,
) -> Outfit:
    rejected_combination_ids = rejected_combination_ids or set()
    ordered = tuple(sorted(items, key=lambda item: item.id))
    combo = combination_id(item.id for item in ordered)
    categories = {item.category for item in ordered}
    contributions: list[RuleContribution] = []
    rejections: list[str] = []
    review = False

    if any(item.excluded for item in ordered):
        rejections.append("An excluded garment is present.")
        contributions.append(RuleContribution("exclusion", False, "Explicit exclusion."))

    if any(not item.analysis_eligible for item in ordered):
        rejections.append("A garment is not analysis-eligible until confirmed.")
        contributions.append(RuleContribution("eligibility", False, "Unconfirmed garment."))

    if "dress" in categories:
        template = "dress"
        if "top" in categories or "bottom" in categories:
            rejections.append("Dress templates cannot include a separate top or bottom.")
            contributions.append(RuleContribution("template", False, "Dress plus top/bottom."))
        else:
            contributions.append(RuleContribution("template", True, "Dress template."))
    elif "top" in categories and "bottom" in categories:
        template = "top+bottom"
        contributions.append(RuleContribution("template", True, "Top plus bottom template."))
    else:
        template = "incomplete"
        rejections.append("MVP templates require top+bottom or a dress.")
        contributions.append(RuleContribution("template", False, "Incomplete template."))

    if categories.intersection({"top", "bottom", "dress"}) and sum(
        1 for item in ordered if item.category in MAIN_CATEGORIES
    ) > (1 if "dress" in categories else 2):
        rejections.append("Category consistency failed: extra main garments.")

    if footwear_required and "footwear" not in categories:
        rejections.append("Footwear is required by analysis configuration.")
        contributions.append(RuleContribution("footwear", False, "Required footwear missing."))
    elif not footwear_required and "footwear" in categories:
        rejections.append("Footwear is included only when configured as required.")
        contributions.append(RuleContribution("footwear", False, "Optional footwear omitted from templates."))
    else:
        contributions.append(
            RuleContribution("footwear", True, "Footwear rule satisfied under current configuration.")
        )

    occasion_range = OCCASION_RANGES.get(occasion, OCCASION_RANGES["any"])
    formality_values = [_item_formality(item) for item in ordered]
    if any(value is None for value in formality_values):
        review = True
        contributions.append(
            RuleContribution("formality", False, "Unknown formality triggers review, not invented overlap.")
        )
        rejections.append("Unknown formality: outfit held for review.")
    else:
        ok = all(_range_overlap(value, occasion_range) for value in formality_values)
        pairwise = True
        typed = [value for value in formality_values if value is not None]
        for index, left in enumerate(typed):
            for right in typed[index + 1 :]:
                pairwise = pairwise and bool(_range_overlap(left, right))
        if ok and pairwise:
            contributions.append(RuleContribution("formality", True, f"Overlaps occasion {occasion} {occasion_range}."))
        else:
            rejections.append("Formality range does not overlap the selected occasion or other garments.")
            contributions.append(RuleContribution("formality", False, "No formality overlap."))

    pairs = [(ordered[i], ordered[j]) for i in range(len(ordered)) for j in range(i + 1, len(ordered))]
    for left, right in pairs:
        colour_ok, colour_detail = _colour_result(left, right)
        if colour_ok is None:
            review = True
            rejections.append(colour_detail)
            contributions.append(RuleContribution("colour", False, colour_detail))
        elif colour_ok:
            contributions.append(RuleContribution("colour", True, colour_detail))
        else:
            rejections.append(colour_detail)
            contributions.append(RuleContribution("colour", False, colour_detail))

        pattern_ok, pattern_detail = _pattern_result(left, right)
        if pattern_ok is None:
            review = True
            rejections.append(pattern_detail)
            contributions.append(RuleContribution("pattern", False, pattern_detail))
        elif pattern_ok:
            contributions.append(RuleContribution("pattern", True, pattern_detail))
        else:
            rejections.append(pattern_detail)
            contributions.append(RuleContribution("pattern", False, pattern_detail))

    if combo in rejected_combination_ids:
        rejections.append("User rejected this look; excluded from subsequent versions.")
        contributions.append(RuleContribution("feedback", False, "User rejection."))

    signature = cluster_signature(template, ordered)
    qualified = not rejections
    youcam = qualified and all(item.youcam_eligible for item in ordered)
    cart_mask = 0
    for item in ordered:
        if item.source == "cart" and item.cart_bit is not None:
            cart_mask |= 1 << item.cart_bit

    return Outfit(
        combination_id=combo,
        garment_ids=tuple(item.id for item in ordered),
        items=ordered,
        template=template,
        cluster_signature=signature,
        cluster_id=cluster_id_for(signature),
        qualified=qualified,
        needs_review=review and not qualified,
        youcam_eligible=youcam,
        rule_contributions=contributions,
        rejection_reasons=rejections,
        cart_mask=cart_mask,
    )


def generate_outfits(
    wardrobe: list[Item],
    cart: list[Item],
    occasion: str,
    footwear_required: bool,
    rejected_combination_ids: set[str] | None = None,
) -> list[Outfit]:
    pool = [item for item in (*wardrobe, *cart) if not item.excluded]
    by_cat: dict[str, list[Item]] = {category: [] for category in CATEGORIES}
    for item in pool:
        if item.category in by_cat:
            by_cat[item.category].append(item)

    outfits: list[Outfit] = []
    seen: set[str] = set()

    def consider(members: list[Item]) -> None:
        evaluated = evaluate_outfit(members, occasion, footwear_required, rejected_combination_ids)
        if evaluated.combination_id in seen:
            return
        seen.add(evaluated.combination_id)
        outfits.append(evaluated)

    outerwear_options: list[Item | None] = [None, *by_cat["outerwear"]]
    footwear_options: list[Item | None] = [None]
    if footwear_required:
        footwear_options = list(by_cat["footwear"]) or []

    for top in by_cat["top"]:
        for bottom in by_cat["bottom"]:
            for outer in outerwear_options:
                if footwear_required:
                    for shoe in footwear_options:
                        consider([item for item in (top, bottom, outer, shoe) if item])
                else:
                    consider([item for item in (top, bottom, outer) if item])

    for dress in by_cat["dress"]:
        for outer in outerwear_options:
            if footwear_required:
                for shoe in footwear_options:
                    consider([item for item in (dress, outer, shoe) if item])
            else:
                consider([item for item in (dress, outer) if item])

    return outfits


def pairwise_edges(outfits: list[Outfit]) -> list[dict[str, Any]]:
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    for outfit in outfits:
        if not outfit.qualified:
            continue
        ids = list(outfit.garment_ids)
        for i, left in enumerate(ids):
            for right in ids[i + 1 :]:
                key = (left, right) if left < right else (right, left)
                bucket = edges.setdefault(
                    key,
                    {
                        "source": key[0],
                        "target": key[1],
                        "qualified_outfit_ids": [],
                        "evidence": [],
                    },
                )
                bucket["qualified_outfit_ids"].append(outfit.combination_id)
                bucket["evidence"].append(
                    {
                        "combination_id": outfit.combination_id,
                        "template": outfit.template,
                        "rules": [asdict(rule) for rule in outfit.rule_contributions if rule.passed],
                    }
                )
    return list(edges.values())
