#!/usr/bin/env python3
"""Run the complete CPU headless lab and record per-stage timings.

Stages: scene -> domain randomisation -> episode -> perception evaluation ->
episode sweep -> labcheck.  The working tree is cleaned of generated artifacts
at the start, so every run is a real end-to-end reproduction.

The timings are the only values in ``results/timings.json`` that legitimately
vary between runs; artifact hashes are expected to be identical.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from isaac_starter_lab.datasets.dr import generate_dataset  # noqa: E402
from isaac_starter_lab.episode import run_episode  # noqa: E402
from isaac_starter_lab.evaluation import (  # noqa: E402
    evaluate_episodes,
    evaluate_perception,
)
from isaac_starter_lab.grading import run_checks  # noqa: E402
from isaac_starter_lab.ranges import parse_seed_range  # noqa: E402
from isaac_starter_lab.scene.pipeline import run_scene_command  # noqa: E402


def _clean() -> None:
    shutil.rmtree(Path("artifacts"), ignore_errors=True)
    for relative in ("datasets/dr/images", "datasets/dr/labels"):
        directory = Path(relative)
        directory.mkdir(parents=True, exist_ok=True)
        for path in directory.glob("seed_*"):
            path.unlink()
    manifest = Path("datasets/dr/manifest.json")
    if manifest.exists():
        manifest.unlink()
    for relative in (
        "results/perception_eval.json",
        "results/episode_sweep.json",
        "results/labcheck.json",
        "results/timings.json",
    ):
        path = Path(relative)
        if path.exists():
            path.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="working directory for the lab")
    parser.add_argument("--seeds", default="0-199", help="DR seed range")
    parser.add_argument("--episode-seeds", default="0-99", help="episode seed range")
    parser.add_argument("--skip-clean", action="store_true")
    parser.add_argument("--skip-episodes", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.chdir(root)
    Path("results").mkdir(exist_ok=True)
    Path("artifacts").mkdir(exist_ok=True)
    if not args.skip_clean:
        _clean()

    dr_seeds = parse_seed_range(args.seeds)
    episode_seeds = parse_seed_range(args.episode_seeds)
    stages: list[dict] = []
    all_ok = True

    def run_stage(name: str, func) -> None:
        nonlocal all_ok
        start = time.perf_counter()
        print(f"\n=== stage: {name} ===", flush=True)
        try:
            func()
            ok = True
        except Exception as exc:
            ok = False
            all_ok = False
            print(f"stage {name} FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
            raise
        finally:
            seconds = time.perf_counter() - start
            stages.append({"name": name, "seconds": seconds, "ok": ok})
            print(f"=== {name}: {seconds:.3f} s ===", flush=True)

    def stage_scene() -> None:
        run_scene_command(
            argparse.Namespace(
                seed=7,
                out="artifacts/scene_seed7.usda",
                n_cubes=None,
                render="artifacts/ex2_frame.png",
                force=True,
                root=".",
            )
        )

    def stage_dr() -> None:
        generate_dataset(Path("datasets/dr"), dr_seeds, overwrite=True)

    def stage_episode() -> None:
        summary = run_episode(7, out_dir="artifacts/episodes/seed_7")
        if not summary["success"]:
            raise RuntimeError(f"seed-7 episode failed: {summary['failure_reason']}")

    def stage_perception_eval() -> None:
        result = evaluate_perception(Path("datasets/dr"))
        Path("results/perception_eval.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def stage_episode_eval() -> None:
        if args.skip_episodes:
            return
        result = evaluate_episodes(
            episode_seeds,
            episodes_root="artifacts/sweeps",
        )
        Path("results/episode_sweep.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def stage_labcheck() -> None:
        # The learner-facing gate requires 200 DR seeds.  A reduced sweep used by
        # the determinism test still grades env/ex1/ex2/ex3 but cannot satisfy the
        # dataset-size gate; the full default run always runs ``all``.
        if len(dr_seeds) >= 200:
            report = run_checks(Path("."), "all")
        else:
            print(f"reduced seed set ({len(dr_seeds)}): skipping ex4 dataset-size gate")
            checks: list[dict] = []
            for step in ("env", "ex1", "ex2", "ex3"):
                checks.extend(run_checks(Path("."), step)["checks"])
            report = {
                "schema": "isaac_starter_lab.labcheck.v1",
                "step": "reduced",
                "root": str(Path(".").resolve()),
                "passed": all(check["passed"] for check in checks),
                "count": len(checks),
                "failed": sum(1 for check in checks if not check["passed"]),
                "checks": checks,
            }
        Path("results/labcheck.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if not report["passed"]:
            raise RuntimeError(f"labcheck failed: {report['failed']} checks")

    run_stage("scene", stage_scene)
    run_stage("dr", stage_dr)
    run_stage("episode", stage_episode)
    run_stage("perception_eval", stage_perception_eval)
    run_stage("episode_eval", stage_episode_eval)
    run_stage("labcheck", stage_labcheck)

    payload = {
        "schema": "isaac_starter_lab.timings.v1",
        "stages": stages,
        "total_s": sum(stage["seconds"] for stage in stages),
        "dr_seeds": dr_seeds,
        "episode_seeds": episode_seeds,
        "all_ok": all_ok,
    }
    Path("results/timings.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("\nstage timings")
    for stage in stages:
        print(f"  {stage['name']:<18} {stage['seconds']:8.3f} s")
    print(f"  {'total':<18} {payload['total_s']:8.3f} s")
    print("results/timings.json written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
