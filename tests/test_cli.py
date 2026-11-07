"""CLI parser contracts and the module dispatcher."""

from __future__ import annotations

import pytest

from isaac_starter_lab.cli import (
    build_check_parser,
    build_dr_parser,
    build_episode_parser,
    build_eval_parser,
    build_quiz_parser,
    build_scene_parser,
    main,
)


def test_scene_parser_defaults():
    args = build_scene_parser().parse_args([])
    assert args.seed == 7
    assert args.out is None
    assert args.render is None
    assert args.force is False


def test_scene_parser_render_and_seed():
    args = build_scene_parser().parse_args(
        ["--seed", "8", "--out", "x.usda", "--render", "x.png", "--force"]
    )
    assert args.seed == 8
    assert args.out == "x.usda"
    assert args.render == "x.png"
    assert args.force is True


def test_episode_parser_uses_environment(monkeypatch):
    monkeypatch.setenv("LAB_BACKEND", "isaac")
    monkeypatch.setenv("LAB_BRIDGE", "ros2")
    args = build_episode_parser().parse_args([])
    assert args.backend == "isaac"
    assert args.bridge == "ros2"
    assert args.max_ticks == 4000


def test_episode_parser_rejects_unknown_backend():
    with pytest.raises(SystemExit):
        build_episode_parser().parse_args(["--backend", "mujoco"])


def test_dr_parser_defaults():
    args = build_dr_parser().parse_args([])
    assert args.seeds == "0-199"
    assert args.out == "datasets/dr"


def test_eval_parser_requires_subcommand():
    with pytest.raises(SystemExit):
        build_eval_parser().parse_args([])
    args = build_eval_parser().parse_args(["perception"])
    assert args.command == "perception"
    episodes = build_eval_parser().parse_args(["episodes", "--seeds", "0-9"])
    assert episodes.seeds == "0-9"


def test_check_parser_choices():
    args = build_check_parser().parse_args(["all"])
    assert args.step == "all"
    assert args.json_out == "results/labcheck.json"
    with pytest.raises(SystemExit):
        build_check_parser().parse_args(["ex9"])


def test_quiz_parser_requires_answers():
    with pytest.raises(SystemExit):
        build_quiz_parser().parse_args([])
    args = build_quiz_parser().parse_args(["--answers", "a.yaml"])
    assert args.answers == "a.yaml"


def test_module_dispatcher_help_and_errors(capsys):
    assert main([]) == 2
    assert "usage:" in capsys.readouterr().out
    assert main(["--help"]) == 0
    assert main(["not-a-command"]) == 2
    assert "unknown command" in capsys.readouterr().err
