"""Perception/evaluation aggregation and the eval CLI."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from isaac_starter_lab.datasets.dr import generate_dataset
from isaac_starter_lab.evaluation import (
    _percentiles,
    evaluate_episodes,
    evaluate_perception,
    run_eval_command,
)


@pytest.fixture(scope="module")
def dataset(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("dr-eval")
    generate_dataset(path, [0, 1, 2], overwrite=True, verbose=False)
    return path


def test_percentiles_handles_empty_and_values():
    assert _percentiles([]) == {"mean": 0.0, "p95": 0.0, "max": 0.0, "count": 0}
    result = _percentiles([0.0, 1.0, 2.0, 3.0, 4.0])
    assert result["mean"] == pytest.approx(2.0)
    assert result["p95"] == pytest.approx(3.8)
    assert result["max"] == 4.0
    assert result["count"] == 5


def test_perception_evaluation_on_small_dataset(dataset):
    result = evaluate_perception(dataset, verbose=False)
    assert result["schema"] == "isaac_starter_lab.perception_eval.v1"
    assert result["seeds"] == 3
    assert result["cubes_evaluated"] == 15
    assert result["visible_cubes"] > 0
    assert result["detections"] > 0
    assert result["pixel_error"]["mean"] < 3.0
    assert result["pixel_error"]["count"] == result["true_positives"]
    assert result["error_3d_mm"]["mean"] < 10.0
    assert result["recall"] > 0.8
    assert result["precision"] > 0.5
    assert len(result["worst_seeds"]) <= 5

    again = evaluate_perception(dataset, verbose=False)
    assert again["pixel_error"] == result["pixel_error"]
    assert again["recall"] == result["recall"]


def test_episode_evaluation_and_reason_histogram(dataset, tmp_path):
    result = evaluate_episodes(
        [0, 1],
        episodes_root=tmp_path / "episodes",
        verbose=False,
    )
    assert result["count"] == 2
    assert result["successes"] == 2
    assert result["success_rate"] == 1.0
    assert result["failure_histogram"] == {}
    assert result["cycle_time_s"]["mean"] > 0
    assert result["ticks"]["mean"] > 0
    assert len(result["episodes"]) == 2


def test_eval_cli_writes_both_reports(dataset, tmp_path):
    perception_args = SimpleNamespace(
        command="perception",
        root=str(tmp_path),
        dataset=str(dataset),
        out="results/perception_eval.json",
        pixel_threshold=5.0,
    )
    assert run_eval_command(perception_args) == 0
    report = json.loads((tmp_path / "results/perception_eval.json").read_text())
    assert report["seeds"] == 3

    episode_args = SimpleNamespace(
        command="episodes",
        root=str(tmp_path),
        seeds="0-0",
        backend="kinematic",
        bridge="localbus",
        out="results/episode_sweep.json",
        episodes_root="artifacts/sweeps",
    )
    assert run_eval_command(episode_args) == 0
    sweep = json.loads((tmp_path / "results/episode_sweep.json").read_text())
    assert sweep["count"] == 1
    assert sweep["success_rate"] == 1.0


def test_unknown_eval_command_is_rejected(tmp_path):
    args = SimpleNamespace(command="nonsense", root=str(tmp_path))
    with pytest.raises(ValueError, match="unknown eval command"):
        run_eval_command(args)
