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


# ═══════════════════════════════════════════════════════════════════════════
# Shortlist coverage for all 8 supported intents (P1 fix)
# ═══════════════════════════════════════════════════════════════════════════

# Typical Object Library IDs that SHOULD match each intent.
# These are illustrative names — the real v242 catalog is the authority.
TYPICAL_IDS = [
    "power_transmission_box",
    "net_power_flow_box",
    "absorption_monitor",
    "farfield_projection_box",
    "polarization_ellipse_box",
    "effective_mode_area_box",
    "modal_volume_box",
    "cw_movie_box",
]

# A known non-analysis-group ID that must NOT match any intent.
NEGATIVE_ID = "rounded_cylinder"


@pytest.mark.parametrize(
    ("script_id", "intent_kind"),
    [
        ("power_transmission_box", "transmission"),
        ("net_power_flow_box", "net_power_flow"),
        ("absorption_monitor", "absorption"),
        ("farfield_projection_box", "far_field"),
        ("polarization_ellipse_box", "polarization"),
        ("effective_mode_area_box", "mode_area"),
        ("modal_volume_box", "modal_volume"),
        ("cw_movie_box", "movie"),
    ],
)
def test_typical_id_enters_shortlist_for_its_intent(script_id, intent_kind):
    """Every supported intent must be able to shortlist at least one typical ID."""
    catalog = {
        "script_ids": TYPICAL_IDS + [NEGATIVE_ID],
        "probes": {},
    }
    intent = {"kind": intent_kind, "outputs": []}
    result = shortlist_candidates(catalog, intent, {}, limit=3)
    matching = [item["script_id"] for item in result]
    assert script_id in matching, (
        f"{script_id!r} must enter the shortlist for intent {intent_kind!r}. "
        f"Shortlist returned: {matching}"
    )
    assert all(item["score"] >= 0.35 for item in result), (
        f"All shortlist entries must meet or exceed 0.35. "
        f"Scores: {[(r['script_id'], r['score']) for r in result]}"
    )


def test_shortlist_is_deterministic_for_all_intents():
    """Shortlist must be deterministic across calls for all intents."""
    catalog = {"script_ids": TYPICAL_IDS, "probes": {}}
    for intent_kind in [
        "transmission", "net_power_flow", "absorption", "far_field",
        "polarization", "mode_area", "modal_volume", "movie",
    ]:
        intent = {"kind": intent_kind, "outputs": []}
        first = shortlist_candidates(catalog, intent, {}, limit=3)
        second = shortlist_candidates(catalog, intent, {}, limit=3)
        assert first == second, f"Shortlist not deterministic for {intent_kind}"


def test_negative_id_never_enters_shortlist():
    """rounded_cylinder must not match any analysis intent."""
    catalog = {"script_ids": [NEGATIVE_ID, "power_transmission_box"], "probes": {}}
    for intent_kind in [
        "transmission", "net_power_flow", "absorption", "far_field",
        "polarization", "mode_area", "modal_volume", "movie",
    ]:
        intent = {"kind": intent_kind, "outputs": []}
        result = shortlist_candidates(catalog, intent, {}, limit=3)
        matching = [item["script_id"] for item in result]
        assert NEGATIVE_ID not in matching, (
            f"{NEGATIVE_ID!r} must NOT match intent {intent_kind!r}"
        )


def test_farfield_with_underscore_form_also_enters_shortlist():
    """far_field_projection (underscore form) must also shortlist for far_field."""
    catalog = {
        "script_ids": ["far_field_projection_box", NEGATIVE_ID],
        "probes": {},
    }
    intent = {"kind": "far_field", "outputs": []}
    result = shortlist_candidates(catalog, intent, {}, limit=3)
    assert result[0]["script_id"] == "far_field_projection_box"


from src.analysis_group_selection import (
    AnalysisSelectionError,
    resolve_analysis_parameters,
)


PROBE = {
    "setup_properties": [
        {"name": "x span", "type_code": 2, "default_value": 2e-6, "default_readable": True},
        {"name": "material", "type_code": 5, "default_value": "Si", "default_readable": True},
    ],
    "analysis_properties": [
        {"name": "make plots", "type_code": 0, "default_value": 1, "default_readable": True},
    ],
}


def test_override_beats_context_and_default():
    result = resolve_analysis_parameters(
        PROBE,
        {"x span": 4e-6},
        {"solver": {"x span": 3e-6}},
    )
    assert result["applied"]["x span"] == 4e-6
    assert result["sources"]["x span"] == "parameter_overrides"


def test_solver_span_is_used_when_unique_and_override_absent():
    result = resolve_analysis_parameters(
        PROBE,
        {},
        {"solver": {"x span": 3e-6}},
    )
    assert result["applied"]["x span"] == 3e-6
    assert result["defaults_preserved"]["material"] == "Si"


def test_unknown_override_is_rejected():
    with pytest.raises(AnalysisSelectionError) as exc:
        resolve_analysis_parameters(PROBE, {"not real": 1}, {})
    assert exc.value.error_type == "analysis_parameter_unknown"


def test_type_mismatch_is_rejected():
    with pytest.raises(AnalysisSelectionError) as exc:
        resolve_analysis_parameters(PROBE, {"x span": "wide"}, {})
    assert exc.value.error_type == "analysis_parameter_type_mismatch"
