"""The full headless pipeline is byte-identical across two clean directories."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_determinism.py"


@pytest.mark.slow
def test_headless_pipeline_is_deterministic(tmp_path):
    out = tmp_path / "determinism.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out",
            str(out),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=1800,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(out.read_text())
    assert report["schema"] == "isaac_starter_lab.determinism.v1"
    assert report["runs"] == 2
    assert report["artifacts_identical"] is True
    assert report["mismatches"] == []
    assert report["artifact_count"] >= 500
    assert report["combined_sha256"][0] == report["combined_sha256"][1]
    assert "IDENTICAL" in result.stdout
