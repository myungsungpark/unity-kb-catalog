"""Prepare a release candidate from a fully validated draft catalog.

The source tree stays unchanged. Release status is changed ONLY in output
after the original draft has passed the existing schema validator.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def prepare(root, destination, requested_version):
    root = Path(root)
    destination = Path(destination)
    if not isinstance(requested_version, str) or not VERSION.fullmatch(requested_version):
        raise ValueError("invalid catalog version")
    original = json.loads((root / "catalog/unity-kb-catalog.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if (original.get("catalog_status") != "draft" or manifest.get("catalog_status") != "draft"
            or original.get("catalog_version") != requested_version
            or manifest.get("catalog_version") != requested_version):
        raise ValueError("release version and draft source must match")
    if manifest.get("catalog_file") != "catalog/unity-kb-catalog.json":
        raise ValueError("invalid catalog path")
    source_check = subprocess.run(
        [sys.executable, str(root / "scripts/validate_catalog.py")],
        cwd=root, capture_output=True, text=True, check=False
    )
    if source_check.returncode or "VALIDATION PASSED" not in source_check.stdout:
        raise ValueError("source catalog validation failed: " + source_check.stdout + source_check.stderr)
    # Validator's draft-only enforcement is replaced exclusively by this
    # verified in-memory transition; do not weaken the main validator.
    released = dict(original)
    released["catalog_status"] = "released"
    if not released.get("articles") or any(
        not isinstance(article, dict) or article.get("matching", {}).get("enabled") is not False
        for article in released["articles"]
    ):
        raise ValueError("invalid article matching policy")
    destination.mkdir(parents=True, exist_ok=True)
    candidate = destination / "unity-kb-catalog.json"
    candidate.write_text(json.dumps(released, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return candidate


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--version", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    print(prepare(ROOT, args.out, args.version))


if __name__ == "__main__":
    main()
