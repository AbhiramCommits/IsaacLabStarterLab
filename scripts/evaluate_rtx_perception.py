#!/usr/bin/env python3
"""Compare pinhole and RTX perception on the same DR labels."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from isaac_starter_lab.evaluation import evaluate_perception


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="datasets/dr")
    parser.add_argument("--frames", default="results/gpu/rtx_frames")
    parser.add_argument("--out", default="results/gpu/rtx_perception.json")
    args = parser.parse_args()
    dataset = Path(args.dataset)
    frames = Path(args.frames)
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "images").mkdir()
        (tmp_path / "labels").mkdir()
        entries = []
        for entry in manifest["entries"]:
            seed = int(entry["seed"])
            frame = frames / f"seed_{seed:04d}.png"
            label = dataset / entry["label"]
            if not frame.exists():
                continue
            shutil.copy(frame, tmp_path / "images" / frame.name)
            shutil.copy(label, tmp_path / "labels" / label.name)
            entries.append(
                {
                    "seed": seed,
                    "image": f"images/{frame.name}",
                    "label": f"labels/{label.name}",
                }
            )
        (tmp_path / "manifest.json").write_text(
            json.dumps({"count": len(entries), "entries": entries}), encoding="utf-8"
        )
        rtx = evaluate_perception(tmp_path, verbose=True)
    pinhole_path = Path("results/perception_eval.json")
    pinhole = json.loads(pinhole_path.read_text(encoding="utf-8")) if pinhole_path.exists() else {}
    result = {
        "schema": "isaac_starter_lab.rtx_perception.v1",
        "frames": len(list(frames.glob("seed_*.png"))),
        "rtx": rtx,
        "pinhole": {
            key: pinhole.get(key)
            for key in (
                "seeds",
                "visible_cubes",
                "detections",
                "true_positives",
                "false_positives",
                "false_negatives",
                "recall",
                "precision",
                "pixel_error",
                "error_3d_mm",
            )
        },
        "note": "Same DR labels, camera and cube layout; pinhole uses the CPU ray caster, RTX uses Isaac Sim 6.0.",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
