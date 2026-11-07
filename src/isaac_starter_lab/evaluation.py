"""Perception and episode evaluation producing the numbers in README.md."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
from PIL import Image

from .config import CameraIntrinsics, SceneConfig
from .episode import run_episode
from .perception import detect_cubes
from .ranges import parse_seed_range
from .render.pinhole import CameraPose

__all__ = ["evaluate_perception", "evaluate_episodes", "run_eval_command"]


def _percentiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "p95": 0.0, "max": 0.0, "count": 0}
    array = np.asarray(values, dtype=float)
    return {
        "mean": float(array.mean()),
        "p95": float(np.percentile(array, 95)),
        "max": float(array.max()),
        "count": int(array.size),
    }


def evaluate_perception(
    dataset_dir: str | Path,
    *,
    pixel_threshold: float = 5.0,
    verbose: bool = True,
) -> dict:
    dataset = Path(dataset_dir)
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    pixel_errors: list[float] = []
    errors_3d_mm: list[float] = []
    per_seed = []
    cubes_total = 0
    visible_total = 0
    true_positives = 0
    false_negatives = 0
    detections_total = 0
    matched_detections = 0
    start = time.perf_counter()

    for entry in manifest["entries"]:
        image = np.asarray(Image.open(dataset / entry["image"]).convert("RGB"))
        label = json.loads((dataset / entry["label"]).read_text(encoding="utf-8"))
        intrinsics = CameraIntrinsics.from_dict(label["camera"]["intrinsics"])
        pose = CameraPose.from_dict(label["camera"])
        plane_z = float(label["table_top"]) + float(label["cube_size"]) / 2.0
        scene = SceneConfig(n_cubes=int(label["n_cubes"]))
        seed_pixel_errors = []
        seed_3d_errors = []
        seed_visible = 0
        seed_matched = 0

        for cube in label["cubes"]:
            cubes_total += 1
            gt_u, gt_v = cube["pixel_centroid"]
            detections = detect_cubes(
                image,
                cube["color"],
                scene=scene,
                intrinsics=intrinsics,
                pose=pose,
                plane_z=plane_z,
            )
            detections_total += len(detections)
            best = None
            best_error = float("inf")
            for detection in detections:
                error = math.hypot(detection.u - gt_u, detection.v - gt_v)
                if error < best_error:
                    best = detection
                    best_error = error
            matched = best is not None and best_error <= pixel_threshold
            if matched:
                matched_detections += 1
            if cube["visible"]:
                visible_total += 1
                seed_visible += 1
                if matched:
                    true_positives += 1
                    seed_matched += 1
                    pixel_errors.append(best_error)
                    seed_pixel_errors.append(best_error)
                    error_3d = 1000.0 * float(
                        np.linalg.norm(
                            np.asarray(best.position) - np.asarray(cube["position"], dtype=float)
                        )
                    )
                    errors_3d_mm.append(error_3d)
                    seed_3d_errors.append(error_3d)
                else:
                    false_negatives += 1
            # A detection far from every ground-truth cube would be a false
            # positive; unmatched detections are counted through precision.
        per_seed.append(
            {
                "seed": entry["seed"],
                "visible_cubes": seed_visible,
                "matched_visible": seed_matched,
                "mean_pixel_error": float(np.mean(seed_pixel_errors)) if seed_pixel_errors else None,
            }
        )

    false_positives = detections_total - matched_detections
    recall = true_positives / visible_total if visible_total else 0.0
    precision = matched_detections / detections_total if detections_total else 0.0
    result = {
        "schema": "isaac_starter_lab.perception_eval.v1",
        "dataset": str(dataset),
        "dataset_hash": manifest.get("dataset_hash"),
        "seeds": manifest.get("count", len(manifest["entries"])),
        "cubes_evaluated": cubes_total,
        "visible_cubes": visible_total,
        "detections": detections_total,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "recall": float(recall),
        "precision": float(precision),
        "pixel_threshold": float(pixel_threshold),
        "pixel_error": _percentiles(pixel_errors),
        "error_3d_mm": _percentiles(errors_3d_mm),
        "elapsed_s": float(time.perf_counter() - start),
        "worst_seeds": sorted(
            [s for s in per_seed if s["mean_pixel_error"] is not None],
            key=lambda s: s["mean_pixel_error"],
            reverse=True,
        )[:5],
    }
    if verbose:
        print(f"perception dataset={dataset} seeds={result['seeds']}")
        print(
            f"  pixel error mean={result['pixel_error']['mean']:.3f} px "
            f"p95={result['pixel_error']['p95']:.3f} px"
        )
        print(
            f"  3D error mean={result['error_3d_mm']['mean']:.3f} mm "
            f"p95={result['error_3d_mm']['p95']:.3f} mm"
        )
        print(f"  recall={recall:.4f} precision={precision:.4f}")
    return result


def evaluate_episodes(
    seeds: list[int],
    *,
    backend: str = "kinematic",
    bridge: str = "localbus",
    episodes_root: str | Path = "artifacts/sweeps",
    max_ticks: int = 4000,
    verbose: bool = True,
) -> dict:
    root = Path(episodes_root)
    root.mkdir(parents=True, exist_ok=True)
    summaries = []
    start = time.perf_counter()
    for index, seed in enumerate(seeds):
        summary = run_episode(
            seed,
            backend=backend,
            bridge_name=bridge,
            out_dir=root / f"seed_{seed}",
            max_ticks=max_ticks,
            write_frames=False,
            verbose=False,
        )
        summary["episode_index"] = index
        summaries.append(summary)
        if verbose and (index + 1) % 20 == 0:
            print(f"  episodes {index + 1}/{len(seeds)}")
    successes = sum(1 for s in summaries if s["success"])
    failures = [s for s in summaries if not s["success"]]
    failure_histogram: dict[str, int] = {}
    for summary in failures:
        reason = summary["failure_reason"] or "UNKNOWN"
        failure_histogram[reason] = failure_histogram.get(reason, 0) + 1
    cycle_times = [s["cycle_time_s"] for s in summaries]
    ticks = [s["ticks"] for s in summaries]
    result = {
        "schema": "isaac_starter_lab.episode_sweep.v1",
        "backend": backend,
        "bridge": bridge,
        "seeds": seeds,
        "count": len(seeds),
        "successes": successes,
        "success_rate": successes / len(seeds) if seeds else 0.0,
        "failure_histogram": failure_histogram,
        "cycle_time_s": _percentiles(cycle_times),
        "ticks": {
            "mean": float(np.mean(ticks)) if ticks else 0.0,
            "max": int(max(ticks)) if ticks else 0,
        },
        "elapsed_s": float(time.perf_counter() - start),
        "episodes": summaries,
    }
    if verbose:
        print(f"episodes count={len(seeds)} backend={backend} bridge={bridge}")
        print(f"  success_rate={result['success_rate']:.4f} ({successes}/{len(seeds)})")
        print(
            f"  cycle mean={result['cycle_time_s']['mean']:.3f} s "
            f"p95={result['cycle_time_s']['p95']:.3f} s"
        )
        print(f"  failures={failure_histogram}")
    return result


def _write(path: str | Path, payload: dict, root: Path) -> Path:
    out = Path(path)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def run_eval_command(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if args.command == "perception":
        dataset = Path(args.dataset)
        if not dataset.is_absolute():
            dataset = root / dataset
        result = evaluate_perception(dataset, pixel_threshold=args.pixel_threshold)
        out = _write(args.out, result, root)
        print(f"  wrote {out}")
        return 0
    if args.command == "episodes":
        seeds = parse_seed_range(args.seeds)
        episodes_root = Path(args.episodes_root)
        if not episodes_root.is_absolute():
            episodes_root = root / episodes_root
        result = evaluate_episodes(
            seeds,
            backend=args.backend,
            bridge=args.bridge,
            episodes_root=episodes_root,
        )
        out = _write(args.out, result, root)
        print(f"  wrote {out}")
        return 0
    raise ValueError(f"unknown eval command {args.command!r}")
