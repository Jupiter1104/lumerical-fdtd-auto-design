"""Cross-platform helpers for FDTD template probe (Stage B0)."""

import hashlib
import json
import os
from pathlib import Path


PROBE_VERSION = "0.1"


def stable_json(value: dict) -> str:
    """Deterministic JSON with sorted keys, no whitespace, no NaN."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def file_sha256(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path, value: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(str(temporary), str(target))


def probe_fingerprint(probe: dict) -> str:
    """Stable fingerprint that excludes its own field."""
    payload = dict(probe)
    payload.pop("probe_fingerprint", None)
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()
