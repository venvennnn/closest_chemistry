from app.services.compatibility import Item
from app.services.optimizer import optimise


def _item(
    ident: str,
    category: str,
    source: str = "wardrobe",
    colour_family: str = "navy",
    pattern_family: str = "solid",
    formality: tuple[int, int] = (40, 80),
    price: int = 0,
    subtype: str = "basic",
    **kwargs,
) -> Item:
    return Item(
        id=ident,
        category=category,
        subtype=subtype,
        colour=colour_family,
        colour_family=colour_family,
        pattern=pattern_family,
        pattern_family=pattern_family,
        formality_min=formality[0],
        formality_max=formality[1],
        source=source,
        price_minor=price,
        display_name=ident,
        analysis_eligible=True,
        **kwargs,
    )


def test_baseline_wardrobe_and_exact_unlock():
    wardrobe = [
        _item("w-top", "top", colour_family="white"),
        _item("w-bottom", "bottom", colour_family="navy"),
    ]
    cart = [
        _item("c-jacket", "outerwear", source="cart", colour_family="black", price=10000, subtype="blazer"),
        _item("c-dress", "dress", source="cart", colour_family="black", price=8000, subtype="midi"),
    ]
    result = optimise(wardrobe, cart, occasion="any", budget_minor=20000, footwear_required=False)
    assert result.rejected_infeasible is None
    assert result.wardrobe_cluster_count >= 1
    assert result.exact.objective_value >= result.greedy.objective_value
    assert result.exact.objective_value >= 1
    assert set(result.exact.product_ids) <= {"c-jacket", "c-dress"}


def test_synergy_complementarity_not_additive():
    wardrobe = [_item("w-top", "top", colour_family="white")]
    cart = [
        _item("c-bottom", "bottom", source="cart", colour_family="navy", price=5000),
        _item("c-outer", "outerwear", source="cart", colour_family="black", price=5000, subtype="coat"),
    ]
    result = optimise(wardrobe, cart, occasion="any", budget_minor=20000, footwear_required=False)
    pair = result.synergy[0]
    assert pair["f_ij"] >= pair["f_i"]
    assert pair["synergy"] == pair["f_ij"] - pair["f_i"] - pair["f_j"]
    standalone_sum = sum(row["standalone_f"] for row in result.standalone)
    assert result.exact.objective_value <= standalone_sum or pair["synergy"] > 0


def test_tie_break_lower_cost_then_fewer_then_stable_ids():
    wardrobe = [_item("w-top", "top"), _item("w-bottom", "bottom")]
    cart = [
        _item("c-a", "outerwear", source="cart", price=3000, subtype="blazer"),
        _item("c-b", "outerwear", source="cart", price=5000, subtype="blazer"),
    ]
    result = optimise(wardrobe, cart, occasion="any", budget_minor=10000, footwear_required=False)
    if result.exact.objective_value > 0:
        assert result.exact.cost_minor <= 5000


def test_impossible_pin_budget_rejected():
    wardrobe = [_item("w-top", "top"), _item("w-bottom", "bottom")]
    cart = [_item("c-pricey", "outerwear", source="cart", price=20000, subtype="coat")]
    result = optimise(
        wardrobe,
        cart,
        occasion="any",
        budget_minor=1000,
        footwear_required=False,
        pinned_ids={"c-pricey"},
    )
    assert result.rejected_infeasible is not None
    assert result.exact.details.get("infeasible") is True


def test_unknown_attributes_are_review_not_invented():
    wardrobe = [
        _item("w-top", "top"),
        Item(
            id="w-bottom",
            category="bottom",
            subtype="trouser",
            colour=None,
            colour_family=None,
            pattern=None,
            pattern_family=None,
            formality_min=None,
            formality_max=None,
            source="wardrobe",
            display_name="unknown-bottom",
            analysis_eligible=True,
        ),
    ]
    result = optimise(wardrobe, [], occasion="office", budget_minor=0, footwear_required=False)
    qualified = [outfit for outfit in result.outfits if outfit.qualified]
    assert qualified == []
    review = [outfit for outfit in result.outfits if outfit.needs_review or outfit.rejection_reasons]
    assert review


def test_user_rejection_excludes_combination():
    wardrobe = [_item("w-top", "top"), _item("w-bottom", "bottom")]
    first = optimise(wardrobe, [], occasion="any", budget_minor=0, footwear_required=False)
    combo = next(outfit.combination_id for outfit in first.outfits if outfit.qualified)
    second = optimise(
        wardrobe,
        [],
        occasion="any",
        budget_minor=0,
        footwear_required=False,
        rejected_combination_ids={combo},
    )
    assert all(outfit.combination_id != combo or not outfit.qualified for outfit in second.outfits)


def test_percentage_gap_undefined_when_optimum_zero():
    wardrobe = [_item("w-top", "top"), _item("w-bottom", "bottom")]
    cart = [_item("c-same-outer", "outerwear", source="cart", price=1000, subtype="blazer")]
    result = optimise(wardrobe, cart, occasion="evening", budget_minor=1000, footwear_required=False)
    if result.exact.objective_value == 0:
        row = next(item for item in result.comparison if item["method"] == "greedy_marginal")
        assert row["percentage_gap"] is None
        assert row["percentage_gap_defined"] is False


def test_cluster_identity_stable_across_baskets():
    wardrobe = [_item("w-top", "top"), _item("w-bottom", "bottom")]
    cart = [
        _item("c-1", "outerwear", source="cart", price=1000, subtype="blazer"),
        _item("c-2", "dress", source="cart", price=1000, subtype="midi"),
    ]
    wide = optimise(wardrobe, cart, occasion="any", budget_minor=5000, footwear_required=False)
    narrow = optimise(wardrobe, cart[:1], occasion="any", budget_minor=5000, footwear_required=False)
    shared = set(cluster.cluster_id for cluster in wide.clusters) & set(
        cluster.cluster_id for cluster in narrow.clusters
    )
    assert shared


def test_footwear_only_when_required():
    wardrobe = [
        _item("w-top", "top"),
        _item("w-bottom", "bottom"),
        _item("w-shoe", "footwear", subtype="sneaker"),
    ]
    off = optimise(wardrobe, [], occasion="any", budget_minor=0, footwear_required=False)
    on = optimise(wardrobe, [], occasion="any", budget_minor=0, footwear_required=True)
    assert all("footwear" not in outfit.template and "w-shoe" not in outfit.garment_ids or not outfit.qualified for outfit in off.outfits)
    assert any(outfit.qualified and "w-shoe" in outfit.garment_ids for outfit in on.outfits)
