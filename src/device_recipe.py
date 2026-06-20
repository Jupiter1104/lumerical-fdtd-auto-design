"""Device recipe validation, normalization, and compilation.

Pure Python — no Windows/Lumerical/RPC required.

Provides:
- Safe expression parser (restricted AST, no eval/exec)
- Recipe validator with structured error reporting
- Recipe compiler that generates Lumerical script
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from .fdtd_schema import fingerprint_json, stable_json_dumps
from .fdtd_script import format_lsf_value, quote_lsf_string


# ═══════════════════════════════════════════════════════════════════════════
# Expression parser
# ═══════════════════════════════════════════════════════════════════════════

# Valid parameter reference: ${name} where name is a valid identifier
_PARAM_REF_RE = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

# Combined tokenizer pattern — matches one token at a time from left to right
_TOKEN_RE = re.compile(
    r"""
    \s*
    (
        \$\{[a-zA-Z_][a-zA-Z0-9_]*\}  # param ref ${name}
      | \d+\.\d*(?:[eE][+-]?\d+)?     # float literal
      | \d+(?:[eE][+-]?\d+)?          # int literal (also catches int-suffix of float)
      | \+                             # plus
      | -                              # minus
      | \*                             # star
      | /                              # slash
      | \(                             # left paren
      | \)                             # right paren
    )
    """,
    re.VERBOSE,
)

# Patterns Python injection attempts try to use
_DANGEROUS_PATTERNS = [
    "__", "import", "exec", "eval", "compile", "open",
    "getattr", "setattr", "hasattr", "delattr",
    "globals", "locals", "vars", "dir",
    "lambda", "yield", "raise", "assert",
    "print", "input",
    "base64", "zlib", "pickle", "marshal",
    "subprocess", "shutil", "pathlib",
    "os.", "sys.",
    ";",
]


class ExpressionError(Exception):
    """Error during expression parsing or evaluation."""

    def __init__(self, message: str, code: str = "invalid_expression") -> None:
        super().__init__(message)
        self.code = code


# ── AST nodes ────────────────────────────────────────────────────────────────


class _NumberNode:
    __slots__ = ("value",)

    def __init__(self, value: Union[int, float]) -> None:
        self.value = value

    def __repr__(self) -> str:
        return f"Number({self.value!r})"


class _ParamRefNode:
    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"ParamRef(${{{self.name}}})"


class _BinaryOpNode:
    __slots__ = ("op", "left", "right")

    def __init__(self, op: str, left: Any, right: Any) -> None:
        self.op = op
        self.left = left
        self.right = right

    def __repr__(self) -> str:
        return f"BinOp({self.op!r}, {self.left!r}, {self.right!r})"


class _UnaryOpNode:
    __slots__ = ("op", "operand")

    def __init__(self, op: str, operand: Any) -> None:
        self.op = op
        self.operand = operand

    def __repr__(self) -> str:
        return f"UnaryOp({self.op!r}, {self.operand!r})"


# ── Tokenizer ────────────────────────────────────────────────────────────────


class _TokenType:
    NUMBER = "NUMBER"
    PARAM_REF = "PARAM_REF"
    PLUS = "PLUS"
    MINUS = "MINUS"
    STAR = "STAR"
    SLASH = "SLASH"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    EOF = "EOF"


class _Token:
    __slots__ = ("type", "value", "pos")

    def __init__(self, type: str, value: Any, pos: int) -> None:
        self.type = type
        self.value = value
        self.pos = pos

    def __repr__(self) -> str:
        return f"Token({self.type}, {self.value!r}, {self.pos})"


def _tokenize(expr: str) -> List[_Token]:
    """Tokenize an expression string into a list of tokens."""
    tokens: List[_Token] = []
    pos = 0

    for m in _TOKEN_RE.finditer(expr):
        start = m.start()
        if start > pos:
            bad = expr[pos:start].strip()
            if bad:
                raise ExpressionError(
                    f"Unrecognized token: {bad!r} at position {pos}"
                )
        text = m.group(1)

        if text.startswith("${"):
            name = text[2:-1]
            tokens.append(_Token(_TokenType.PARAM_REF, name, start))
        elif text == "+":
            tokens.append(_Token(_TokenType.PLUS, text, start))
        elif text == "-":
            tokens.append(_Token(_TokenType.MINUS, text, start))
        elif text == "*":
            tokens.append(_Token(_TokenType.STAR, text, start))
        elif text == "/":
            tokens.append(_Token(_TokenType.SLASH, text, start))
        elif text == "(":
            tokens.append(_Token(_TokenType.LPAREN, text, start))
        elif text == ")":
            tokens.append(_Token(_TokenType.RPAREN, text, start))
        else:
            # Numeric literal — parse as int or float
            if "." in text or "e" in text.lower():
                tokens.append(_Token(_TokenType.NUMBER, float(text), start))
            else:
                tokens.append(_Token(_TokenType.NUMBER, int(text), start))
        pos = m.end()

    # Check for trailing unrecognized text
    remaining = expr[pos:].strip()
    if remaining:
        raise ExpressionError(
            f"Unrecognized token: {remaining!r} at position {pos}"
        )

    return tokens


# ── Recursive-descent parser ─────────────────────────────────────────────────


class _Parser:
    """Recursive-descent parser for restricted arithmetic expressions.

    Grammar::

        expr   → term (('+' | '-') term)*
        term   → unary (('*' | '/') unary)*
        unary  → ('+' | '-') unary | primary
        primary → NUMBER | '${' NAME '}' | '(' expr ')'
    """

    def __init__(self, tokens: List[_Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> _Token:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return _Token(_TokenType.EOF, None, -1)

    def _advance(self) -> _Token:
        tok = self._peek()
        self._pos += 1
        return tok

    def _expect(self, *types: str) -> _Token:
        tok = self._advance()
        if tok.type not in types:
            expected = ", ".join(types)
            raise ExpressionError(
                f"Expected {expected}, got {tok.type} ({tok.value!r}) "
                f"at position {tok.pos}"
            )
        return tok

    def parse(self) -> Any:
        """Parse the full expression and return the root AST node."""
        result = self._parse_expr()
        if self._peek().type != _TokenType.EOF:
            raise ExpressionError(
                f"Unexpected token after expression: "
                f"{self._peek().value!r} at position {self._peek().pos}"
            )
        return result

    def _parse_expr(self) -> Any:
        """expr → term (('+' | '-') term)*"""
        left = self._parse_term()
        while self._peek().type in (_TokenType.PLUS, _TokenType.MINUS):
            op = self._advance().value
            right = self._parse_term()
            left = _BinaryOpNode(op=op, left=left, right=right)
        return left

    def _parse_term(self) -> Any:
        """term → unary (('*' | '/') unary)*"""
        left = self._parse_unary()
        while self._peek().type in (_TokenType.STAR, _TokenType.SLASH):
            op = self._advance().value
            right = self._parse_unary()
            left = _BinaryOpNode(op=op, left=left, right=right)
        return left

    def _parse_unary(self) -> Any:
        """unary → ('+' | '-') unary | primary"""
        if self._peek().type in (_TokenType.PLUS, _TokenType.MINUS):
            op = self._advance().value
            operand = self._parse_unary()
            return _UnaryOpNode(op=op, operand=operand)
        return self._parse_primary()

    def _parse_primary(self) -> Any:
        """primary → NUMBER | '${' NAME '}' | '(' expr ')'"""
        tok = self._peek()
        if tok.type == _TokenType.NUMBER:
            self._advance()
            return _NumberNode(value=tok.value)
        if tok.type == _TokenType.PARAM_REF:
            self._advance()
            return _ParamRefNode(name=tok.value)
        if tok.type == _TokenType.LPAREN:
            self._advance()
            expr = self._parse_expr()
            self._expect(_TokenType.RPAREN)
            return expr
        raise ExpressionError(
            f"Unexpected token: {tok.value!r} at position {tok.pos}"
        )


# ── Public API ───────────────────────────────────────────────────────────────


def _security_check(expr: str) -> None:
    """Reject Python-specific constructs and injection attempts.

    This is a belt-and-suspenders check — the tokenizer/parser already
    only accepts a strict whitelist of tokens.  This pre-scan adds an
    extra layer of defence.
    """
    # Remove valid parameter references before scanning the remainder
    cleaned = _PARAM_REF_RE.sub(" ", expr)
    cleaned_lower = cleaned.lower()

    for pattern in _DANGEROUS_PATTERNS:
        if pattern.lower() in cleaned_lower:
            raise ExpressionError(
                f"Expression contains disallowed pattern: {pattern!r}",
                code="invalid_expression",
            )

    # Reject dots outside numeric literals (attribute access)
    dotless = re.sub(r"\d+\.\d*", "0", cleaned)
    dotless = re.sub(r"\d*\.\d+", "0", dotless)
    if "." in dotless:
        raise ExpressionError(
            "Attribute access ('.') is not allowed in expressions",
            code="invalid_expression",
        )


def parse_expression(expr: str) -> Any:
    """Parse an expression string into a safe AST.

    Accepted: numeric constants, ``${name}`` parameter references,
    ``+`` ``-`` ``*`` ``/``, parentheses, unary plus/minus.

    Raises :exc:`ExpressionError` for any disallowed syntax.
    """
    if not isinstance(expr, str):
        raise ExpressionError(
            f"Expression must be a string, got {type(expr).__name__}"
        )
    stripped = expr.strip()
    if not stripped:
        raise ExpressionError("Empty expression")

    _security_check(stripped)
    tokens = _tokenize(stripped)
    parser = _Parser(tokens)
    return parser.parse()


def evaluate_expression(
    ast_node: Any, params: Dict[str, Union[int, float]]
) -> float:
    """Evaluate a parsed expression AST with the given parameter values.

    Raises :exc:`ExpressionError` for undeclared parameters, division by
    zero, or non-finite results.
    """
    if isinstance(ast_node, _NumberNode):
        result = float(ast_node.value)
    elif isinstance(ast_node, _ParamRefNode):
        if ast_node.name not in params:
            raise ExpressionError(
                f"Undeclared parameter reference: ${{{ast_node.name}}}",
                code="undeclared_parameter",
            )
        result = float(params[ast_node.name])
    elif isinstance(ast_node, _BinaryOpNode):
        left = evaluate_expression(ast_node.left, params)
        right = evaluate_expression(ast_node.right, params)
        if ast_node.op == "+":
            result = left + right
        elif ast_node.op == "-":
            result = left - right
        elif ast_node.op == "*":
            result = left * right
        elif ast_node.op == "/":
            if right == 0:
                raise ExpressionError(
                    "Division by zero", code="division_by_zero"
                )
            result = left / right
        else:
            raise ExpressionError(f"Unknown operator: {ast_node.op}")
    elif isinstance(ast_node, _UnaryOpNode):
        operand = evaluate_expression(ast_node.operand, params)
        result = operand if ast_node.op == "+" else -operand
    else:
        raise ExpressionError(
            f"Unknown AST node type: {type(ast_node).__name__}"
        )

    if not math.isfinite(result):
        raise ExpressionError(
            f"Result is non-finite: {result}", code="non_finite_result"
        )

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Recipe validation
# ═══════════════════════════════════════════════════════════════════════════

VALID_PARAM_TYPES = {"float", "int"}


def _validate_parameter(
    name: str,
    param: dict,
    assumptions: List[dict],
) -> Tuple[List[dict], List[dict]]:
    """Validate a single parameter definition.

    Returns (errors, warnings).
    """
    errors: List[dict] = []
    warnings: List[dict] = []

    if not isinstance(param, dict):
        errors.append({
            "code": "invalid_parameter",
            "message": f"Parameter {name!r} must be an object",
        })
        return errors, warnings

    # type is required
    ptype = param.get("type")
    if ptype not in VALID_PARAM_TYPES:
        errors.append({
            "code": "missing_parameter_type",
            "message": (
                f"Parameter {name!r} must have 'type' in "
                f"{VALID_PARAM_TYPES}, got {ptype!r}"
            ),
        })
        return errors, warnings

    has_default = "default" in param
    has_source_ref = (
        isinstance(param.get("source_ref"), dict)
        and "locator" in param["source_ref"]
        and param["source_ref"]["locator"]
    )

    # Required parameter (no default) must have source_ref.locator
    if not has_default and not has_source_ref:
        errors.append({
            "code": "missing_required_source_ref",
            "message": (
                f"Required parameter {name!r} has no default and no "
                f"source_ref.locator"
            ),
        })

    # Non-critical parameter (has default) must have a documented assumption
    if has_default:
        matching_assumption = None
        for assumption in assumptions:
            if isinstance(assumption, dict) and assumption.get("parameter") == name:
                matching_assumption = assumption
                break

        if matching_assumption is None:
            errors.append({
                "code": "missing_assumption",
                "message": (
                    f"Non-critical parameter {name!r} has a default but no "
                    f"assumption with a reason"
                ),
            })
        elif not matching_assumption.get("reason"):
            errors.append({
                "code": "missing_assumption",
                "message": (
                    f"Assumption for parameter {name!r} is missing 'reason'"
                ),
            })

    # Validate default against min/max
    if has_default:
        default_val = param["default"]
        if "min" in param and default_val < param["min"]:
            warnings.append({
                "code": "default_below_min",
                "message": (
                    f"Parameter {name!r} default ({default_val}) is below "
                    f"min ({param['min']})"
                ),
            })
        if "max" in param and default_val > param["max"]:
            warnings.append({
                "code": "default_above_max",
                "message": (
                    f"Parameter {name!r} default ({default_val}) is above "
                    f"max ({param['max']})"
                ),
            })

    # Validate type consistency
    if has_default:
        if ptype == "int" and not isinstance(param["default"], int):
            errors.append({
                "code": "type_mismatch",
                "message": (
                    f"Parameter {name!r} type is int but default is "
                    f"{type(param['default']).__name__}"
                ),
            })
        if ptype == "float" and isinstance(param["default"], bool):
            errors.append({
                "code": "type_mismatch",
                "message": (
                    f"Parameter {name!r} type is float but default is bool"
                ),
            })

    return errors, warnings


def _validate_geometry_step(
    step: dict, param_names: set, index: int
) -> Tuple[List[dict], List[dict]]:
    """Validate a single geometry step."""
    errors: List[dict] = []
    warnings: List[dict] = []

    if not isinstance(step, dict):
        errors.append({
            "code": "invalid_geometry",
            "message": f"Geometry step {index} must be an object",
        })
        return errors, warnings

    if "type" not in step:
        errors.append({
            "code": "missing_geometry_type",
            "message": f"Geometry step {index} missing 'type'",
        })
    if "name" not in step:
        errors.append({
            "code": "missing_geometry_name",
            "message": f"Geometry step {index} missing 'name'",
        })

    # Validate expressions in properties
    properties = step.get("properties", {})
    if isinstance(properties, dict):
        for prop_name, prop_value in properties.items():
            if isinstance(prop_value, str) and "${" in prop_value:
                try:
                    ast = parse_expression(prop_value)
                    # Check that all referenced params are declared
                    _check_param_refs(ast, param_names)
                except ExpressionError as exc:
                    errors.append({
                        "code": exc.code,
                        "message": (
                            f"Geometry step {index} property {prop_name!r}: "
                            f"{exc}"
                        ),
                    })
    return errors, warnings


def _check_param_refs(ast_node: Any, param_names: set) -> None:
    """Recursively check that all ParamRefNodes reference declared parameters."""
    if isinstance(ast_node, _ParamRefNode):
        if ast_node.name not in param_names:
            raise ExpressionError(
                f"Undeclared parameter reference: ${{{ast_node.name}}}",
                code="undeclared_parameter",
            )
    elif isinstance(ast_node, _BinaryOpNode):
        _check_param_refs(ast_node.left, param_names)
        _check_param_refs(ast_node.right, param_names)
    elif isinstance(ast_node, _UnaryOpNode):
        _check_param_refs(ast_node.operand, param_names)


def _validate_material(
    mat: dict, index: int, param_names: set
) -> Tuple[List[dict], List[dict]]:
    """Validate a single material definition."""
    errors: List[dict] = []
    warnings: List[dict] = []

    if not isinstance(mat, dict):
        errors.append({
            "code": "invalid_material",
            "message": f"Material {index} must be an object",
        })
        return errors, warnings

    if "name" not in mat:
        errors.append({
            "code": "missing_material_name",
            "message": f"Material {index} missing 'name'",
        })
    if "type" not in mat:
        errors.append({
            "code": "missing_material_type",
            "message": f"Material {index} missing 'type'",
        })

    # Validate expressions in material properties
    properties = mat.get("properties", {})
    if isinstance(properties, dict):
        for prop_name, prop_value in properties.items():
            if isinstance(prop_value, str) and "${" in prop_value:
                try:
                    ast = parse_expression(prop_value)
                    _check_param_refs(ast, param_names)
                except ExpressionError as exc:
                    errors.append({
                        "code": exc.code,
                        "message": (
                            f"Material {index} property {prop_name!r}: {exc}"
                        ),
                    })
    return errors, warnings


def validate_recipe(recipe: dict) -> dict:
    """Validate and normalize a device recipe.

    Returns a dict with keys: ``ok``, ``errors``, ``warnings``,
    ``normalized_recipe`` (if ok), and ``defaults_applied``.
    """
    errors: List[dict] = []
    warnings: List[dict] = []
    defaults_applied: List[dict] = []

    if not isinstance(recipe, dict):
        return {
            "ok": False,
            "errors": [{"code": "invalid_recipe", "message": "Recipe must be a dict"}],
            "warnings": [],
            "defaults_applied": [],
        }

    # ── schema_version ──────────────────────────────────────────────────

    schema_version = recipe.get("schema_version")
    if schema_version != "1.0":
        errors.append({
            "code": "invalid_schema_version",
            "message": (
                f"schema_version must be '1.0', got {schema_version!r}"
            ),
        })
        return {
            "ok": False,
            "errors": errors,
            "warnings": warnings,
            "defaults_applied": defaults_applied,
        }

    # ── parameters ───────────────────────────────────────────────────────

    params = recipe.get("parameters", {})
    if not isinstance(params, dict) or len(params) == 0:
        errors.append({
            "code": "missing_parameters",
            "message": "Recipe must have at least one parameter",
        })
        return {
            "ok": False,
            "errors": errors,
            "warnings": warnings,
            "defaults_applied": defaults_applied,
        }

    assumptions = recipe.get("assumptions", [])
    if not isinstance(assumptions, list):
        assumptions = []

    normalized_params: Dict[str, dict] = {}
    param_names: set = set()

    for name in sorted(params):
        param = params[name]
        p_errors, p_warnings = _validate_parameter(name, param, assumptions)
        errors.extend(p_errors)
        warnings.extend(p_warnings)

        # Build normalized parameter
        ptype = param.get("type")
        if ptype in VALID_PARAM_TYPES:
            norm = {"type": ptype}
            for key in ("default", "min", "max", "unit"):
                if key in param:
                    norm[key] = param[key]
            if "source_ref" in param:
                norm["source_ref"] = dict(param["source_ref"])
            normalized_params[name] = norm
        param_names.add(name)

    # ── assumptions ──────────────────────────────────────────────────────

    normalized_assumptions: List[dict] = []
    seen_params: set = set()
    for i, assumption in enumerate(assumptions):
        if not isinstance(assumption, dict):
            errors.append({
                "code": "invalid_assumption",
                "message": f"Assumption {i} must be an object",
            })
            continue
        param_name = assumption.get("parameter", "")
        if param_name in seen_params:
            warnings.append({
                "code": "duplicate_assumption",
                "message": f"Duplicate assumption for parameter {param_name!r}",
            })
        seen_params.add(param_name)
        normalized_assumptions.append({
            "parameter": param_name,
            "reason": assumption.get("reason", ""),
        })

    # ── materials ────────────────────────────────────────────────────────

    materials = recipe.get("materials", [])
    if not isinstance(materials, list) or len(materials) == 0:
        errors.append({
            "code": "missing_materials",
            "message": "Recipe must have at least one material",
        })

    normalized_materials: List[dict] = []
    material_names: set = set()
    for i, mat in enumerate(materials):
        m_errors, m_warnings = _validate_material(mat, i, param_names)
        errors.extend(m_errors)
        warnings.extend(m_warnings)

        if isinstance(mat, dict):
            norm_mat = {
                "name": mat.get("name", ""),
                "type": mat.get("type", ""),
                "properties": dict(mat.get("properties", {})),
            }
            normalized_materials.append(norm_mat)
            if norm_mat["name"]:
                material_names.add(norm_mat["name"])

    # ── geometry ─────────────────────────────────────────────────────────

    geometry = recipe.get("geometry", [])
    if not isinstance(geometry, list) or len(geometry) == 0:
        errors.append({
            "code": "missing_geometry",
            "message": "Recipe must have at least one geometry step",
        })

    normalized_geometry: List[dict] = []
    geometry_names: set = set()
    for i, step in enumerate(geometry):
        g_errors, g_warnings = _validate_geometry_step(step, param_names, i)
        errors.extend(g_errors)
        warnings.extend(g_warnings)

        if isinstance(step, dict):
            norm_step = {
                "type": step.get("type", ""),
                "name": step.get("name", ""),
                "properties": dict(step.get("properties", {})),
            }
            normalized_geometry.append(norm_step)
            if norm_step["name"]:
                geometry_names.add(norm_step["name"])

    # ── optional sections ────────────────────────────────────────────────

    normalized_sources = _normalize_optional_list(
        recipe.get("sources"), param_names
    )
    normalized_monitors = _normalize_optional_list(
        recipe.get("monitors"), param_names
    )
    normalized_analysis_groups = _normalize_optional_list(
        recipe.get("analysis_groups"), param_names
    )

    # ── hooks ────────────────────────────────────────────────────────────

    pre_run = recipe.get("pre_run", "")
    post_run = recipe.get("post_run", "")
    if not isinstance(pre_run, str):
        pre_run = ""
    if not isinstance(post_run, str):
        post_run = ""

    # ── build result ─────────────────────────────────────────────────────

    normalized = {
        "schema_version": "1.0",
        "parameters": normalized_params,
        "assumptions": normalized_assumptions,
        "materials": normalized_materials,
        "geometry": normalized_geometry,
        "sources": normalized_sources,
        "monitors": normalized_monitors,
        "analysis_groups": normalized_analysis_groups,
        "pre_run": pre_run,
        "post_run": post_run,
    }

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "normalized_recipe": normalized,
        "defaults_applied": defaults_applied,
    }


def _normalize_optional_list(
    items: Any, param_names: set
) -> List[dict]:
    """Normalize an optional list of typed items (sources, monitors, etc.)."""
    if not isinstance(items, list):
        return []
    result: List[dict] = []
    for item in items:
        if isinstance(item, dict):
            result.append({
                "type": item.get("type", ""),
                "name": item.get("name", ""),
                "properties": dict(item.get("properties", {})),
            })
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Recipe compilation
# ═══════════════════════════════════════════════════════════════════════════


def _resolve_param_values(params: dict) -> Dict[str, Union[int, float]]:
    """Extract default values from normalized parameters."""
    values: Dict[str, Union[int, float]] = {}
    for name, p in params.items():
        if "default" in p:
            values[name] = p["default"]
    return values


def _compile_expression(expr_str: str, param_values: dict) -> str:
    """Compile an expression string to a resolved numeric value.

    If ``expr_str`` is not a string or doesn't contain ``${``, return as-is
    (it's already a literal).  Otherwise parse, evaluate, and format.
    """
    if not isinstance(expr_str, str) or "${" not in expr_str:
        return format_lsf_value(expr_str) if not isinstance(expr_str, str) else expr_str

    try:
        ast = parse_expression(expr_str)
        result = evaluate_expression(ast, param_values)
        return format_lsf_value(result)
    except ExpressionError:
        # If evaluation fails (undeclared param, etc.), emit a comment
        return f"# ERROR: could not resolve expression: {expr_str}"


def _generate_material_script(
    materials: List[dict], param_values: dict
) -> Tuple[List[str], List[dict]]:
    """Generate LSF script lines for materials."""
    lines: List[str] = []
    lifecycle: List[dict] = []

    lines.append("# === Materials ===")
    for mat in materials:
        name = mat.get("name", "")
        mat_type = mat.get("type", "")
        props = mat.get("properties", {})

        lines.append("")
        lines.append(f"# Material: {name} ({mat_type})")
        lines.append("addmaterial;")
        lines.append(f'set("name", {quote_lsf_string(name)});')
        for prop_name, prop_value in props.items():
            resolved = _compile_expression(prop_value, param_values)
            lines.append(f'set({quote_lsf_string(prop_name)}, {resolved});')

        lifecycle.append({
            "name": name,
            "type": "material",
            "material_type": mat_type,
        })

    lines.append("")
    return lines, lifecycle


def _generate_geometry_script(
    geometry: List[dict], param_values: dict
) -> Tuple[List[str], List[dict]]:
    """Generate LSF script lines for geometry."""
    lines: List[str] = []
    lifecycle: List[dict] = []

    lines.append("# === Geometry ===")

    # Map geometry types to Lumerical commands
    TYPE_COMMANDS = {
        "rectangle": "addrect",
        "circle": "addcircle",
        "polygon": "addpoly",
        "ring": "addring",
    }

    for step in geometry:
        geo_type = step.get("type", "")
        geo_name = step.get("name", "")
        props = step.get("properties", {})

        command = TYPE_COMMANDS.get(geo_type, f"# Unknown type: {geo_type}")
        lines.append("")
        lines.append(f"# Geometry: {geo_name} ({geo_type})")
        if geo_type in TYPE_COMMANDS:
            lines.append(f"{command};")
        else:
            lines.append(command)
        lines.append(f'set("name", {quote_lsf_string(geo_name)});')

        for prop_name, prop_value in props.items():
            resolved = _compile_expression(prop_value, param_values)
            lines.append(f'set({quote_lsf_string(prop_name)}, {resolved});')

        lifecycle.append({
            "name": geo_name,
            "type": "geometry",
            "geometry_type": geo_type,
        })

    lines.append("")
    return lines, lifecycle


def _generate_simulation_region_script() -> Tuple[List[str], List[dict]]:
    """Generate simulation region section."""
    lines: List[str] = [
        "# === Simulation Region ===",
        "addfdtd;",
        'set("dimension", "2D");',
        "",
    ]
    lifecycle: List[dict] = [{"name": "FDTD", "type": "simulation_region"}]
    return lines, lifecycle


def _generate_boundaries_script() -> List[str]:
    """Generate boundary conditions section."""
    return [
        "# === Boundary Conditions ===",
        "# Configure boundary conditions",
        "",
    ]


def _generate_mesh_script() -> List[str]:
    """Generate mesh section."""
    return [
        "# === Mesh ===",
        "addmesh;",
        'set("dx", 10e-9);',
        'set("dy", 10e-9);',
        "",
    ]


def _generate_sources_script(
    sources: List[dict], param_values: dict
) -> Tuple[List[str], List[dict]]:
    """Generate sources section."""
    lines: List[str] = []
    lifecycle: List[dict] = []

    if not sources:
        lines.append("# === Sources ===")
        lines.append("# No sources defined")
        lines.append("")
        return lines, lifecycle

    lines.append("# === Sources ===")
    for src in sources:
        name = src.get("name", "")
        src_type = src.get("type", "")
        props = src.get("properties", {})

        lines.append("")
        lines.append(f"# Source: {name} ({src_type})")
        lines.append("addsource;")
        lines.append(f'set("name", {quote_lsf_string(name)});')
        for prop_name, prop_value in props.items():
            resolved = _compile_expression(prop_value, param_values)
            lines.append(f'set({quote_lsf_string(prop_name)}, {resolved});')

        lifecycle.append({
            "name": name,
            "type": "source",
            "source_type": src_type,
        })

    lines.append("")
    return lines, lifecycle


def _generate_monitors_script(
    monitors: List[dict], param_values: dict
) -> Tuple[List[str], List[dict]]:
    """Generate monitors section."""
    lines: List[str] = []
    lifecycle: List[dict] = []

    if not monitors:
        lines.append("# === Monitors ===")
        lines.append("# No monitors defined")
        lines.append("")
        return lines, lifecycle

    lines.append("# === Monitors ===")
    for mon in monitors:
        name = mon.get("name", "")
        mon_type = mon.get("type", "")
        props = mon.get("properties", {})

        lines.append("")
        lines.append(f"# Monitor: {name} ({mon_type})")
        lines.append("addmonitor;")
        lines.append(f'set("name", {quote_lsf_string(name)});')
        for prop_name, prop_value in props.items():
            resolved = _compile_expression(prop_value, param_values)
            lines.append(f'set({quote_lsf_string(prop_name)}, {resolved});')

        lifecycle.append({
            "name": name,
            "type": "monitor",
            "monitor_type": mon_type,
        })

    lines.append("")
    return lines, lifecycle


def compile_recipe(recipe: dict) -> dict:
    """Validate, normalize, and compile a device recipe.

    Returns a compile report with fingerprints, the generated Lumerical
    script, object lifecycle, and assumptions report.
    """
    # ── Validate first ───────────────────────────────────────────────────

    validation = validate_recipe(recipe)
    if not validation["ok"]:
        return {
            "ok": False,
            "recipe_fingerprint": "",
            "compile_fingerprint": "",
            "script_sha256": "",
            "script": "",
            "object_lifecycle": [],
            "assumptions_report": [],
            "raw_hook_hashes": {},
            "warnings": validation["warnings"],
            "errors": validation["errors"],
        }

    normalized = validation["normalized_recipe"]
    param_values = _resolve_param_values(normalized["parameters"])

    # ── Fingerprint the normalized recipe ────────────────────────────────

    recipe_fingerprint = fingerprint_json(normalized)

    # ── Build raw hook hashes ────────────────────────────────────────────

    pre_run = normalized.get("pre_run", "")
    post_run = normalized.get("post_run", "")
    raw_hook_hashes = {
        "pre_run": _sha256_hex(pre_run),
        "post_run": _sha256_hex(post_run),
    }

    # ── Generate script sections in compilation order ────────────────────

    script_parts: List[str] = []
    object_lifecycle: List[dict] = []

    # Compilation order per spec:
    #   1. pre_geometry (raw hook)
    #   2. materials
    #   3. geometry
    #   4. post_geometry (raw hook)
    #   5. simulation region
    #   6. boundaries
    #   7. mesh
    #   8. sources
    #   9. monitors
    #  10. save model

    # 1. pre_geometry hook (not executed in build-only mode)
    script_parts.append("# === Pre-Geometry Hook ===")
    if pre_run.strip():
        script_parts.append("# (not executed in build-only mode)")
        script_parts.append(pre_run.strip())
    else:
        script_parts.append("# No pre_geometry hook")
    script_parts.append("")

    # 2. materials
    mat_lines, mat_lifecycle = _generate_material_script(
        normalized["materials"], param_values
    )
    script_parts.extend(mat_lines)
    object_lifecycle.extend(mat_lifecycle)

    # 3. geometry
    geo_lines, geo_lifecycle = _generate_geometry_script(
        normalized["geometry"], param_values
    )
    script_parts.extend(geo_lines)
    object_lifecycle.extend(geo_lifecycle)

    # 4. post_geometry hook
    script_parts.append("# === Post-Geometry Hook ===")
    if post_run.strip():
        script_parts.append("# (not executed in build-only mode)")
        script_parts.append(post_run.strip())
    else:
        script_parts.append("# No post_geometry hook")
    script_parts.append("")

    # 5. simulation region
    sim_lines, sim_lifecycle = _generate_simulation_region_script()
    script_parts.extend(sim_lines)
    object_lifecycle.extend(sim_lifecycle)

    # 6. boundaries
    script_parts.extend(_generate_boundaries_script())

    # 7. mesh
    script_parts.extend(_generate_mesh_script())

    # 8. sources
    src_lines, src_lifecycle = _generate_sources_script(
        normalized.get("sources", []), param_values
    )
    script_parts.extend(src_lines)
    object_lifecycle.extend(src_lifecycle)

    # 9. monitors
    mon_lines, mon_lifecycle = _generate_monitors_script(
        normalized.get("monitors", []), param_values
    )
    script_parts.extend(mon_lines)
    object_lifecycle.extend(mon_lifecycle)

    # 10. save model
    script_parts.append("# === Save Model ===")
    script_parts.append('save("device_model");')
    script_parts.append("")

    # ── Assemble script ──────────────────────────────────────────────────

    header = [
        "# ============================================================",
        "# FDTD Device Recipe — Compiled Script",
        f"# Recipe fingerprint: {recipe_fingerprint}",
        "# ============================================================",
        "",
    ]
    script = "\n".join(header + script_parts)

    # ── Compute fingerprints ─────────────────────────────────────────────

    script_sha256 = _sha256_hex(script)
    assumptions_report = list(normalized.get("assumptions", []))

    compile_data = {
        "recipe_fingerprint": recipe_fingerprint,
        "script_sha256": script_sha256,
        "assumptions_report": assumptions_report,
        "raw_hook_hashes": raw_hook_hashes,
        "object_lifecycle": object_lifecycle,
    }
    compile_fingerprint = fingerprint_json(compile_data)

    return {
        "ok": True,
        "recipe_fingerprint": recipe_fingerprint,
        "compile_fingerprint": compile_fingerprint,
        "script_sha256": script_sha256,
        "script": script,
        "object_lifecycle": object_lifecycle,
        "assumptions_report": assumptions_report,
        "raw_hook_hashes": raw_hook_hashes,
        "warnings": validation["warnings"],
    }


def _sha256_hex(content: str) -> str:
    """Return ``sha256:<hex>`` for a string."""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
