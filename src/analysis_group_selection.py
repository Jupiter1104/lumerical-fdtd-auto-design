# src/analysis_group_selection.py
from __future__ import annotations

import re

MATCH_POLICY_VERSION = "1.0"
SHORTLIST_THRESHOLD = 0.35
AUTO_SELECT_THRESHOLD = 0.85
AUTO_SELECT_GAP = 0.15

VALID_INTENTS = {
    "transmission",
    "net_power_flow",
    "absorption",
    "far_field",
    "polarization",
    "mode_area",
    "modal_volume",
    "movie",
    "unknown",
}

INTENT_TOKENS = {
    "transmission": {"transmission", "power", "box"},
    "net_power_flow": {"power", "flow", "transmission", "box"},
    "absorption": {"absorption", "absorbed", "power"},
    "far_field": {"farfield", "far", "field", "projection", "directivity"},
    "polarization": {"polarization", "ellipse", "farfield"},
    "mode_area": {"mode", "area", "effective"},
    "modal_volume": {"modal", "mode", "volume", "cavity"},
    "movie": {"movie", "cw"},
    "unknown": set(),
}

# Core token groups for shortlist matching.
# Each intent maps to a list of token *sets*.  A script_id enters the
# shortlist (score 0.45) when its tokens contain ALL tokens of ANY set.
# This avoids penalising candidates when only a subset of the legacy
# synonym tokens appear (e.g. "farfield" alone must be enough for
# far_field without also matching "far", "field", "directivity").
CORE_TOKEN_GROUPS: dict[str, list[set[str]]] = {
    "transmission": [{"transmission"}],
    "net_power_flow": [{"power", "flow"}],
    "absorption": [{"absorption"}],
    "far_field": [{"farfield"}, {"far", "field"}],
    "polarization": [{"polarization"}],
    "mode_area": [{"mode", "area"}],
    "modal_volume": [{"modal", "volume"}],
    "movie": [{"movie"}],
    "unknown": [],
}

OUTPUT_INTENTS = {
    "t": "transmission",
    "transmission": "transmission",
    "net_power_flow": "net_power_flow",
    "power_flow": "net_power_flow",
    "absorbed_power": "absorption",
    "absorption": "absorption",
    "directivity": "far_field",
    "far_field": "far_field",
    "farfield": "far_field",
    "polarization_ellipse": "polarization",
    "polarization": "polarization",
    "effective_mode_area": "mode_area",
    "mode_area": "mode_area",
    "modal_volume": "modal_volume",
    "cw_movie": "movie",
    "movie": "movie",
}


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", str(value).lower())
        if token
    }


def resolve_analysis_intent(
    explicit: dict | None,
    recipe_context: dict | None,
) -> dict:
    context = recipe_context or {}
    if explicit:
        raw_kind = str(explicit.get("kind", "unknown"))
        kind = raw_kind if raw_kind in VALID_INTENTS else "unknown"
        return {
            **explicit,
            "kind": kind,
            "raw_kind": raw_kind,
            "outputs": list(explicit.get("outputs", [])),
            "source": "explicit",
            "evidence": [f"explicit:{raw_kind}"],
        }

    outputs = [str(item) for item in context.get("outputs", [])]
    monitor_types = {
        str(item.get("type", item.get("monitor_type", ""))).lower()
        for item in context.get("monitors", [])
        if isinstance(item, dict)
    }
    fom_result = str((context.get("fom") or {}).get("result", ""))
    evidence = []
    normalized_outputs = [
        re.sub(r"[^a-z0-9]+", "_", item.lower()).strip("_")
        for item in [*outputs, fom_result]
        if item
    ]
    derived_kinds = {
        OUTPUT_INTENTS[item]
        for item in normalized_outputs
        if item in OUTPUT_INTENTS
    }
    if len(derived_kinds) == 1:
        kind = next(iter(derived_kinds))
        # Use original item names for evidence, not normalized versions
        for orig_item in [*outputs, fom_result]:
            if not orig_item:
                continue
            norm = re.sub(r"[^a-z0-9]+", "_", orig_item.lower()).strip("_")
            if OUTPUT_INTENTS.get(norm) == kind:
                evidence.append(f"output:{orig_item}")
        if kind == "transmission" and any("power" in item for item in monitor_types):
            evidence.append("monitor:power")
        return {
            "kind": kind,
            "outputs": outputs,
            "source": "derived",
            "evidence": evidence,
        }
    if ("T" in outputs or fom_result == "T") and not derived_kinds:
        evidence.append("output:T")
        if any("power" in item for item in monitor_types):
            evidence.append("monitor:power")
        return {
            "kind": "transmission",
            "outputs": outputs or ["T"],
            "source": "derived",
            "evidence": evidence,
        }
    return {
        "kind": "unknown",
        "outputs": outputs,
        "source": "derived",
        "evidence": [],
    }


def _base_score(script_id: str, intent: dict) -> tuple[float, list[str]]:
    groups = CORE_TOKEN_GROUPS.get(intent["kind"], [])
    if not groups:
        return 0.0, []
    actual = _tokens(script_id)
    # Any core-token group fully contained in the script_id tokens gives the
    # full shortlist score.  Supporting tokens (from INTENT_TOKENS) are still
    # collected as match reasons for transparency but do not affect scoring.
    for group in groups:
        if group.issubset(actual):
            return 0.45, [f"id_token:{t}" for t in sorted(group)]
    # No core group matched — still collect supporting reasons for diagnostics.
    wanted = INTENT_TOKENS.get(intent["kind"], set())
    overlap = wanted & actual
    if overlap:
        return 0.0, [f"id_token:{t}" for t in sorted(overlap)]
    return 0.0, []


def shortlist_candidates(
    catalog: dict,
    intent: dict,
    context: dict,
    limit: int = 3,
) -> list[dict]:
    candidates = []
    probes = catalog.get("probes", {})
    for script_id in catalog.get("script_ids", []):
        probe = probes.get(script_id)
        if probe and probe.get("status") == "not_analysis_group":
            continue
        score, reasons = _base_score(script_id, intent)
        if score >= SHORTLIST_THRESHOLD:
            candidates.append({
                "script_id": script_id,
                "score": score,
                "match_reasons": reasons,
                "probe": probe,
            })
    return sorted(
        candidates,
        key=lambda item: (-item["score"], item["script_id"].lower()),
    )[:limit]


def rank_probed_candidates(
    candidates: list[dict],
    intent: dict,
    context: dict,
) -> list[dict]:
    requested_outputs = {str(item) for item in intent.get("outputs", [])}
    fom_result = str((context.get("fom") or {}).get("result", ""))
    has_power_monitor = any(
        "power" in str(item.get("type", item.get("monitor_type", ""))).lower()
        for item in context.get("monitors", [])
        if isinstance(item, dict)
    )
    ranked = []
    for candidate in candidates:
        probe = candidate.get("probe") or {}
        if probe.get("status") != "verified_analysis_group":
            continue
        score, reasons = _base_score(candidate["script_id"], intent)
        result_names = {
            str(item.get("name"))
            for item in probe.get("analysis_results", [])
        }
        property_names = {
            str(item.get("name")).lower()
            for key in ("setup_properties", "analysis_properties")
            for item in probe.get(key, [])
        }
        if requested_outputs & result_names:
            score += 0.25
            reasons.append("result:" + sorted(requested_outputs & result_names)[0])
        intent_tokens = INTENT_TOKENS[intent["kind"]]
        if any(_tokens(name) & intent_tokens for name in property_names):
            score += 0.15
            reasons.append("parameter:intent_match")
        if has_power_monitor and intent["kind"] in {"transmission", "net_power_flow"}:
            score += 0.10
            reasons.append("monitor:power")
        if fom_result and fom_result in result_names:
            score += 0.05
            reasons.append(f"fom:{fom_result}")
        ranked.append({
            **candidate,
            "score": round(min(score, 1.0), 12),
            "match_reasons": reasons,
        })
    return sorted(
        ranked,
        key=lambda item: (-item["score"], item["script_id"].lower()),
    )


def choose_high_confidence(ranked: list[dict]) -> dict | None:
    if not ranked or ranked[0]["score"] < AUTO_SELECT_THRESHOLD:
        return None
    if len(ranked) > 1 and ranked[0]["score"] - ranked[1]["score"] < AUTO_SELECT_GAP:
        return None
    return ranked[0]


class AnalysisSelectionError(Exception):
    def __init__(
        self,
        error_type: str,
        message: str,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.details = details or {}


TYPE_NAMES = {
    0: "number",
    1: "string",
    2: "length",
    3: "time",
    4: "frequency",
    5: "material",
    6: "matrix",
}

PROPERTY_ALIASES = {
    "x span": ("x span", "x_span"),
    "y span": ("y span", "y_span"),
    "z span": ("z span", "z_span"),
    "wavelength start": ("wavelength start", "wavelength_start"),
    "wavelength stop": ("wavelength stop", "wavelength_stop"),
}


def normalize_property_type(type_code: int) -> str:
    return TYPE_NAMES.get(type_code, "unknown")


def _compatible(type_name: str, value) -> bool:
    if type_name in {"number", "length", "time", "frequency"}:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name in {"string", "material"}:
        return isinstance(value, str)
    if type_name == "matrix":
        return isinstance(value, list)
    return True


def _context_value(name: str, context: dict):
    aliases = PROPERTY_ALIASES.get(name, (name, name.replace(" ", "_")))
    containers = [
        context.get("explicit_properties", {}),
        context.get("solver", {}),
    ]
    for container in containers:
        for alias in aliases:
            if alias in container:
                return container[alias], "recipe_context"

    matching = []
    for section in ("monitors", "sources"):
        for item in context.get(section, []):
            props = item.get("properties", {}) if isinstance(item, dict) else {}
            for alias in aliases:
                if alias in props:
                    matching.append(props[alias])
    if len(matching) == 1:
        return matching[0], "recipe_context"
    return None, None


def resolve_analysis_parameters(
    probe: dict,
    overrides: dict,
    recipe_context: dict,
) -> dict:
    schema = {
        item["name"]: item
        for key in ("setup_properties", "analysis_properties")
        for item in probe.get(key, [])
    }
    unknown = sorted(set(overrides) - set(schema))
    if unknown:
        raise AnalysisSelectionError(
            "analysis_parameter_unknown",
            "parameter_overrides contains unknown analysis parameters.",
            {"parameters": unknown},
        )

    applied = {}
    defaults = {}
    unresolved = []
    sources = {}
    for name, item in schema.items():
        type_name = normalize_property_type(item.get("type_code", -1))
        if name in overrides:
            value = overrides[name]
            source = "parameter_overrides"
        else:
            value, source = _context_value(name, recipe_context)
        if source:
            if not _compatible(type_name, value):
                raise AnalysisSelectionError(
                    "analysis_parameter_type_mismatch",
                    f"Parameter {name!r} is incompatible with {type_name}.",
                    {"parameter": name, "type": type_name},
                )
            applied[name] = value
            sources[name] = source
        elif item.get("default_readable"):
            defaults[name] = item.get("default_value")
        else:
            unresolved.append({
                "name": name,
                "type": type_name,
                "reason": "no_unique_source_and_default_unreadable",
            })
    return {
        "applied": applied,
        "defaults_preserved": defaults,
        "unresolved": unresolved,
        "sources": sources,
    }
