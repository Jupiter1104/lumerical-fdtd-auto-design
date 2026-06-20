"""Tests for fdtd operation compiler primitives."""

from src.fdtd_operations import compile_object_create, validate_object_type
from src.fdtd_schema import fingerprint_json, stable_json_dumps


def test_stable_json_and_fingerprint_are_order_independent():
    left = {"b": 2, "a": 1}
    right = {"a": 1, "b": 2}
    assert stable_json_dumps(left) == stable_json_dumps(right)
    assert fingerprint_json(left) == fingerprint_json(right)


def test_object_create_dry_run_script_and_warnings():
    result = compile_object_create(
        object_type="rectangle",
        name="rect_1",
        properties={"x span": 1e-6, "material": "Si"},
    )
    assert result["ok"] is True
    assert "addrect;" in result["script"]
    assert 'set("name","rect_1");' in result["script"]
    assert 'set("x span",1e-06);' in result["script"]
    assert result["script_sha256"].startswith("sha256:")


def test_source_type_rejected_from_generic_object_create():
    assert validate_object_type("plane_source") == {
        "ok": False,
        "error": {
            "type": "use_typed_domain_tool",
            "message": "Use fdtd_source_create for object_type=plane_source.",
            "details": {"tool": "fdtd_source_create"},
        },
    }


def test_monitor_type_rejected_from_generic_object_create():
    assert validate_object_type("power_monitor") == {
        "ok": False,
        "error": {
            "type": "use_typed_domain_tool",
            "message": "Use fdtd_monitor_create for object_type=power_monitor.",
            "details": {"tool": "fdtd_monitor_create"},
        },
    }


def test_valid_object_types_accepted():
    valid_types = [
        "fdtd_region",
        "rectangle",
        "circle",
        "ring",
        "polygon",
        "structure_group",
        "mesh_override",
    ]
    for obj_type in valid_types:
        result = validate_object_type(obj_type)
        assert result == {"ok": True}, f"Expected ok for {obj_type}, got {result}"


def test_lsf_value_formatting():
    from src.fdtd_script import format_lsf_value, quote_lsf_string

    # bool -> 1/0
    assert format_lsf_value(True) == "1"
    assert format_lsf_value(False) == "0"

    # float precision via repr
    assert "e" in format_lsf_value(1e-6) or format_lsf_value(1e-6) == "1e-06"

    # string quoting
    quoted = quote_lsf_string('hello "world"')
    assert quoted == '"hello \\"world\\""'

    # list formatting
    assert format_lsf_value([1, 2, 3]) == "{1, 2, 3}"
    assert format_lsf_value(["a", "b"]) == '{"a", "b"}'
