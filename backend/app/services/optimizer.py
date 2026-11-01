"""Exact basket search and declared baselines under identical constraints."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.services.compatibility import Item, Outfit, generate_outfits, pairwise_edges

ALGORITHM_VERSION = "exact-v1"
MAX_CANDIDATES = 10


@dataclass
class ClusterView:
    cluster_id: str
    signature: str
    member_combination_ids: list[str]
    wardrobe_unlocked: bool
    unlock_masks: list[int]


@dataclass
class MethodResult:
    method: str
    product_ids: list[str]
    bits: int
    cost_minor: int
    objective_value: int
    runtime_ms: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class OptimisationResult:
    wardrobe_cluster_count: int
    clusters: list[ClusterView]
    outfits: list[Outfit]
    edges: list[dict[str, Any]]
    standalone: list[dict[str, Any]]
    exact: MethodResult
    greedy: MethodResult
    cheapest: MethodResult
    standalone_rank: MethodResult
    frontier: list[dict[str, Any]]
    synergy: list[dict[str, Any]]
    comparison: list[dict[str, Any]]
    rejected_infeasible: str | None = None


def _cluster_views(outfits: list[Outfit]) -> list[ClusterView]:
    grouped: dict[str, ClusterView] = {}
    for outfit in outfits:
        if not outfit.qualified:
            continue
        view = grouped.get(outfit.cluster_id)
        if view is None:
            view = ClusterView(
                cluster_id=outfit.cluster_id,
                signature=outfit.cluster_signature,
                member_combination_ids=[],
                wardrobe_unlocked=False,
                unlock_masks=[],
            )
            grouped[outfit.cluster_id] = view
        view.member_combination_ids.append(outfit.combination_id)
        if outfit.cart_mask == 0:
            view.wardrobe_unlocked = True
        elif outfit.cart_mask not in view.unlock_masks:
            view.unlock_masks.append(outfit.cart_mask)
    return list(grouped.values())


def _objective(clusters: list[ClusterView], mask: int) -> int:
    baseline = sum(1 for cluster in clusters if cluster.wardrobe_unlocked)
    unlocked = 0
    for cluster in clusters:
        if cluster.wardrobe_unlocked:
            unlocked += 1
            continue
        if any(required & mask == required for required in cluster.unlock_masks):
            unlocked += 1
    return unlocked - baseline


def _cost(cart: list[Item], mask: int) -> int:
    return sum(item.price_minor for item in cart if item.cart_bit is not None and mask & (1 << item.cart_bit))


def _ids(cart: list[Item], mask: int) -> list[str]:
    return [item.id for item in cart if item.cart_bit is not None and mask & (1 << item.cart_bit)]


def _count(mask: int) -> int:
    return mask.bit_count()


def _feasible(mask: int, pinned: int, excluded: int, budget: int, max_items: int | None, cart: list[Item]) -> bool:
    if mask & excluded:
        return False
    if pinned & mask != pinned:
        return False
    if max_items is not None and _count(mask) > max_items:
        return False
    return _cost(cart, mask) <= budget


def _pick_best(candidates: Iterable[tuple[int, int, int, int, str]]) -> tuple[int, int, int, int, str] | None:
    """Tuples are (objective, -cost, -count, mask, first_id). Maximise objective, then cheaper, fewer, stable id."""
    best = None
    for row in candidates:
        if best is None or row > best:
            best = row
    return best


def _enumerate_exact(
    cart: list[Item],
    clusters: list[ClusterView],
    pinned: int,
    excluded: int,
    budget: int,
    max_items: int | None,
) -> tuple[MethodResult, list[dict[str, Any]]]:
    started = time.perf_counter()
    n = len(cart)
    if n > MAX_CANDIDATES:
        raise ValueError(f"Exact search supports at most {MAX_CANDIDATES} candidates, received {n}.")

    best_mask = pinned
    best_obj = _objective(clusters, pinned) if _feasible(pinned, pinned, excluded, budget, max_items, cart) else -1
    best_cost = _cost(cart, pinned) if best_obj >= 0 else 10**18
    best_count = _count(pinned)
    frontier_by_cost: dict[int, dict[str, Any]] = {}
    evaluated = 0

    if not _feasible(pinned, pinned, excluded, budget, max_items, cart):
        runtime = int((time.perf_counter() - started) * 1000)
        return (
            MethodResult(
                method="exact",
                product_ids=[],
                bits=0,
                cost_minor=0,
                objective_value=0,
                runtime_ms=runtime,
                details={"infeasible": True},
            ),
            [],
        )

    for mask in range(1 << n):
        if not _feasible(mask, pinned, excluded, budget, max_items, cart):
            continue
        evaluated += 1
        obj = _objective(clusters, mask)
        cost = _cost(cart, mask)
        count = _count(mask)
        first_id = min(_ids(cart, mask) or [""])
        current = (obj, -cost, -count, -int.from_bytes(first_id.encode()[:8].ljust(8, b"\0"), "big"), mask)
        best_tuple = (best_obj, -best_cost, -best_count, 0, best_mask)
        if current > best_tuple:
            best_mask, best_obj, best_cost, best_count = mask, obj, cost, count
        existing = frontier_by_cost.get(cost)
        if existing is None or (obj, -count, first_id) > (
            existing["objective_value"],
            -len(existing["product_ids"]),
            existing["product_ids"][0] if existing["product_ids"] else "",
        ):
            frontier_by_cost[cost] = {
                "cost_minor": cost,
                "objective_value": obj,
                "product_ids": _ids(cart, mask),
                "bits": mask,
            }

    # Step frontier: running best objective at each increasing breakpoint.
    steps: list[dict[str, Any]] = []
    running_best = -1
    running_row: dict[str, Any] | None = None
    for cost in sorted(frontier_by_cost):
        row = frontier_by_cost[cost]
        if row["objective_value"] > running_best:
            running_best = row["objective_value"]
            running_row = row
        if running_row is not None:
            steps.append({**running_row, "breakpoint_minor": cost})

    runtime = int((time.perf_counter() - started) * 1000)
    return (
        MethodResult(
            method="exact",
            product_ids=_ids(cart, best_mask),
            bits=best_mask,
            cost_minor=best_cost if best_obj >= 0 else 0,
            objective_value=max(best_obj, 0),
            runtime_ms=runtime,
            details={"subsets_evaluated": evaluated, "guarantee": "exact under declared rules"},
        ),
        steps,
    )


def _greedy_marginal(
    cart: list[Item],
    clusters: list[ClusterView],
    pinned: int,
    excluded: int,
    budget: int,
    max_items: int | None,
) -> MethodResult:
    started = time.perf_counter()
    mask = pinned
    if not _feasible(mask, pinned, excluded, budget, max_items, cart):
        return MethodResult("greedy_marginal", [], 0, 0, 0, 0, {"infeasible": True})

    remaining = [item for item in cart if item.cart_bit is not None and not (mask & (1 << item.cart_bit))]
    while remaining:
        scored: list[tuple[float, int, int, str, Item]] = []
        current = _objective(clusters, mask)
        for item in remaining:
            bit = 1 << (item.cart_bit or 0)
            candidate = mask | bit
            if not _feasible(candidate, pinned, excluded, budget, max_items, cart):
                continue
            gain = _objective(clusters, candidate) - current
            cost = max(item.price_minor, 1)
            scored.append((gain / cost, -item.price_minor, gain, item.id, item))
        if not scored:
            break
        scored.sort(reverse=True)
        chosen = scored[0][4]
        mask |= 1 << (chosen.cart_bit or 0)
        remaining = [item for item in remaining if item.id != chosen.id]

    runtime = int((time.perf_counter() - started) * 1000)
    return MethodResult(
        method="greedy_marginal",
        product_ids=_ids(cart, mask),
        bits=mask,
        cost_minor=_cost(cart, mask),
        objective_value=_objective(clusters, mask),
        runtime_ms=runtime,
        details={
            "note": "Dynamic marginal yield per cost. Complementarity means f need not be submodular; no approximation guarantee."
        },
    )


def _cheapest_first(
    cart: list[Item],
    clusters: list[ClusterView],
    pinned: int,
    excluded: int,
    budget: int,
    max_items: int | None,
) -> MethodResult:
    started = time.perf_counter()
    mask = pinned
    if not _feasible(mask, pinned, excluded, budget, max_items, cart):
        return MethodResult("cheapest_first", [], 0, 0, 0, 0, {"infeasible": True})
    for item in sorted(cart, key=lambda value: (value.price_minor, value.id)):
        if item.cart_bit is None:
            continue
        candidate = mask | (1 << item.cart_bit)
        if candidate == mask:
            continue
        if _feasible(candidate, pinned, excluded, budget, max_items, cart):
            mask = candidate
    runtime = int((time.perf_counter() - started) * 1000)
    return MethodResult(
        method="cheapest_first",
        product_ids=_ids(cart, mask),
        bits=mask,
        cost_minor=_cost(cart, mask),
        objective_value=_objective(clusters, mask),
        runtime_ms=runtime,
        details={},
    )


def _standalone_rank(
    cart: list[Item],
    clusters: list[ClusterView],
    pinned: int,
    excluded: int,
    budget: int,
    max_items: int | None,
) -> MethodResult:
    started = time.perf_counter()
    mask = pinned
    if not _feasible(mask, pinned, excluded, budget, max_items, cart):
        return MethodResult("standalone_yield", [], 0, 0, 0, 0, {"infeasible": True})
    ranked = sorted(
        cart,
        key=lambda item: (
            -_objective(clusters, pinned | (1 << (item.cart_bit or 0)) if item.cart_bit is not None else 0),
            item.price_minor,
            item.id,
        ),
    )
    for item in ranked:
        if item.cart_bit is None:
            continue
        candidate = mask | (1 << item.cart_bit)
        if candidate == mask:
            continue
        if _feasible(candidate, pinned, excluded, budget, max_items, cart):
            mask = candidate
    runtime = int((time.perf_counter() - started) * 1000)
    return MethodResult(
        method="standalone_yield",
        product_ids=_ids(cart, mask),
        bits=mask,
        cost_minor=_cost(cart, mask),
        objective_value=_objective(clusters, mask),
        runtime_ms=runtime,
        details={"note": "Standalone f({x}) ranking is not additive with overlapping yields."},
    )


def _synergy(cart: list[Item], clusters: list[ClusterView], pinned: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, left in enumerate(cart):
        if left.cart_bit is None:
            continue
        for right in cart[i + 1 :]:
            if right.cart_bit is None:
                continue
            a = pinned | (1 << left.cart_bit)
            b = pinned | (1 << right.cart_bit)
            both = a | b
            fa = _objective(clusters, a)
            fb = _objective(clusters, b)
            fab = _objective(clusters, both)
            delta = fab - fa - fb
            supporting = [
                cluster.cluster_id
                for cluster in clusters
                if not cluster.wardrobe_unlocked
                and any(required & both == required for required in cluster.unlock_masks)
                and not any(required & a == required for required in cluster.unlock_masks)
                and not any(required & b == required for required in cluster.unlock_masks)
            ]
            rows.append(
                {
                    "i": left.id,
                    "j": right.id,
                    "i_name": left.display_name,
                    "j_name": right.display_name,
                    "f_i": fa,
                    "f_j": fb,
                    "f_ij": fab,
                    "synergy": delta,
                    "explanation": (
                        "Positive complementarity: the pair unlocks clusters neither item unlocks alone."
                        if delta > 0
                        else "Negative overlap: the pair shares unlocks already counted in standalone yields."
                        if delta < 0
                        else "No pairwise interaction beyond standalone yields."
                    ),
                    "supporting_cluster_ids": supporting,
                }
            )
    return rows


def _gap(method: MethodResult, exact: MethodResult) -> dict[str, Any]:
    absolute = exact.objective_value - method.objective_value
    percent: float | None
    if exact.objective_value == 0:
        percent = None
    else:
        percent = absolute / exact.objective_value
    return {
        "method": method.method,
        "objective_value": method.objective_value,
        "product_ids": method.product_ids,
        "cost_minor": method.cost_minor,
        "runtime_ms": method.runtime_ms,
        "absolute_gap": absolute,
        "percentage_gap": percent,
        "percentage_gap_defined": percent is not None,
        "details": method.details,
    }


def optimise(
    wardrobe: list[Item],
    cart: list[Item],
    occasion: str,
    budget_minor: int,
    footwear_required: bool,
    pinned_ids: set[str] | None = None,
    excluded_ids: set[str] | None = None,
    max_items: int | None = None,
    rejected_combination_ids: set[str] | None = None,
) -> OptimisationResult:
    pinned_ids = pinned_ids or set()
    excluded_ids = excluded_ids or set()
    if len(cart) > MAX_CANDIDATES:
        raise ValueError(f"At most {MAX_CANDIDATES} cart candidates can be optimised.")

    indexed: list[Item] = []
    for index, item in enumerate(cart):
        indexed.append(
            Item(
                **{
                    **item.__dict__,
                    "cart_bit": index,
                    "source": "cart",
                    "excluded": item.id in excluded_ids or item.excluded,
                }
            )
        )

    pinned = 0
    excluded = 0
    for item in indexed:
        if item.cart_bit is None:
            continue
        if item.id in pinned_ids:
            pinned |= 1 << item.cart_bit
        if item.excluded:
            excluded |= 1 << item.cart_bit

    if pinned & excluded:
        return OptimisationResult(
            wardrobe_cluster_count=0,
            clusters=[],
            outfits=[],
            edges=[],
            standalone=[],
            exact=MethodResult("exact", [], 0, 0, 0, 0, {"infeasible": True}),
            greedy=MethodResult("greedy_marginal", [], 0, 0, 0, 0, {"infeasible": True}),
            cheapest=MethodResult("cheapest_first", [], 0, 0, 0, 0, {"infeasible": True}),
            standalone_rank=MethodResult("standalone_yield", [], 0, 0, 0, 0, {"infeasible": True}),
            frontier=[],
            synergy=[],
            comparison=[],
            rejected_infeasible="A pinned item is also excluded.",
        )

    if _cost(indexed, pinned) > budget_minor:
        return OptimisationResult(
            wardrobe_cluster_count=0,
            clusters=[],
            outfits=[],
            edges=[],
            standalone=[],
            exact=MethodResult("exact", [], 0, 0, 0, 0, {"infeasible": True}),
            greedy=MethodResult("greedy_marginal", [], 0, 0, 0, 0, {"infeasible": True}),
            cheapest=MethodResult("cheapest_first", [], 0, 0, 0, 0, {"infeasible": True}),
            standalone_rank=MethodResult("standalone_yield", [], 0, 0, 0, 0, {"infeasible": True}),
            frontier=[],
            synergy=[],
            comparison=[],
            rejected_infeasible="Pinned items exceed the selected budget. Shipping and tax are excluded unless supplied.",
        )

    outfits = generate_outfits(wardrobe, indexed, occasion, footwear_required, rejected_combination_ids)
    clusters = _cluster_views(outfits)
    wardrobe_count = sum(1 for cluster in clusters if cluster.wardrobe_unlocked)
    exact, frontier = _enumerate_exact(indexed, clusters, pinned, excluded, budget_minor, max_items)
    greedy = _greedy_marginal(indexed, clusters, pinned, excluded, budget_minor, max_items)
    cheapest = _cheapest_first(indexed, clusters, pinned, excluded, budget_minor, max_items)
    standalone_rank = _standalone_rank(indexed, clusters, pinned, excluded, budget_minor, max_items)

    standalone = []
    for item in indexed:
        if item.cart_bit is None:
            continue
        bit = 1 << item.cart_bit
        value = _objective(clusters, pinned | bit)
        basket_conditional = 0
        if exact.bits & bit:
            without = exact.bits & ~bit
            if pinned & bit:
                basket_conditional = exact.objective_value
            else:
                basket_conditional = exact.objective_value - _objective(clusters, without | pinned)
        standalone.append(
            {
                "product_id": item.id,
                "name": item.display_name,
                "price_minor": item.price_minor,
                "standalone_f": value,
                "basket_conditional_f": basket_conditional,
                "in_exact_basket": bool(exact.bits & bit),
                "note": "Standalone f({x}) and basket-conditional contribution are labelled separately; overlapping yields are not additive.",
            }
        )

    comparison = [_gap(exact, exact), _gap(greedy, exact), _gap(cheapest, exact), _gap(standalone_rank, exact)]
    return OptimisationResult(
        wardrobe_cluster_count=wardrobe_count,
        clusters=clusters,
        outfits=outfits,
        edges=pairwise_edges(outfits),
        standalone=standalone,
        exact=exact,
        greedy=greedy,
        cheapest=cheapest,
        standalone_rank=standalone_rank,
        frontier=frontier,
        synergy=_synergy(indexed, clusters, pinned),
        comparison=comparison,
        rejected_infeasible=None,
    )


def result_to_dict(result: OptimisationResult) -> dict[str, Any]:
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "wardrobe_cluster_count": result.wardrobe_cluster_count,
        "rejected_infeasible": result.rejected_infeasible,
        "disclaimer": (
            "Values are rule-qualified outfit options under declared compatibility rules. "
            "Exact search is exact under those rules, not objective fashion truth. "
            "Algorithm superiority under this objective is not proof of user usefulness."
        ),
        "clusters": [
            {
                "cluster_id": cluster.cluster_id,
                "signature": cluster.signature,
                "member_combination_ids": cluster.member_combination_ids,
                "wardrobe_unlocked": cluster.wardrobe_unlocked,
                "unlock_masks": cluster.unlock_masks,
            }
            for cluster in result.clusters
        ],
        "outfits": [outfit.to_dict() for outfit in result.outfits],
        "edges": result.edges,
        "standalone": result.standalone,
        "exact": result.exact.__dict__,
        "greedy_marginal": result.greedy.__dict__,
        "cheapest_first": result.cheapest.__dict__,
        "standalone_yield": result.standalone_rank.__dict__,
        "frontier": result.frontier,
        "synergy": result.synergy,
        "comparison": result.comparison,
    }
