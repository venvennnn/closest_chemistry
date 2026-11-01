from app.models import Analysis, Garment, Workspace
from app.services.analysis import run_analysis
from app.services.compatibility import Item
from app.services.optimizer import optimise, result_to_dict


def test_analysis_result_roundtrip(session):
    workspace = Workspace(owner_id="owner-a")
    session.add(workspace)
    session.flush()
    for ident, category, family in (("t1", "top", "white"), ("b1", "bottom", "navy")):
        session.add(
            Garment(
                owner_id="owner-a",
                workspace_id=workspace.id,
                canonical_key=ident,
                display_name=ident,
                category=category,
                subtype="basic",
                colour=family,
                colour_family=family,
                pattern="solid",
                pattern_family="solid",
                formality_min=30,
                formality_max=70,
                status="confirmed",
                needs_review=False,
                analysis_eligible=True,
                source_kind="wardrobe",
            )
        )
    analysis = Analysis(
        owner_id="owner-a",
        workspace_id=workspace.id,
        occasion="any",
        budget_minor=10000,
        currency="USD",
        status="queued",
    )
    session.add(analysis)
    session.commit()
    payload = run_analysis(session, analysis)
    stored = session.get(Analysis, analysis.id)
    assert stored.status in {"succeeded", "failed"}
    assert stored.input_snapshot_hash
    assert stored.result == payload
    assert "frontier" in payload
    assert "comparison" in payload
    assert payload["algorithm_version"] == stored.algorithm_version


def test_duplicate_combination_ids_are_stable():
    wardrobe = [
        Item(
            id="same-top",
            category="top",
            subtype="tee",
            colour="white",
            colour_family="white",
            pattern="solid",
            pattern_family="solid",
            formality_min=20,
            formality_max=50,
            source="wardrobe",
            display_name="tee",
            analysis_eligible=True,
        ),
        Item(
            id="same-bottom",
            category="bottom",
            subtype="jean",
            colour="navy",
            colour_family="navy",
            pattern="solid",
            pattern_family="solid",
            formality_min=20,
            formality_max=50,
            source="wardrobe",
            display_name="jean",
            analysis_eligible=True,
        ),
    ]
    first = result_to_dict(optimise(wardrobe, [], "any", 0, False))
    second = result_to_dict(optimise(wardrobe, [], "any", 0, False))
    ids = [row["combination_id"] for row in first["outfits"]]
    assert ids == [row["combination_id"] for row in second["outfits"]]
    assert len(ids) == len(set(ids))
