"""The results collector and guide extractor behave as maintainer tools."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


collect = _load("collect_results", "scripts/collect_results.py")
extractor = _load("extract_guide_commands", "scripts/extract_guide_commands.py")


def test_extract_blocks_requires_marker_and_fence(tmp_path):
    guide = tmp_path / "guide.md"
    guide.write_text(
        "intro\n<!-- test:run -->\n```bash\nlabcheck env\n```\n"
        "<!-- test:run -->\n```bash\nlabcheck ex1\n```\n"
    )
    blocks = extractor.extract_blocks(guide.read_text())
    assert blocks == ["labcheck env", "labcheck ex1"]
    with pytest.raises(ValueError, match="not followed by a bash block"):
        extractor.extract_blocks("<!-- test:run -->\n```python\nprint(1)\n```\n")


def test_collect_results_injects_readme(tmp_path, monkeypatch):
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts/scene_seed7.meta.json").write_text(
        json.dumps({"seed": 7, "hash": "abc", "prim_count": 46})
    )
    (tmp_path / "datasets/dr").mkdir(parents=True)
    (tmp_path / "datasets/dr/manifest.json").write_text(
        json.dumps({"count": 200, "dataset_hash": "def", "n_cubes": 5, "image_size": [640, 480]})
    )
    (tmp_path / "results").mkdir()
    (tmp_path / "results/perception_eval.json").write_text(
        json.dumps(
            {
                "seeds": 200,
                "visible_cubes": 874,
                "pixel_error": {"mean": 1.0, "p95": 3.0},
                "error_3d_mm": {"mean": 3.0, "p95": 12.0},
                "recall": 0.96,
                "precision": 0.86,
            }
        )
    )
    (tmp_path / "results/episode_sweep.json").write_text(
        json.dumps(
            {
                "count": 100,
                "successes": 100,
                "success_rate": 1.0,
                "cycle_time_s": {"mean": 5.1, "p95": 5.4},
                "ticks": {"mean": 300, "max": 350},
                "failure_histogram": {},
            }
        )
    )
    (tmp_path / "results/determinism.json").write_text(
        json.dumps({"runs": 2, "artifact_count": 608, "artifacts_identical": True})
    )
    (tmp_path / "results/timings.json").write_text(
        json.dumps({"stages": [{"name": "scene", "seconds": 0.1}]})
    )
    (tmp_path / "results/labcheck.json").write_text(
        json.dumps({"passed": True, "count": 45})
    )
    (tmp_path / "results/coverage.json").write_text(
        json.dumps({"totals": {"percent_covered": 88.2}})
    )
    (tmp_path / "results/pytest.xml").write_text(
        '<testsuite tests="141" failures="0" errors="0"></testsuite>'
    )
    (tmp_path / "README.md").write_text(
        "before\n<!-- RESULTS:START -->\nold\n<!-- RESULTS:END -->\nafter\n"
    )
    (tmp_path / "learner-testing/cold_runs").mkdir(parents=True)
    (tmp_path / "learner-testing/cold_runs/run_1.md").write_text("cold run")
    (tmp_path / "learner-testing/issues").mkdir(parents=True)
    (tmp_path / "learner-testing/issues/ISSUE-001.md").write_text("Status: fixed")

    monkeypatch.setattr(collect, "ROOT", tmp_path)
    assert collect.main() == 0
    readme = (tmp_path / "README.md").read_text()
    assert "before" in readme and "after" in readme
    assert "608 artifacts" in readme
    assert "88.20%" in readme
    assert "1 cold run, 1 issue filed, 1 fixed" in readme
    summary = json.loads((tmp_path / "results/summary.json").read_text())
    assert summary["determinism"]["artifacts_identical"] is True


def test_collect_results_requires_markers(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text("no markers\n")
    monkeypatch.setattr(collect, "ROOT", tmp_path)
    with pytest.raises(SystemExit):
        collect.main()
