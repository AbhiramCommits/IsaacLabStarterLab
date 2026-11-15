#!/usr/bin/env python3
"""Turn an Isaac Lab rsl_rl training log into a small JSON summary.

    python scripts/parse_isaac_lab_log.py /tmp/train_long.log --out results/gpu/isaac_lab_ppo.json

Only the per-iteration block that rsl_rl prints is parsed; nothing is
estimated.  Missing fields stay ``null`` so a partial log is visible as such.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;]*m")
FIELDS = {
    "reward": "Mean reward",
    "episode_length": "Mean episode length",
    "steps_per_second": "Steps per second",
    "total_steps": "Total steps",
    "reaching": "Episode_Reward/reaching",
    "lifting": "Episode_Reward/lifting",
    "grasping": "Episode_Reward/grasping",
    "placing": "Episode_Reward/placing",
    "success": "Episode_Termination/success",
    "time_out": "Episode_Termination/time_out",
    "dropped": "Episode_Termination/dropped",
}


def _value(body: str, label: str) -> float | None:
    match = re.search(rf"{re.escape(label)}:\s*(-?[0-9][0-9.eE+-]*)", body)
    return float(match.group(1)) if match else None


def parse(text: str) -> dict[str, object]:
    text = ANSI.sub("", text)
    parts = re.split(r"Learning iteration (\d+)/(\d+)", text)
    records: dict[int, dict[str, float | None]] = {}
    total_iterations = None
    for index in range(1, len(parts), 3):
        iteration = int(parts[index])
        total_iterations = int(parts[index + 1])
        body = parts[index + 2]
        records[iteration] = {name: _value(body, label) for name, label in FIELDS.items()}

    if not records:
        return {"iterations_parsed": 0, "records": {}, "samples": [], "summary": {}}

    last_iteration = max(records)
    last = records[last_iteration]
    successes = [r["success"] for r in records.values() if r["success"] is not None]
    lifts = [r["lifting"] for r in records.values() if r["lifting"] is not None]
    rewards = [r["reward"] for r in records.values() if r["reward"] is not None]
    speeds = [r["steps_per_second"] for r in records.values() if r["steps_per_second"]]
    sample_every = max(1, last_iteration // 15)
    samples = [
        {"iteration": iteration, **records[iteration]}
        for iteration in sorted(records)
        if iteration % sample_every == 0 or iteration == last_iteration
    ]
    return {
        "iterations_parsed": len(records),
        "total_iterations_requested": total_iterations,
        "last_iteration": last_iteration,
        "summary": {
            "reward_first": rewards[0] if rewards else None,
            "reward_last": last["reward"],
            "reward_max": max(rewards) if rewards else None,
            "lifting_last": last["lifting"],
            "lifting_max": max(lifts) if lifts else None,
            "success_last": last["success"],
            "success_max": max(successes) if successes else None,
            "episode_length_last": last["episode_length"],
            "total_steps_last": last["total_steps"],
            "steps_per_second_mean": round(sum(speeds) / len(speeds), 1) if speeds else None,
        },
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    summary = parse(Path(args.log).read_text())
    payload = json.dumps(summary, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(payload + "\n")
        print(f"wrote {args.out}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
