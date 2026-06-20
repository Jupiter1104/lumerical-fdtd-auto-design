"""Stable JSON serialization and SHA-256 fingerprinting.

Pure-Python helpers that guarantee deterministic output regardless of
dictionary key insertion order.  Used as the foundation for dry-run
script compilation and operation deduplication.
"""

import hashlib
import json


def stable_json_dumps(value) -> str:
    """Return a deterministic JSON string for *value*.

    Keys are sorted, whitespace is minimal, and ASCII is not forced so
    Unicode characters are preserved.  The output is identical for any
    two dictionaries that compare equal, regardless of key-insertion
    order.
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def fingerprint_json(value) -> str:
    """Return ``sha256:<hex>`` for the stable-JSON representation of *value*."""
    digest = hashlib.sha256(
        stable_json_dumps(value).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"
