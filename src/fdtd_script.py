"""Safe Lumerical script string formatting helpers.

Pure Python — no Lumerical or Windows APIs required.
"""


def quote_lsf_string(value: str) -> str:
    """Escape backslashes and double-quotes, then wrap in double-quotes.

    >>> quote_lsf_string('hello "world"')
    '"hello \\\\"world\\\\""'
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def format_lsf_value(value) -> str:
    """Convert a Python value to its Lumerical script literal.

    * ``True`` / ``False``  → ``"1"`` / ``"0"``
    * ``int`` / ``float``   → ``repr(value)`` (full precision for floats)
    * ``str``               → ``quote_lsf_string(value)``
    * ``list``              → ``"{" + ", ".join(...) + "}"`` (recursive)
    """
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return quote_lsf_string(value)
    if isinstance(value, list):
        return "{" + ", ".join(format_lsf_value(v) for v in value) + "}"
    raise TypeError(f"Unsupported LSF value type: {type(value).__name__}")
