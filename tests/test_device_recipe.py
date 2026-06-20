"""Tests for device recipe validation, expression parsing, and compilation.

Covers:
- Recipe validation with required/unrequired params, assumptions
- Expression parser (safe, restricted AST)
- Recipe compiler with fingerprinting and script generation
- Edge cases: division by zero, Python injection, non-finite values
"""

import pytest

from src.device_recipe import (
    ExpressionError,
    compile_recipe,
    evaluate_expression,
    parse_expression,
    validate_recipe,
)


# ═══════════════════════════════════════════════════════════════════
# Shared test fixtures
# ═══════════════════════════════════════════════════════════════════

MINIMAL_RECIPE = {
    "schema_version": "1.0",
    "parameters": {
        "pillar_radius": {
            "type": "float",
            "default": 100e-9,
            "min": 50e-9,
            "max": 200e-9,
            "unit": "m",
            "source_ref": {"locator": "model::pillar_radius"},
        }
    },
    "assumptions": [
        {"parameter": "pillar_radius", "reason": "Typical value for NIR metasurface"}
    ],
    "materials": [
        {"name": "SiO2", "type": "dielectric", "properties": {"index": 1.45}}
    ],
    "geometry": [
        {
            "type": "rectangle",
            "name": "pillar",
            "properties": {"x_span": "${pillar_radius} * 2"},
        }
    ],
}


# ═══════════════════════════════════════════════════════════════════
# 1. Validation tests
# ═══════════════════════════════════════════════════════════════════


def test_validate_minimal_recipe_passes():
    """A minimal valid recipe passes validation with ok=True and no errors."""
    result = validate_recipe(MINIMAL_RECIPE)
    assert result["ok"] is True
    assert result["errors"] == []


def test_missing_schema_version_fails():
    """Recipe without schema_version returns an error."""
    recipe = {k: v for k, v in MINIMAL_RECIPE.items() if k != "schema_version"}
    result = validate_recipe(recipe)
    assert result["ok"] is False
    assert any(
        e["code"] == "invalid_schema_version" for e in result["errors"]
    )


def test_wrong_schema_version_fails():
    """Recipe with wrong schema_version returns an error."""
    recipe = {**MINIMAL_RECIPE, "schema_version": "0.5"}
    result = validate_recipe(recipe)
    assert result["ok"] is False
    assert any(
        e["code"] == "invalid_schema_version" for e in result["errors"]
    )


def test_required_param_without_source_ref_fails():
    """A required parameter (no default) without source_ref.locator fails."""
    recipe = {
        "schema_version": "1.0",
        "parameters": {
            "pillar_radius": {
                "type": "float",
                "min": 50e-9,
                "max": 200e-9,
                "unit": "m",
                # No default → required
                # No source_ref → should fail
            }
        },
        "assumptions": [],
        "materials": [
            {"name": "SiO2", "type": "dielectric", "properties": {"index": 1.45}}
        ],
        "geometry": [
            {
                "type": "rectangle",
                "name": "pillar",
                "properties": {"x_span": "100e-9"},
            }
        ],
    }
    result = validate_recipe(recipe)
    assert result["ok"] is False
    assert any(
        e["code"] == "missing_required_source_ref" for e in result["errors"]
    )


def test_required_param_with_source_ref_passes():
    """A required parameter (no default) with source_ref.locator passes."""
    recipe = {
        "schema_version": "1.0",
        "parameters": {
            "pillar_radius": {
                "type": "float",
                "min": 50e-9,
                "max": 200e-9,
                "source_ref": {"locator": "model::pillar_radius"},
            }
        },
        "assumptions": [],
        "materials": [
            {"name": "SiO2", "type": "dielectric", "properties": {"index": 1.45}}
        ],
        "geometry": [
            {
                "type": "rectangle",
                "name": "pillar",
                "properties": {"x_span": "100e-9"},
            }
        ],
    }
    result = validate_recipe(recipe)
    assert result["ok"] is True


def test_non_critical_default_without_reason_fails():
    """Non-critical default without assumption.reason fails with missing_assumption."""
    recipe = {
        "schema_version": "1.0",
        "parameters": {
            "pillar_radius": {
                "type": "float",
                "default": 100e-9,
                "min": 50e-9,
                "max": 200e-9,
                "unit": "m",
                "source_ref": {"locator": "model::pillar_radius"},
            }
        },
        "assumptions": [
            {"parameter": "pillar_radius"}  # Missing "reason"
        ],
        "materials": [
            {"name": "SiO2", "type": "dielectric", "properties": {"index": 1.45}}
        ],
        "geometry": [
            {
                "type": "rectangle",
                "name": "pillar",
                "properties": {"x_span": "${pillar_radius} * 2"},
            }
        ],
    }
    result = validate_recipe(recipe)
    assert result["ok"] is False
    assert any(
        e["code"] == "missing_assumption" for e in result["errors"]
    )


def test_non_critical_default_with_reason_passes():
    """Non-critical default with proper assumption.reason passes."""
    # MINIMAL_RECIPE already has this — it should pass
    result = validate_recipe(MINIMAL_RECIPE)
    assert result["ok"] is True


def test_missing_parameters_fails():
    """Recipe with no parameters fails."""
    recipe = {**MINIMAL_RECIPE, "parameters": {}}
    result = validate_recipe(recipe)
    assert result["ok"] is False
    assert any(
        e["code"] == "missing_parameters" for e in result["errors"]
    )


# ═══════════════════════════════════════════════════════════════════
# 2. Expression parser tests
# ═══════════════════════════════════════════════════════════════════


def test_expression_resolves():
    """Expression ${a} * 2 + ${b} with a=3, b=1 resolves to 7.0."""
    ast = parse_expression("${a} * 2 + ${b}")
    result = evaluate_expression(ast, {"a": 3, "b": 1})
    assert result == 7.0


def test_simple_expression_pillar_radius():
    """Expression ${pillar_radius} * 2 resolves correctly."""
    ast = parse_expression("${pillar_radius} * 2")
    result = evaluate_expression(ast, {"pillar_radius": 100e-9})
    assert result == 200e-9


def test_python_expression_rejected():
    """Python-like __import__('os') is rejected with invalid_expression."""
    with pytest.raises(ExpressionError) as exc_info:
        parse_expression('__import__("os")')
    assert exc_info.value.code == "invalid_expression"


def test_python_builtins_rejected():
    """Python builtins like eval, exec are rejected."""
    for expr in ["eval('1+1')", "exec('x=1')", "open('/etc/passwd')",
                 "__builtins__", "getattr(obj, 'attr')"]:
        with pytest.raises(ExpressionError) as exc_info:
            parse_expression(expr)
        assert exc_info.value.code == "invalid_expression"


def test_division_by_literal_zero_rejected():
    """Division by literal zero is rejected at evaluation time."""
    ast = parse_expression("1 / 0")
    with pytest.raises(ExpressionError) as exc_info:
        evaluate_expression(ast, {})
    assert exc_info.value.code == "division_by_zero"


def test_undeclared_parameter_rejected():
    """Reference to undeclared parameter fails."""
    ast = parse_expression("${undefined} + 1")
    with pytest.raises(ExpressionError) as exc_info:
        evaluate_expression(ast, {})
    assert exc_info.value.code == "undeclared_parameter"


def test_complex_expression():
    """Complex nested expressions work correctly."""
    ast = parse_expression("(${a} + ${b}) * (${c} - ${d}) / 2")
    result = evaluate_expression(ast, {"a": 10, "b": 2, "c": 8, "d": 4})
    assert result == 24.0  # (10+2)*(8-4)/2 = 12*4/2 = 24


def test_unary_minus():
    """Unary minus works correctly."""
    ast = parse_expression("-${x} + 5")
    result = evaluate_expression(ast, {"x": 3})
    assert result == 2.0


def test_unary_plus():
    """Unary plus works correctly."""
    ast = parse_expression("+${x} - 2")
    result = evaluate_expression(ast, {"x": 10})
    assert result == 8.0


def test_pure_numeric():
    """Pure numeric expression (no params) works."""
    ast = parse_expression("2 + 3 * 4")
    result = evaluate_expression(ast, {})
    assert result == 14.0


def test_float_literals():
    """Float literals are parsed correctly."""
    ast = parse_expression("1.5 + 2.5e-1")
    result = evaluate_expression(ast, {})
    assert result == 1.75


def test_non_finite_rejected():
    """Expressions producing inf/nan are rejected."""
    ast = parse_expression("1e400 / 1e400")  # inf / inf = nan
    with pytest.raises(ExpressionError) as exc_info:
        evaluate_expression(ast, {})
    assert exc_info.value.code == "non_finite_result"


def test_semicolon_rejected():
    """Semicolons are rejected (statement separators)."""
    with pytest.raises(ExpressionError) as exc_info:
        parse_expression("1; import os")
    assert exc_info.value.code == "invalid_expression"


def test_empty_expression_rejected():
    """Empty expressions are rejected."""
    with pytest.raises(ExpressionError):
        parse_expression("")
    with pytest.raises(ExpressionError):
        parse_expression("   ")


# ═══════════════════════════════════════════════════════════════════
# 3. Compilation tests
# ═══════════════════════════════════════════════════════════════════


def test_compile_produces_fingerprints():
    """Compile output contains all required fingerprint and metadata fields."""
    result = compile_recipe(MINIMAL_RECIPE)
    assert result["ok"] is True
    assert result["recipe_fingerprint"].startswith("sha256:")
    assert result["compile_fingerprint"].startswith("sha256:")
    assert result["script_sha256"].startswith("sha256:")
    assert "script" in result
    assert len(result["script"]) > 0
    assert "base_script" in result
    assert result["base_script"] == result["script"]
    assert "analysis_group_instructions" in result
    assert result["analysis_group_instructions"] == []
    assert "match_policy_version" in result
    assert result["match_policy_version"] == "1.0"
    assert isinstance(result["object_lifecycle"], list)
    assert isinstance(result["assumptions_report"], list)
    assert "raw_hook_hashes" in result
    assert isinstance(result["raw_hook_hashes"], dict)
    assert isinstance(result["warnings"], list)


def test_compile_order_matches_spec():
    """Script sections appear in correct compilation order."""
    result = compile_recipe(MINIMAL_RECIPE)
    script = result["script"].lower()

    # Use unique section header markers (avoid substring matches like
    # "geometry" matching inside "pre_geometry")
    markers = [
        "# === pre-geometry",
        "# === materials",
        "# === geometry",
        "# === post-geometry",
        "# === simulation region",
        "# === boundary",
        "# === mesh",
        "# === source",
        "# === monitor",
        "# === analysis",
    ]

    positions = []
    for marker in markers:
        idx = script.find(marker)
        if idx >= 0:
            positions.append((marker, idx))

    # Verify positions are strictly increasing
    for i in range(1, len(positions)):
        assert positions[i][1] > positions[i - 1][1], (
            f"Out of order: {positions[i-1][0]} (at {positions[i-1][1]}) "
            f"before {positions[i][0]} (at {positions[i][1]})"
        )

    # All expected markers should appear
    found_markers = {m for m, _ in positions}
    assert len(found_markers) >= 8, (
        f"Only found {len(found_markers)} markers: {found_markers}"
    )


def test_compile_with_sources_and_monitors():
    """Recipe with sources and monitors compiles correctly."""
    recipe = {
        **MINIMAL_RECIPE,
        "sources": [
            {
                "type": "gaussian",
                "name": "source_01",
                "properties": {
                    "wavelength_start": 1.5e-6,
                    "wavelength_stop": 1.6e-6,
                },
            }
        ],
        "monitors": [
            {
                "type": "frequency_power",
                "name": "monitor_01",
                "properties": {"monitor_type": "2D XZ"},
            }
        ],
    }
    result = compile_recipe(recipe)
    assert result["ok"] is True
    # Source and monitor should appear in object_lifecycle
    obj_names = [o["name"] for o in result["object_lifecycle"]]
    assert "source_01" in obj_names
    assert "monitor_01" in obj_names


def test_builtin_analysis_group_compiles_to_runtime_instruction():
    """Builtin analysis groups produce runtime instructions, not addobject in base_script."""
    recipe = {
        **MINIMAL_RECIPE,
        "outputs": ["T"],
        "fom": {"result": "T"},
        "analysis_groups": [{
            "type": "analysis_group",
            "name": "analysis_builtin",
            "analysis_intent": {
                "kind": "transmission",
                "outputs": ["T"],
            },
            "prefer_builtin": True,
            "require_builtin": False,
            "script_id": "",
            "parameter_overrides": {"x span": "${pillar_radius} * 4"},
            "properties": {},
        }],
    }

    result = compile_recipe(recipe)

    assert result["ok"] is True
    assert "addobject(" not in result["base_script"]
    assert 'save("device_model")' not in result["base_script"]
    assert result["script"] == result["base_script"]
    assert result["analysis_group_instructions"] == [{
        "name": "analysis_builtin",
        "analysis_intent": {"kind": "transmission", "outputs": ["T"]},
        "prefer_builtin": True,
        "require_builtin": False,
        "script_id": "",
        "parameter_overrides": {"x span": 4e-7},
        "properties": {},
        "recipe_context": {
            "solver": {},
            "sources": [],
            "monitors": [],
            "outputs": ["T"],
            "fom": {"result": "T"},
        },
    }]
    assert result["match_policy_version"] == "1.0"


def test_custom_analysis_group_stays_in_base_script():
    """Custom (non-builtin) analysis groups stay in base_script."""
    recipe = {
        **MINIMAL_RECIPE,
        "analysis_groups": [{
            "type": "analysis_group",
            "name": "custom",
            "prefer_builtin": False,
            "require_builtin": False,
            "properties": {"x": 0},
        }],
    }
    result = compile_recipe(recipe)
    assert "addanalysisgroup;" in result["base_script"]
    assert result["analysis_group_instructions"] == []


def test_compile_includes_assumptions_report():
    """Compilation includes the assumptions report with reasons."""
    result = compile_recipe(MINIMAL_RECIPE)
    assert len(result["assumptions_report"]) == 1
    assert result["assumptions_report"][0]["parameter"] == "pillar_radius"
    assert "reason" in result["assumptions_report"][0]


def test_compile_with_pre_post_run():
    """Compilation handles pre_run and post_run hooks."""
    recipe = {
        **MINIMAL_RECIPE,
        "pre_run": 'set("wavelength", 1.55e-6);',
        "post_run": 'runanalysis;',
    }
    result = compile_recipe(recipe)
    assert result["ok"] is True
    assert "pre_run" in result["raw_hook_hashes"]
    assert "post_run" in result["raw_hook_hashes"]
    assert result["raw_hook_hashes"]["pre_run"].startswith("sha256:")
    assert result["raw_hook_hashes"]["post_run"].startswith("sha256:")

    # Verify hook content lines are commented out in the build-only script
    script_lines = result["script"].splitlines()
    pre_comment_found = False
    post_comment_found = False
    for line in script_lines:
        if '# set("wavelength", 1.55e-6);' in line:
            pre_comment_found = True
            assert line.startswith("#"), (
                f"Expected pre_run hook line to be commented out, got: {line!r}"
            )
        if "# runanalysis;" in line:
            post_comment_found = True
            assert line.startswith("#"), (
                f"Expected post_run hook line to be commented out, got: {line!r}"
            )
    assert pre_comment_found, "pre_run hook content not found in script"
    assert post_comment_found, "post_run hook content not found in script"


def test_compile_invalid_recipe_fails():
    """Compiling an invalid recipe returns ok=False."""
    result = compile_recipe({"schema_version": "0.5"})
    assert result["ok"] is False


def test_normalized_recipe_has_deterministic_fingerprint():
    """Same recipe content produces same fingerprint regardless of key order."""
    recipe1 = dict(MINIMAL_RECIPE)
    recipe2 = {
        "geometry": MINIMAL_RECIPE["geometry"],
        "materials": MINIMAL_RECIPE["materials"],
        "schema_version": MINIMAL_RECIPE["schema_version"],
        "assumptions": MINIMAL_RECIPE["assumptions"],
        "parameters": MINIMAL_RECIPE["parameters"],
    }
    result1 = compile_recipe(recipe1)
    result2 = compile_recipe(recipe2)
    assert result1["recipe_fingerprint"] == result2["recipe_fingerprint"]


def test_compile_script_references_object_names():
    """Compiled script contains references to created objects."""
    result = compile_recipe(MINIMAL_RECIPE)
    script = result["script"]
    assert "SiO2" in script
    assert "pillar" in script


# ═══════════════════════════════════════════════════════════════════
# 4. Parameter validation edge cases
# ═══════════════════════════════════════════════════════════════════


def test_int_parameter_type():
    """Int-type parameters are accepted."""
    recipe = {
        "schema_version": "1.0",
        "parameters": {
            "n_layers": {
                "type": "int",
                "default": 5,
                "min": 1,
                "max": 10,
                "source_ref": {"locator": "config::n_layers"},
            }
        },
        "assumptions": [
            {"parameter": "n_layers", "reason": "Standard layer count"}
        ],
        "materials": [
            {"name": "TiO2", "type": "dielectric", "properties": {"index": 2.4}}
        ],
        "geometry": [
            {
                "type": "rectangle",
                "name": "layer",
                "properties": {"y_span": "${n_layers} * 50e-9"},
            }
        ],
    }
    result = validate_recipe(recipe)
    assert result["ok"] is True


def test_float_default_out_of_range():
    """Parameter default outside min/max range generates a warning."""
    recipe = {
        "schema_version": "1.0",
        "parameters": {
            "pillar_radius": {
                "type": "float",
                "default": 500e-9,  # Outside max=200e-9
                "min": 50e-9,
                "max": 200e-9,
                "unit": "m",
                "source_ref": {"locator": "model::pillar_radius"},
            }
        },
        "assumptions": [
            {"parameter": "pillar_radius", "reason": "Large pillar test"}
        ],
        "materials": [
            {"name": "SiO2", "type": "dielectric", "properties": {"index": 1.45}}
        ],
        "geometry": [
            {
                "type": "rectangle",
                "name": "pillar",
                "properties": {"x_span": "${pillar_radius} * 2"},
            }
        ],
    }
    result = validate_recipe(recipe)
    # Validation should still pass but with warnings
    assert result["ok"] is True
    assert len(result["warnings"]) > 0


def test_parameter_without_type_fails():
    """Parameter without a type field fails validation."""
    recipe = {
        **MINIMAL_RECIPE,
        "parameters": {
            "pillar_radius": {
                # Missing type
                "default": 100e-9,
            }
        },
    }
    result = validate_recipe(recipe)
    assert result["ok"] is False
    assert any(
        e["code"] == "missing_parameter_type" for e in result["errors"]
    )
