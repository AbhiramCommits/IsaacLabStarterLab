#!/usr/bin/env python3
"""Run the headless lab twice in separate directories and compare artifact hashes.

The comparison covers ``artifacts/`` and ``datasets/dr/`` including every PNG,
label, trajectory, summary and manifest.  Results that legitimately contain
timings or absolute paths (``results/timings.json``, ``results/labcheck.json``)
are excluded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORE = shutil.ignore_patterns(
    ".git",
    ".venv",
    "__pycache__",
    "*.pyc",
    "artifacts",
    "results",
)


def _copy_repo(destination: Path) -> None:
    shutil.copytree(ROOT, destination, ignore=IGNORE)


def _hash_tree(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for base in (root / "artifacts", root / "datasets" / "dr"):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                relative = path.relative_to(root).as_posix()
                hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _combined(hashes: dict[str, str]) -> str:
    payload = "\n".join(f"{name}:{digest}" for name, digest in sorted(hashes.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", default="0-199", help="DR seed range for each run")
    parser.add_argument("--episode-seeds", default="0-99", help="episode seed range")
    parser.add_argument("--keep", action="store_true", help="keep the two temporary trees")
    parser.add_argument("--out", default="results/determinism.json")
    args = parser.parse_args(argv)

    base = Path(tempfile.mkdtemp(prefix="isaaclab-determinism-"))
    run_dirs = [base / "run_a", base / "run_b"]
    started = time.perf_counter()
    hashes = []
    try:
        for run_dir in run_dirs:
            _copy_repo(run_dir)
            command = [
                sys.executable,
                str(ROOT / "scripts" / "run_lab_headless.py"),
                "--root",
                ".",
                "--seeds",
                args.seeds,
                "--episode-seeds",
                args.episode_seeds,
            ]
            result = subprocess.run(
                command,
                cwd=run_dir,
                text=True,
                capture_output=True,
                timeout=1800,
            )
            if result.returncode != 0:
                print(result.stdout)
                print(result.stderr, file=sys.stderr)
                raise RuntimeError(f"headless lab failed in {run_dir}")
            hashes.append(_hash_tree(run_dir))
    finally:
        if not args.keep:
            shutil.rmtree(base, ignore_errors=True)

    first, second = hashes
    mismatches = sorted(
        name
        for name in set(first) | set(second)
        if first.get(name) != second.get(name)
    )
    identical = not mismatches and first == second
    payload = {
        "schema": "isaac_starter_lab.determinism.v1",
        "runs": 2,
        "artifact_count": len(first),
        "artifacts_identical": identical,
        "mismatches": mismatches,
        "combined_sha256": [_combined(first), _combined(second)],
        "dr_seeds": args.seeds,
        "episode_seeds": args.episode_seeds,
        "elapsed_s": time.perf_counter() - started,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"determinism: {len(first)} artifacts, "
        f"{'IDENTICAL' if identical else 'MISMATCH'} ({len(mismatches)} differences)"
    )
    print(f"wrote {out}")
    return 0 if identical else 1


if __name__ == "__main__":
    raise SystemExit(main())
