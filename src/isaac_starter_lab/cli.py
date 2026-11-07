"""Console entry points for the lab.

Every console script has one small ``argparse`` entry here.  Parsers are the
public command contract: the Makefile, the lab guide and CI all call them, so
arguments are kept stable while the implementation behind them grows.

At scaffold time each entry point prints its resolved arguments.  Later steps
replace the body with the real implementation while keeping the same flags.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from typing import Any

DEFAULT_SEED = 7
DEFAULT_SCENE_OUT = "artifacts/scene_seed7.usda"
DEFAULT_DR_OUT = "datasets/dr"
DEFAULT_EPISODE_OUT = "artifacts/episodes/seed_{seed}"


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        default=".",
        help="repository root used to resolve relative paths (default: .)",
    )


def build_scene_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lab-scene",
        description="Generate the deterministic OpenUSD tabletop scene.",
    )
    p.add_argument("--seed", type=int, default=DEFAULT_SEED, help="teaching seed (default: 7)")
    p.add_argument("--out", default=None, help="output .usda path")
    p.add_argument("--n-cubes", type=int, default=None, help="override the number of cubes")
    p.add_argument("--render", default=None, help="also write a 640x480 PNG of the scene")
    p.add_argument("--force", action="store_true", help="overwrite an existing output file")
    _add_common(p)
    return p


def build_dr_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lab-dr",
        description="Render the seeded domain-randomization synthetic dataset.",
    )
    p.add_argument("--seeds", default="0-199", help="inclusive seed range, e.g. 0-199 or 3")
    p.add_argument("--out", default=DEFAULT_DR_OUT, help="dataset directory")
    p.add_argument("--n-cubes", type=int, default=None, help="override cubes per frame")
    p.add_argument("--overwrite", action="store_true", help="regenerate existing seeds")
    _add_common(p)
    return p


def build_episode_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lab-episode",
        description="Run one perception -> controller pick-and-place episode.",
    )
    p.add_argument("--seed", type=int, default=DEFAULT_SEED, help="episode seed")
    p.add_argument(
        "--backend",
        default=os.environ.get("LAB_BACKEND", "kinematic"),
        choices=("kinematic", "isaac"),
        help="simulation backend (default: $LAB_BACKEND or kinematic)",
    )
    p.add_argument(
        "--bridge",
        default=os.environ.get("LAB_BRIDGE", "localbus"),
        choices=("localbus", "ros2"),
        help="transport backend (default: $LAB_BRIDGE or localbus)",
    )
    p.add_argument("--out", default=None, help="episode output directory")
    p.add_argument("--target-color", default=None, help="cube colour to pick (default: seeded)")
    p.add_argument("--max-ticks", type=int, default=4000, help="hard episode tick limit")
    _add_common(p)
    return p


def build_eval_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lab-eval",
        description="Evaluate perception and/or pick-and-place episodes.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    perc = sub.add_parser("perception", help="score detect_cubes on the DR dataset")
    perc.add_argument("--dataset", default=DEFAULT_DR_OUT, help="dataset directory")
    perc.add_argument("--out", default="results/perception_eval.json", help="result JSON path")
    perc.add_argument("--pixel-threshold", type=float, default=5.0, help="match threshold, px")
    _add_common(perc)

    eps = sub.add_parser("episodes", help="sweep episodes and report success rate")
    eps.add_argument("--seeds", default="0-99", help="inclusive seed range")
    eps.add_argument("--backend", default=os.environ.get("LAB_BACKEND", "kinematic"))
    eps.add_argument("--bridge", default=os.environ.get("LAB_BRIDGE", "localbus"))
    eps.add_argument("--out", default="results/episode_sweep.json", help="result JSON path")
    eps.add_argument(
        "--episodes-root",
        default="artifacts/sweeps",
        help="scratch directory for sweep episodes",
    )
    _add_common(eps)
    return p


def build_check_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="labcheck",
        description="Grade the learner's artifacts step by step.",
    )
    p.add_argument(
        "step",
        choices=("env", "ex1", "ex2", "ex3", "ex4", "all"),
        help="which check to run",
    )
    p.add_argument("--root", default=".", help="repository root containing the artifacts")
    p.add_argument("--json-out", default="results/labcheck.json", help="machine-readable report")
    return p


def build_quiz_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lab-quiz",
        description="Grade the lab knowledge checks.",
    )
    p.add_argument("--answers", required=True, help="YAML file mapping question id to answer")
    p.add_argument(
        "--questions",
        default="lab/knowledge_checks.yaml",
        help="question bank (default: lab/knowledge_checks.yaml)",
    )
    p.add_argument("--out", default="artifacts/quiz_result.json", help="result JSON path")
    _add_common(p)
    return p


def _print_resolved(command: str, args: argparse.Namespace) -> int:
    payload: dict[str, Any] = {"command": command}
    for key, value in sorted(vars(args).items()):
        if key == "command":
            continue
        payload[key] = value
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# Entry points.  Implementations land in later steps; the signature stays.
# ---------------------------------------------------------------------------


def run_scene(args: argparse.Namespace) -> int:
    from .scene.pipeline import run_scene_command

    return run_scene_command(args)


def run_dr(args: argparse.Namespace) -> int:
    from .datasets.dr import run_dr_command

    return run_dr_command(args)


def run_episode(args: argparse.Namespace) -> int:
    from .episode import run_episode_command

    return run_episode_command(args)


def run_eval(args: argparse.Namespace) -> int:
    from .evaluation import run_eval_command

    return run_eval_command(args)


def run_check(args: argparse.Namespace) -> int:
    from .grading import run_check_command

    return run_check_command(args)


def run_quiz(args: argparse.Namespace) -> int:
    from .quiz import run_quiz_command

    return run_quiz_command(args)


def scene_main(argv: Sequence[str] | None = None) -> int:
    return run_scene(build_scene_parser().parse_args(argv))


def dr_main(argv: Sequence[str] | None = None) -> int:
    return run_dr(build_dr_parser().parse_args(argv))


def episode_main(argv: Sequence[str] | None = None) -> int:
    return run_episode(build_episode_parser().parse_args(argv))


def eval_main(argv: Sequence[str] | None = None) -> int:
    return run_eval(build_eval_parser().parse_args(argv))


def check_main(argv: Sequence[str] | None = None) -> int:
    return run_check(build_check_parser().parse_args(argv))


def quiz_main(argv: Sequence[str] | None = None) -> int:
    return run_quiz(build_quiz_parser().parse_args(argv))


_COMMANDS = {
    "scene": build_scene_parser,
    "dr": build_dr_parser,
    "episode": build_episode_parser,
    "eval": build_eval_parser,
    "check": build_check_parser,
    "quiz": build_quiz_parser,
}
_RUNNERS = {
    "scene": run_scene,
    "dr": run_dr,
    "episode": run_episode,
    "eval": run_eval,
    "check": run_check,
    "quiz": run_quiz,
}


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m isaac_starter_lab.cli <command> ...`` dispatcher."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: python -m isaac_starter_lab.cli {scene,dr,episode,eval,check,quiz} ...")
        return 0 if argv else 2
    command, rest = argv[0], argv[1:]
    if command not in _COMMANDS:
        print(f"unknown command {command!r}", file=sys.stderr)
        return 2
    args = _COMMANDS[command]().parse_args(rest)
    return _RUNNERS[command](args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
