"""`labcheck` must pass clean artifacts and fail loudly on corrupted ones."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

from isaac_starter_lab.cli import build_check_parser
from isaac_starter_lab.grading import run_check_command, run_checks
from isaac_starter_lab.scene.pipeline import run_scene_command

ROOT = Path(__file__).resolve().parents[1]


def _prepare_scene(tmp_path: Path) -> Path:
    shutil.copytree(ROOT / "usd", tmp_path / "usd")
    args = SimpleNamespace(
        seed=7,
        out="artifacts/scene_seed7.usda",
        n_cubes=None,
        render="artifacts/ex2_frame.png",
        force=True,
        root=str(tmp_path),
    )
    assert run_scene_command(args) == 0
    return tmp_path


def test_env_check_passes_on_repository():
    report = run_checks(ROOT, "env")
    assert report["passed"] is True
    assert report["count"] > 5


def test_scene_check_passes_and_rejects_corruption(tmp_path):
    root = _prepare_scene(tmp_path)
    assert run_checks(root, "ex1")["passed"] is True

    scene = root / "artifacts" / "scene_seed7.usda"
    text = scene.read_text()
    assert "(0.05, 0.05, 0.05)" in text
    scene.write_text(text.replace("(0.05, 0.05, 0.05)", "(0.05, 0.05, 0.06)", 1))
    report = run_checks(root, "ex1")
    assert report["passed"] is False
    failed = {check["name"] for check in report["checks"] if not check["passed"]}
    assert "stage_hash" in failed
    assert any("never hand-edit" in check["hint"] for check in report["checks"])


def test_missing_artifacts_fail_without_traceback(tmp_path):
    report = run_checks(tmp_path, "ex1")
    assert report["passed"] is False
    assert any(check["name"] == "file_scene_seed7.usda" for check in report["checks"])
    assert all(check["hint"] for check in report["checks"] if not check["passed"])


def test_malformed_metadata_is_reported(tmp_path):
    root = _prepare_scene(tmp_path)
    (root / "artifacts" / "scene_seed7.meta.json").write_text("{not json")
    report = run_checks(root, "ex1")
    assert report["passed"] is False
    assert any(check["name"] == "meta_json" for check in report["checks"])


def test_ex2_detects_accuracy_and_notimplemented_stub(tmp_path, monkeypatch):
    root = _prepare_scene(tmp_path)
    assert run_checks(root, "ex2")["passed"] is True

    def unavailable(*_args, **_kwargs):
        raise NotImplementedError("detect_cubes is not implemented yet")

    monkeypatch.setattr("isaac_starter_lab.grading.detect_cubes", unavailable)
    report = run_checks(root, "ex2")
    assert report["passed"] is False
    assert any(check["name"] == "detect_cubes" for check in report["checks"])


def test_stale_episode_summary_is_rejected(tmp_path):
    episode = tmp_path / "artifacts" / "episodes" / "seed_7"
    episode.mkdir(parents=True)
    (episode / "summary.json").write_text(
        json.dumps({"schema": "isaac_starter_lab.episode_summary.v0", "ticks": 12})
    )
    report = run_checks(tmp_path, "ex3")
    assert report["passed"] is False
    schema = next(check for check in report["checks"] if check["name"] == "schema")
    assert "Stale episode artifact" in schema["hint"]


def test_short_dataset_is_rejected(tmp_path):
    dataset = tmp_path / "datasets" / "dr"
    dataset.mkdir(parents=True)
    (dataset / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "isaac_starter_lab.dr_dataset.v1",
                "count": 1,
                "n_cubes": 5,
                "entries": [],
                "dataset_hash": "0" * 64,
            }
        )
    )
    report = run_checks(tmp_path, "ex4")
    assert report["passed"] is False
    count = next(check for check in report["checks"] if check["name"] == "count")
    assert count["passed"] is False


def test_corrupt_manifest_does_not_crash(tmp_path):
    dataset = tmp_path / "datasets" / "dr"
    dataset.mkdir(parents=True)
    (dataset / "manifest.json").write_text("{broken")
    report = run_checks(tmp_path, "ex4")
    assert report["passed"] is False
    assert report["checks"]


def test_check_command_returns_nonzero_and_writes_report(tmp_path, capsys):
    args = build_check_parser().parse_args(
        ["ex1", "--root", str(tmp_path), "--json-out", str(tmp_path / "labcheck.json")]
    )
    assert run_check_command(args) == 1
    output = capsys.readouterr().out
    assert "RESULT: FAIL" in output
    report = json.loads((tmp_path / "labcheck.json").read_text())
    assert report["passed"] is False
    assert report["failed"] >= 1
