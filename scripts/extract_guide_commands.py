#!/usr/bin/env python3
"""Execute every ``<!-- test:run -->`` bash block in the lab guide.

The guide is copied to a scratch directory and the blocks run in order with the
current interpreter and console scripts on ``PATH``.  Any non-zero exit fails the
script.  This is the anti-rot check: a command that no longer runs cannot stay in
the guide.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = "<!-- test:run -->"
IGNORE = shutil.ignore_patterns(
    ".git",
    ".venv",
    "__pycache__",
    "*.pyc",
    "artifacts",
    "results",
    "datasets/dr/images",
    "datasets/dr/labels",
)


def extract_blocks(text: str) -> list[str]:
    lines = text.splitlines()
    blocks: list[str] = []
    index = 0
    while index < len(lines):
        if lines[index].strip() != MARKER:
            index += 1
            continue
        cursor = index + 1
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        if cursor >= len(lines) or not lines[cursor].strip().startswith("```bash"):
            raise ValueError(f"marker at line {index + 1} is not followed by a bash block")
        cursor += 1
        block: list[str] = []
        while cursor < len(lines) and lines[cursor].strip() != "```":
            block.append(lines[cursor])
            cursor += 1
        if cursor >= len(lines):
            raise ValueError(f"unterminated bash block after line {index + 1}")
        blocks.append("\n".join(block))
        index = cursor + 1
    return blocks


def _copy_repo(destination: Path) -> None:
    shutil.copytree(ROOT, destination, ignore=IGNORE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guide", default="docs/LAB_GUIDE.md")
    parser.add_argument("--scratch", default=None, help="use this scratch directory")
    parser.add_argument("--keep", action="store_true", help="keep the scratch directory")
    args = parser.parse_args(argv)

    guide_path = (ROOT / args.guide).resolve()
    blocks = extract_blocks(guide_path.read_text(encoding="utf-8"))
    if not blocks:
        print(f"no {MARKER} blocks found in {guide_path}", file=sys.stderr)
        return 1

    scratch = Path(args.scratch) if args.scratch else Path(
        tempfile.mkdtemp(prefix="isaaclab-guide-")
    )
    scratch.mkdir(parents=True, exist_ok=True)
    repo_dir = scratch / "repo"
    _copy_repo(repo_dir)

    env = os.environ.copy()
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    env["PYTHON"] = sys.executable
    env["MPLBACKEND"] = "Agg"
    env.setdefault("PYTHONUNBUFFERED", "1")

    print(f"guide: {guide_path}")
    print(f"scratch: {repo_dir}")
    print(f"blocks: {len(blocks)}")
    started = time.perf_counter()
    failed = False
    try:
        for number, block in enumerate(blocks, start=1):
            first_line = block.strip().splitlines()[0] if block.strip() else "<empty>"
            print(f"\n[{number}/{len(blocks)}] {first_line}")
            block_start = time.perf_counter()
            result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", block],
                cwd=repo_dir,
                env=env,
                text=True,
                capture_output=True,
                timeout=1800,
            )
            print(result.stdout, end="")
            if result.returncode != 0:
                print(result.stderr, file=sys.stderr)
                print(
                    f"BLOCK {number} FAILED with exit {result.returncode}; "
                    f"scratch kept at {scratch}",
                    file=sys.stderr,
                )
                failed = True
                return 1
            print(f"  ok ({time.perf_counter() - block_start:.2f} s)")
    finally:
        if not args.keep and not failed:
            shutil.rmtree(scratch, ignore_errors=True)

    print(
        f"\nall {len(blocks)} guide blocks passed in "
        f"{time.perf_counter() - started:.2f} s"
    )
    if args.keep:
        print(f"scratch kept at {scratch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
