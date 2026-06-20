"""Tests for generic sweep plan validation and expansion.

Covers:
- values array preserves input order
- range inclusive start/stop with exact final value
- Cartesian product: last declared parameter changes fastest
- duplicate values → error
- task count exceeding max_tasks → error without truncation
- same Recipe + SweepPlan → same packet fingerprint
- unknown swept parameter → error
"""

import hashlib

import pytest

from src.generic_sweep import (
    _expand_cartesian_product,
    _expand_range,
    plan_generic_sweep,
    validate_sweep_plan,
)


# ═══════════════════════════════════════════════════════════════════
# Shared fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def min_recipe():
    """Minimal valid device recipe for sweep tests."""
    return {
        "schema_version": "1.0",
        "parameters": {
            "period": {
                "type": "float",
                "default": 500e-9,
                "min": 100e-9,
                "max": 1000e-9,
                "unit": "m",
                "source_ref": {"locator": "model::period"},
            },
            "ratio": {
                "type": "float",
                "default": 0.5,
                "min": 0.1,
                "max": 0.9,
                "unit": "",
                "source_ref": {"locator": "model::ratio"},
            },
        },
        "assumptions": [
            {"parameter": "period", "reason": "Typical NIR wavelength"},
            {"parameter": "ratio", "reason": "Common fill factor"},
        ],
        "materials": [
            {"name": "SiO2", "type": "dielectric", "properties": {"index": 1.45}}
        ],
        "geometry": [
            {
                "type": "rectangle",
                "name": "pillar",
                "properties": {
                    "x_span": "${period} * ${ratio}",
                    "y_span": "${period} * ${ratio}",
                },
            }
        ],
    }


@pytest.fixture
def sweep_plan_values():
    """Sweep plan with explicit values for two parameters."""
    return {
        "schema_version": "1.0",
        "parameters": [
            {"name": "period", "values": [390e-9, 470e-9, 540e-9]},
            {"name": "ratio", "values": [0.3, 0.5, 0.7]},
        ],
        "max_tasks": 100,
    }


@pytest.fixture
def sweep_plan_range():
    """Sweep plan with range-based parameter."""
    return {
        "schema_version": "1.0",
        "parameters": [
            {"name": "period", "values": [500e-9]},
            {"name": "ratio", "range": {"start": 0.2, "stop": 0.8, "count": 3}},
        ],
        "max_tasks": 100,
    }


@pytest.fixture
def sweep_plan_single():
    """Sweep plan with a single parameter to simplify range tests."""
    return {
        "schema_version": "1.0",
        "parameters": [
            {"name": "ratio", "range": {"start": 0.2, "stop": 0.8, "count": 3}},
        ],
        "max_tasks": 100,
    }


# ═══════════════════════════════════════════════════════════════════
# 1. _expand_range tests
# ═══════════════════════════════════════════════════════════════════


def test_range_inclusive_start_stop():
    """Range includes exact start and stop values."""
    result = _expand_range(0.2, 0.8, 3)
    assert result == [0.2, 0.5, 0.8]


def test_range_minimum_count():
    """Range with count=2 produces start and stop."""
    result = _expand_range(0.5, 0.5, 2)
    assert result == [0.5, 0.5]


def test_range_two_values():
    """Range with count=2 yields exactly two values."""
    result = _expand_range(0.0, 0.3, 2)
    assert result == [0.0, 0.3]


def test_range_with_submicron_values():
    """Range handles sub-micron float values correctly."""
    result = _expand_range(390e-9, 540e-9, 3)
    assert len(result) == 3
    assert result[0] == pytest.approx(390e-9)
    assert result[-1] == pytest.approx(540e-9)


def test_range_stop_is_exact():
    """The final value in a range must match stop exactly, not approximately."""
    result = _expand_range(0.0, 1.0, 5)
    assert result[-1] == 1.0
    assert result == [0.0, 0.25, 0.5, 0.75, 1.0]


def test_range_count_below_2_fails():
    """Range with count=1 should raise an error."""
    with pytest.raises(ValueError, match="count"):
        _expand_range(0.0, 1.0, 1)


# ═══════════════════════════════════════════════════════════════════
# 2. _expand_cartesian_product tests
# ═══════════════════════════════════════════════════════════════════


def test_values_preserves_order():
    """Explicit values array preserves input order exactly."""
    params = [{"name": "period", "values": [390e-9, 470e-9, 540e-9]}]
    tasks = _expand_cartesian_product(params)
    assert [t["period"] for t in tasks] == [390e-9, 470e-9, 540e-9]


def test_last_parameter_changes_fastest():
    """Last declared parameter changes fastest in Cartesian product."""
    params = [
        {"name": "outer", "values": [1, 2]},
        {"name": "inner", "values": [10, 20, 30]},
    ]
    tasks = _expand_cartesian_product(params)
    # Declaration order: outer, inner
    # inner changes fastest, so: (1,10), (1,20), (1,30), (2,10), (2,20), (2,30)
    expected = [
        {"outer": 1, "inner": 10},
        {"outer": 1, "inner": 20},
        {"outer": 1, "inner": 30},
        {"outer": 2, "inner": 10},
        {"outer": 2, "inner": 20},
        {"outer": 2, "inner": 30},
    ]
    assert tasks == expected


def test_cartesian_product_three_params():
    """Cartesian product with three parameters, last changes fastest."""
    params = [
        {"name": "a", "values": [1, 2]},
        {"name": "b", "values": [10, 20]},
        {"name": "c", "values": [100, 200]},
    ]
    tasks = _expand_cartesian_product(params)
    # c changes fastest, then b, then a
    assert len(tasks) == 8
    assert tasks[0] == {"a": 1, "b": 10, "c": 100}
    assert tasks[1] == {"a": 1, "b": 10, "c": 200}
    assert tasks[2] == {"a": 1, "b": 20, "c": 100}
    assert tasks[3] == {"a": 1, "b": 20, "c": 200}
    assert tasks[4] == {"a": 2, "b": 10, "c": 100}
    assert tasks[5] == {"a": 2, "b": 10, "c": 200}
    assert tasks[6] == {"a": 2, "b": 20, "c": 100}
    assert tasks[7] == {"a": 2, "b": 20, "c": 200}


def test_cartesian_product_single_param():
    """Single parameter produces one entry per value."""
    params = [{"name": "x", "values": [5, 10, 15]}]
    tasks = _expand_cartesian_product(params)
    assert tasks == [{"x": 5}, {"x": 10}, {"x": 15}]


def test_cartesian_product_with_range():
    """Cartesian product works with range-based parameters."""
    params = [
        {"name": "period", "values": [500e-9]},
        {"name": "ratio", "range": {"start": 0.2, "stop": 0.8, "count": 3}},
    ]
    tasks = _expand_cartesian_product(params)
    assert len(tasks) == 3
    assert tasks == [
        {"period": 500e-9, "ratio": 0.2},
        {"period": 500e-9, "ratio": 0.5},
        {"period": 500e-9, "ratio": 0.8},
    ]


# ═══════════════════════════════════════════════════════════════════
# 3. validate_sweep_plan tests
# ═══════════════════════════════════════════════════════════════════


def test_validate_valid_sweep_plan():
    """A well-formed sweep plan passes validation."""
    result = validate_sweep_plan(
        {
            "schema_version": "1.0",
            "parameters": [
                {"name": "ratio", "values": [0.2, 0.5, 0.8]},
            ],
            "max_tasks": 10,
        },
        recipe_fingerprint="sha256:abc123",
    )
    assert result["ok"] is True
    assert "sweep_fingerprint" in result


def test_validate_missing_schema_version():
    """Sweep plan without schema_version fails."""
    result = validate_sweep_plan(
        {
            "parameters": [
                {"name": "ratio", "values": [0.5]},
            ],
        },
        recipe_fingerprint="sha256:abc123",
    )
    assert result["ok"] is False
    assert any(e["code"] == "invalid_schema_version" for e in result["errors"])


def test_validate_missing_parameters():
    """Sweep plan without parameters fails."""
    result = validate_sweep_plan(
        {
            "schema_version": "1.0",
            "max_tasks": 10,
        },
        recipe_fingerprint="sha256:abc123",
    )
    assert result["ok"] is False
    assert any(e["code"] == "missing_parameters" for e in result["errors"])


def test_validate_parameter_without_name():
    """Parameter without a name fails."""
    result = validate_sweep_plan(
        {
            "schema_version": "1.0",
            "parameters": [
                {"values": [0.5]},
            ],
            "max_tasks": 10,
        },
        recipe_fingerprint="sha256:abc123",
    )
    assert result["ok"] is False
    assert any(e["code"] == "missing_parameter_name" for e in result["errors"])


def test_validate_parameter_without_values_or_range():
    """Parameter without values or range spec fails."""
    result = validate_sweep_plan(
        {
            "schema_version": "1.0",
            "parameters": [
                {"name": "ratio"},
            ],
            "max_tasks": 10,
        },
        recipe_fingerprint="sha256:abc123",
    )
    assert result["ok"] is False
    assert any(e["code"] == "missing_parameter_spec" for e in result["errors"])


def test_validate_parameter_with_both_values_and_range():
    """Parameter with both values and range fails."""
    result = validate_sweep_plan(
        {
            "schema_version": "1.0",
            "parameters": [
                {
                    "name": "ratio",
                    "values": [0.2, 0.5],
                    "range": {"start": 0.2, "stop": 0.8, "count": 3},
                },
            ],
            "max_tasks": 10,
        },
        recipe_fingerprint="sha256:abc123",
    )
    assert result["ok"] is False
    assert any(
        e["code"] == "ambiguous_parameter_spec" for e in result["errors"]
    )


def test_duplicate_values_fails():
    """Duplicate values in the same parameter cause a validation error."""
    result = validate_sweep_plan(
        {
            "schema_version": "1.0",
            "parameters": [
                {"name": "ratio", "values": [0.2, 0.5, 0.2, 0.8]},
            ],
            "max_tasks": 10,
        },
        recipe_fingerprint="sha256:abc123",
    )
    assert result["ok"] is False
    assert any(e["code"] == "duplicate_parameter_values" for e in result["errors"])


def test_validate_empty_values_fails():
    """Empty values array fails."""
    result = validate_sweep_plan(
        {
            "schema_version": "1.0",
            "parameters": [
                {"name": "ratio", "values": []},
            ],
            "max_tasks": 10,
        },
        recipe_fingerprint="sha256:abc123",
    )
    assert result["ok"] is False
    assert any(e["code"] == "empty_parameter_values" for e in result["errors"])


def test_validate_range_missing_fields():
    """Range missing required fields fails."""
    result = validate_sweep_plan(
        {
            "schema_version": "1.0",
            "parameters": [
                {"name": "ratio", "range": {"start": 0.2}},
            ],
            "max_tasks": 10,
        },
        recipe_fingerprint="sha256:abc123",
    )
    assert result["ok"] is False
    assert any(e["code"] == "invalid_range_spec" for e in result["errors"])


def test_validate_range_count_below_2_fails():
    """Range with count=1 fails (must be >= 2)."""
    result = validate_sweep_plan(
        {
            "schema_version": "1.0",
            "parameters": [
                {"name": "ratio", "range": {"start": 0.2, "stop": 0.8, "count": 1}},
            ],
            "max_tasks": 10,
        },
        recipe_fingerprint="sha256:abc123",
    )
    assert result["ok"] is False


# ═══════════════════════════════════════════════════════════════════
# 4. plan_generic_sweep tests
# ═══════════════════════════════════════════════════════════════════


def test_plan_includes_fingerprints(min_recipe, sweep_plan_values):
    """Plan packet includes all required fingerprints."""
    result = plan_generic_sweep(min_recipe, sweep_plan_values)
    assert result["ok"] is True
    plan = result["plan"]
    assert plan["recipe_fingerprint"].startswith("sha256:")
    assert plan["sweep_fingerprint"].startswith("sha256:")
    assert plan["packet_fingerprint"].startswith("sha256:")
    assert plan["compile_fingerprint"].startswith("sha256:")


def test_plan_task_count_matches_cartesian_product(min_recipe, sweep_plan_values):
    """Task count equals the Cartesian product of parameter values."""
    # 3 period values x 3 ratio values = 9 tasks
    result = plan_generic_sweep(min_recipe, sweep_plan_values)
    assert result["ok"] is True
    assert result["plan"]["task_count"] == 9
    assert len(result["plan"]["tasks"]) == 9


def test_plan_each_task_has_parameters(min_recipe, sweep_plan_values):
    """Each task has a parameters dict matching swept parameter names."""
    result = plan_generic_sweep(min_recipe, sweep_plan_values)
    tasks = result["plan"]["tasks"]
    for task in tasks:
        assert set(task["parameters"].keys()) == {"period", "ratio"}


def test_plan_each_task_has_unique_task_id(min_recipe, sweep_plan_values):
    """Every task has a unique task_id."""
    result = plan_generic_sweep(min_recipe, sweep_plan_values)
    task_ids = [t["task_id"] for t in result["plan"]["tasks"]]
    assert len(task_ids) == len(set(task_ids))


def test_plan_task_ids_are_stable(min_recipe, sweep_plan_values):
    """Task IDs are stable (deterministic)."""
    result1 = plan_generic_sweep(min_recipe, sweep_plan_values)
    result2 = plan_generic_sweep(min_recipe, sweep_plan_values)
    ids1 = [t["task_id"] for t in result1["plan"]["tasks"]]
    ids2 = [t["task_id"] for t in result2["plan"]["tasks"]]
    assert ids1 == ids2


def test_same_input_produces_same_fingerprint(min_recipe, sweep_plan_values):
    """Same Recipe + SweepPlan produces same packet_fingerprint."""
    result1 = plan_generic_sweep(min_recipe, sweep_plan_values)
    result2 = plan_generic_sweep(min_recipe, sweep_plan_values)
    assert result1["plan"]["packet_fingerprint"] == result2["plan"]["packet_fingerprint"]
    assert result1["plan"]["sweep_fingerprint"] == result2["plan"]["sweep_fingerprint"]


def test_different_sweep_produces_different_fingerprint(min_recipe):
    """Different sweep plans produce different fingerprints."""
    plan1 = {
        "schema_version": "1.0",
        "parameters": [
            {"name": "ratio", "values": [0.2, 0.5]},
        ],
        "max_tasks": 10,
    }
    plan2 = {
        "schema_version": "1.0",
        "parameters": [
            {"name": "ratio", "values": [0.3, 0.6]},
        ],
        "max_tasks": 10,
    }
    result1 = plan_generic_sweep(min_recipe, plan1)
    result2 = plan_generic_sweep(min_recipe, plan2)
    assert result1["plan"]["packet_fingerprint"] != result2["plan"]["packet_fingerprint"]


def test_unknown_parameter_in_sweep_fails(min_recipe):
    """Sweep parameter not in recipe → error."""
    bad_plan = {
        "schema_version": "1.0",
        "parameters": [
            {"name": "nonexistent_param", "values": [1.0]},
        ],
        "max_tasks": 10,
    }
    result = plan_generic_sweep(min_recipe, bad_plan)
    assert result["ok"] is False
    assert any(
        e["code"] == "unknown_sweep_parameter" for e in result["errors"]
    )


def test_task_count_exceeds_max_fails(min_recipe):
    """Task count exceeding max_tasks fails without truncation."""
    big_plan = {
        "schema_version": "1.0",
        "parameters": [
            {"name": "period", "values": list(range(50))},     # 50 values
            {"name": "ratio", "values": list(range(30))},      # 30 values → 1500 total
        ],
        "max_tasks": 100,
    }
    result = plan_generic_sweep(min_recipe, big_plan)
    assert result["ok"] is False
    assert any(
        e["code"] == "task_count_exceeds_max" for e in result["errors"]
    )


def test_plan_task_count_within_max_passes(min_recipe):
    """Task count within max_tasks passes."""
    small_plan = {
        "schema_version": "1.0",
        "parameters": [
            {"name": "period", "values": [390e-9, 470e-9]},
            {"name": "ratio", "values": [0.3, 0.5]},
        ],
        "max_tasks": 5,
    }
    result = plan_generic_sweep(min_recipe, small_plan)
    assert result["ok"] is True
    assert result["plan"]["task_count"] == 4


def test_plan_range_parameter_expands_correctly(min_recipe, sweep_plan_range):
    """Range parameter expands to correct number of tasks."""
    result = plan_generic_sweep(min_recipe, sweep_plan_range)
    assert result["ok"] is True
    # 1 period x 3 ratio values (0.2, 0.5, 0.8) = 3 tasks
    assert result["plan"]["task_count"] == 3


def test_plan_tasks_have_correct_index(min_recipe, sweep_plan_values):
    """Each task has the correct sequential index."""
    result = plan_generic_sweep(min_recipe, sweep_plan_values)
    for i, task in enumerate(result["plan"]["tasks"]):
        assert task["index"] == i


def test_plan_each_task_has_script_and_script_sha256(min_recipe, sweep_plan_values):
    """Each task has a compiled script and its SHA-256 fingerprint."""
    result = plan_generic_sweep(min_recipe, sweep_plan_values)
    for task in result["plan"]["tasks"]:
        assert "script" in task
        assert "script_sha256" in task
        assert task["script_sha256"].startswith("sha256:")
        # Verify the hash matches the script content
        expected = "sha256:" + hashlib.sha256(
            task["script"].encode("utf-8")
        ).hexdigest()
        assert task["script_sha256"] == expected


def test_plan_script_sha256_differs_per_task_when_params_change(min_recipe):
    """Script SHA-256 differs between tasks with different parameter values."""
    plan = {
        "schema_version": "1.0",
        "parameters": [
            {"name": "ratio", "values": [0.2, 0.8]},
        ],
        "max_tasks": 10,
    }
    result = plan_generic_sweep(min_recipe, plan)
    tasks = result["plan"]["tasks"]
    assert len(tasks) == 2
    # Different ratio values → different compiled scripts → different hashes
    assert tasks[0]["script_sha256"] != tasks[1]["script_sha256"]


def test_plan_with_range_minimal_recipe(min_recipe, sweep_plan_single):
    """Plan using range parameter with minimal recipe works."""
    result = plan_generic_sweep(min_recipe, sweep_plan_single)
    assert result["ok"] is True
    assert result["plan"]["task_count"] == 3
    ratios = [t["parameters"]["ratio"] for t in result["plan"]["tasks"]]
    assert ratios == [0.2, 0.5, 0.8]


def test_invalid_recipe_returns_error():
    """An invalid recipe causes plan_generic_sweep to return errors."""
    bad_recipe = {
        "schema_version": "1.0",
        "parameters": {},
        "materials": [],
        "geometry": [],
    }
    plan = {
        "schema_version": "1.0",
        "parameters": [
            {"name": "ratio", "values": [0.5]},
        ],
        "max_tasks": 10,
    }
    result = plan_generic_sweep(bad_recipe, plan)
    assert result["ok"] is False


def test_default_max_tasks_is_1000(min_recipe):
    """When max_tasks is not specified, defaults to 1000."""
    plan = {
        "schema_version": "1.0",
        "parameters": [
            {"name": "ratio", "values": list(range(500))},
        ],
        # No max_tasks field
    }
    result = plan_generic_sweep(min_recipe, plan)
    assert result["ok"] is True  # 500 < default 1000


def test_validate_sweep_fingerprint_is_stable():
    """validate_sweep_plan returns a stable sweep_fingerprint."""
    spec = {
        "schema_version": "1.0",
        "parameters": [
            {"name": "ratio", "values": [0.2, 0.5, 0.8]},
        ],
        "max_tasks": 10,
    }
    r1 = validate_sweep_plan(spec, recipe_fingerprint="sha256:abc123")
    r2 = validate_sweep_plan(spec, recipe_fingerprint="sha256:abc123")
    assert r1["sweep_fingerprint"] == r2["sweep_fingerprint"]


def test_plan_order_matches_cartesian_product(min_recipe):
    """Task order matches Cartesian product with last param changing fastest."""
    plan = {
        "schema_version": "1.0",
        "parameters": [
            {"name": "period", "values": [300e-9, 400e-9]},
            {"name": "ratio", "values": [0.2, 0.5, 0.8]},
        ],
        "max_tasks": 10,
    }
    result = plan_generic_sweep(min_recipe, plan)
    tasks = result["plan"]["tasks"]
    # period varies slowest, ratio fastest
    # (300,0.2), (300,0.5), (300,0.8), (400,0.2), (400,0.5), (400,0.8)
    assert tasks[0]["parameters"] == {"period": 300e-9, "ratio": 0.2}
    assert tasks[1]["parameters"] == {"period": 300e-9, "ratio": 0.5}
    assert tasks[2]["parameters"] == {"period": 300e-9, "ratio": 0.8}
    assert tasks[3]["parameters"] == {"period": 400e-9, "ratio": 0.2}
    assert tasks[4]["parameters"] == {"period": 400e-9, "ratio": 0.5}
    assert tasks[5]["parameters"] == {"period": 400e-9, "ratio": 0.8}
