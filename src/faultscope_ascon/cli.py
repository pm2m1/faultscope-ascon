"""Non-destructive command-line entry points for a FaultScope checkout.

Run from the project root with ``uv run faultscope-ascon ...``.
The commands never regenerate or rewrite committed experimental evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def _root() -> Path:
    root = Path.cwd()
    if not (root / "pyproject.toml").is_file() or not (root / "backend" / "research.py").is_file():
        raise ValueError("Run this command from the FaultScope-Ascon repository root")
    return root


def verify_evidence(root: Path) -> bool:
    """Validate pinned Phase 4B, 7A and 7B CSVs without mutating any file."""
    # The pinned Phase 7 hashes have one source of truth: the read-only API.
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from backend.research import CAMPAIGNS
    from experiments.source_provenance import verify_rtl_source

    manifest = json.loads((root / "reports" / "phase5" / "manifest.json").read_text(encoding="utf-8"))
    expected: dict[str, str] = {
        "reports/phase4b_temporal.csv": manifest["campaign_sha256"],
        **{record["path"]: record["sha256"] for record in CAMPAIGNS.values()},
    }
    success = True
    for name, expected_digest in expected.items():
        try:
            actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
        except OSError as exc:
            print(f"FAIL {name}: {exc}")
            success = False
            continue
        matches = actual == expected_digest
        print(f"{'PASS' if matches else 'FAIL'} {name} sha256={actual}")
        success &= matches
    for name, expected_digest in manifest.get("sources_sha256", {}).items():
        relative = f"rtl/{name}"
        try:
            entry = verify_rtl_source(root / relative, expected_digest)
        except (OSError, ValueError) as exc:
            print(f"FAIL {relative}: {exc}")
            success = False
            continue
        print(f"PASS {relative} raw_sha256={entry['raw_sha256']} "
              f"pinned_sha256={expected_digest} match_mode={entry['match_mode']}")

    # Historical source/ref pins are provenance; they need not match current HEAD.
    try:
        pinned = (root / "docs/ascon_reference_commit.txt").read_text(encoding="utf-8").strip()
        ref_ok = pinned == manifest["ascon_reference_commit"]
        print(f"{'PASS' if ref_ok else 'FAIL'} pinned Ascon-C revision {pinned}")
        success &= ref_ok
    except (OSError, KeyError) as exc:
        print(f"FAIL pinned Ascon-C revision: {exc}")
        success = False

    print("Evidence status:", "PASS" if success else "FAIL")
    return success


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="faultscope-ascon",
        description="FaultScope-Ascon research dashboard and read-only evidence tools.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify-evidence", help="Verify committed Phase 4B/7A/7B CSV digests")
    serve = sub.add_parser("serve", help="Serve the local read-only FastAPI dashboard backend")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true", help="Enable development reload")
    args = parser.parse_args(argv)
    try:
        root = _root()
        if args.command == "verify-evidence":
            return 0 if verify_evidence(root) else 1
        if args.command == "serve":
            import uvicorn
            uvicorn.run("backend.api:app", host=args.host, port=args.port, reload=args.reload)
            return 0
    except (ValueError, OSError, KeyError, json.JSONDecodeError, ImportError) as exc:
        print(f"FaultScope error: {exc}", file=sys.stderr)
        return 1
    return 2
