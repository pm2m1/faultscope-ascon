"""Verify pinned RTL bytes with an explicit, narrow checkout line-ending policy.

Raw SHA-256 remains the provenance of the actual input. Only CRLF -> LF is
allowed for comparison with an existing LF pin; no whitespace, encoding, BOM,
comment, or logic normalization is performed. Campaign/artifact hashes never
use this policy.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def verify_rtl_source(path: Path, pinned_sha256: str) -> dict[str, str]:
    source = path.read_bytes()
    raw = hashlib.sha256(source).hexdigest()
    lf = hashlib.sha256(source.replace(b"\r\n", b"\n")).hexdigest()
    if raw == pinned_sha256:
        mode = "raw"
    elif b"\r\n" in source and lf == pinned_sha256:
        mode = "CRLF-to-LF"
    else:
        raise ValueError(f"RTL source hash differs from historical pin: {path.name}")
    return {"raw_sha256": raw, "lf_sha256": lf,
            "pinned_sha256": pinned_sha256, "match_mode": mode}
