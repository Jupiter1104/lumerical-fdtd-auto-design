# tests/test_analysis_group_selection.py
import pytest

from src.analysis_group_selection import (
    choose_high_confidence,
    rank_probed_candidates,
    resolve_analysis_intent,
    shortlist_candidates,
)


def test_explicit_intent_wins_over_context():
    result = resolve_analysis_intent(
        {"kind": "far_field", "outputs": ["directivity"]},
        {"outputs": ["T"], "monitors": [{"type": "power_monitor"}]},
    )
    assert result["kind"] == "far_field"
    assert result["source"] == "explicit"


def test_context_infers_transmission_from_output_and_power_monitor():
    result = resolve_analysis_intent(
        None,
        {
            "outputs": ["T"],
            "fom": {"result": "T"},
            "monitors": [{"type": "power_monitor", "name": "mon"}],
        },
    )
    assert result["kind"] == "transmission"
    assert result["source"] == "derived"
    assert "output:T" in result["evidence"]


def test_ambiguous_context_stays_unknown():
    result = resolve_analysis_intent(None, {"outputs": [], "monitors": []})
    assert result["kind"] == "unknown"


@pytest.mark.parametrize(
    ("output", "kind"),
    [
        ("absorbed_power", "absorption"),
        ("directivity", "far_field"),
        ("polarization_ellipse", "polarization"),
        ("effective_mode_area", "mode_area"),
        ("modal_volume", "modal_volume"),
        ("cw_movie", "movie"),
        ("net_power_flow", "net_power_flow"),
    ],
)
def test_context_derives_supported_intents_from_structured_outputs(output, kind):
    result = resolve_analysis_intent(
        None,
        {"outputs": [output], "fom": {"result": output}, "monitors": []},
    )
    assert result["kind"] == kind
    assert result["source"] == "derived"


def test_shortlist_uses_real_ids_and_is_deterministic():
    catalog = {
        "script_ids": [
            "farfield_projection_box",
            "power_transmission_box",
            "rounded_cylinder",
        ],
        "probes": {},
    }
    intent = {"kind": "transmission", "outputs": ["T"]}
    first = shortlist_candidates(catalog, intent, {}, limit=3)
    second = shortlist_candidates(catalog, intent, {}, limit=3)
    assert first == second
    assert [item["script_id"] for item in first] == ["power_transmission_box"]


def test_probe_evidence_reaches_high_confidence_gate():
    candidates = [{
        "script_id": "power_transmission_box",
        "probe": {
            "status": "verified_analysis_group",
            "setup_properties": [{"name": "x span", "type_code": 2}],
            "analysis_properties": [],
            "analysis_results": [{"name": "T", "type_code": 0}],
        },
    }]
    ranked = rank_probed_candidates(
        candidates,
        {"kind": "transmission", "outputs": ["T"]},
        {
            "monitors": [{"type": "power_monitor"}],
            "fom": {"result": "T"},
        },
    )
    assert ranked[0]["score"] == 0.85
    assert choose_high_confidence(ranked)["script_id"] == "power_transmission_box"


def test_small_gap_does_not_auto_select():
    assert choose_high_confidence([
        {"script_id": "a", "score": 0.90},
        {"script_id": "b", "score": 0.80},
    ]) is None
