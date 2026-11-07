"""Seeded domain-randomization dataset generation.

Every seed produces one 640x480 frame and one ground-truth label.  The random
variables are deliberately the ones a tabletop perception model must survive:

* cube positions (rejection-sampled, non-overlapping) and palette colours
* dome-light intensity
* camera yaw jitter around the scene centre
* table albedo

The manifest records a sha256 for every image and label plus a dataset-level
hash over those entries, so a regenerated dataset can be compared byte for byte.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from ..config import CameraIntrinsics, SceneConfig
from ..ranges import parse_seed_range
from ..render.pinhole import CameraPose, project_point, render_scene
from ..scene.build_scene import CubePlacement, sample_cube_layout

__all__ = ["generate_dataset", "run_dr_command", "rotate_camera"]

SCHEMA = "isaac_starter_lab.dr_dataset.v1"
LABEL_SCHEMA = "isaac_starter_lab.dr_label.v1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rotate_camera(
    position: tuple[float, float, float],
    look_at: tuple[float, float, float],
    yaw_radians: float,
) -> tuple[float, float, float]:
    """Rotate the camera position around the look-at point about world Z."""
    dx = position[0] - look_at[0]
    dy = position[1] - look_at[1]
    cos_a, sin_a = math.cos(yaw_radians), math.sin(yaw_radians)
    return (
        look_at[0] + cos_a * dx - sin_a * dy,
        look_at[1] + sin_a * dx + cos_a * dy,
        position[2],
    )


def _randomise(seed: int, base: SceneConfig) -> tuple[SceneConfig, list[CubePlacement], float, float]:
    rng = np.random.default_rng(10_000 + seed)
    placements = list(sample_cube_layout(base, seed))
    palette_indices = rng.permutation(len(base.palette))[: len(placements)]
    randomised: list[CubePlacement] = []
    for placement, palette_index in zip(placements, palette_indices, strict=True):
        name, rgb = base.palette[int(palette_index)]
        randomised.append(
            CubePlacement(
                name=placement.name,
                position=placement.position,
                color_name=name,
                rgb=rgb,
            )
        )

    yaw_jitter = math.radians(float(rng.uniform(-8.0, 8.0)))
    camera_position = rotate_camera(base.camera_position, base.camera_look_at, yaw_jitter)
    light = float(rng.uniform(0.65, 1.25))
    jitter = rng.integers(-16, 17, size=3)
    table_color = tuple(int(np.clip(channel + delta, 55, 205)) for channel, delta in zip(base.table_color, jitter, strict=True))
    cfg = SceneConfig(
        table_color=table_color,
        camera_position=camera_position,
        camera_look_at=base.camera_look_at,
        light_intensity=light,
        n_cubes=base.n_cubes,
    )
    return cfg, randomised, light, yaw_jitter


def generate_dataset(
    out_dir: str | Path,
    seeds: list[int],
    *,
    n_cubes: int = 5,
    overwrite: bool = False,
    verbose: bool = True,
) -> dict:
    out = Path(out_dir)
    images_dir = out / "images"
    labels_dir = out / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    base = SceneConfig(n_cubes=n_cubes)
    intrinsics = CameraIntrinsics()
    entries: list[dict] = []

    for position, seed in enumerate(seeds):
        image_path = images_dir / f"seed_{seed:04d}.png"
        label_path = labels_dir / f"seed_{seed:04d}.json"
        if not overwrite and image_path.exists() and label_path.exists():
            entries.append(
                {
                    "seed": seed,
                    "image": f"images/{image_path.name}",
                    "label": f"labels/{label_path.name}",
                    "image_sha256": _sha256_file(image_path),
                    "label_sha256": _sha256_file(label_path),
                }
            )
        else:
            cfg, placements, light, yaw_jitter = _randomise(seed, base)
            pose = CameraPose.from_look_at(cfg.camera_position, cfg.camera_look_at, cfg.camera_up)
            image, ids = render_scene(
                cubes=[(p.position, p.rgb) for p in placements],
                scene=cfg,
                intrinsics=intrinsics,
                camera_position=cfg.camera_position,
                look_at=cfg.camera_look_at,
                table_color=cfg.table_color,
                light_intensity=light,
                return_ids=True,
            )
            Image.fromarray(image).save(image_path)

            cubes = []
            for index, placement in enumerate(placements):
                u, v, depth = project_point(placement.position, pose, intrinsics)
                visible = False
                visible_pixels = int(np.count_nonzero(ids == 2 + index))
                bbox = None
                if math.isfinite(u) and math.isfinite(v) and depth > 0:
                    row = int(round(v))
                    col = int(round(u))
                    if 0 <= row < intrinsics.height and 0 <= col < intrinsics.width:
                        visible = bool(ids[row, col] == 2 + index)
                    rows, cols = np.nonzero(ids == 2 + index)
                    if rows.size:
                        bbox = [int(cols.min()), int(rows.min()), int(cols.max()), int(rows.max())]
                cubes.append(
                    {
                        "name": placement.name,
                        "color": placement.color_name,
                        "rgb": list(placement.rgb),
                        "position": [float(v) for v in placement.position],
                        "pixel_centroid": [float(u), float(v)] if math.isfinite(u) else None,
                        "visible": visible,
                        "visible_pixels": visible_pixels,
                        "bbox": bbox,
                    }
                )

            label = {
                "schema": LABEL_SCHEMA,
                "seed": seed,
                "image": f"images/{image_path.name}",
                "width": intrinsics.width,
                "height": intrinsics.height,
                "n_cubes": n_cubes,
                "cube_size": cfg.cube_size,
                "table_top": cfg.table_top,
                "table_color": [int(v) for v in cfg.table_color],
                "light_intensity": light,
                "camera_yaw_jitter_rad": yaw_jitter,
                "camera": {
                    **pose.to_dict(),
                    "intrinsics": intrinsics.to_dict(),
                },
                "cubes": cubes,
            }
            label_path.write_text(json.dumps(label, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            entries.append(
                {
                    "seed": seed,
                    "image": f"images/{image_path.name}",
                    "label": f"labels/{label_path.name}",
                    "image_sha256": _sha256_file(image_path),
                    "label_sha256": _sha256_file(label_path),
                }
            )
        if verbose and (position + 1) % 25 == 0:
            print(f"  generated {position + 1}/{len(seeds)} seeds")

    dataset_hash = hashlib.sha256(
        json.dumps(
            {"n_cubes": n_cubes, "entries": entries},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    manifest = {
        "schema": SCHEMA,
        "count": len(entries),
        "seeds": seeds,
        "n_cubes": n_cubes,
        "image_size": [intrinsics.width, intrinsics.height],
        "dataset_hash": dataset_hash,
        "entries": entries,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if verbose:
        print(f"dataset: {out}")
        print(f"count: {len(entries)}")
        print(f"dataset_hash: {dataset_hash}")
    return manifest


def run_dr_command(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    seeds = parse_seed_range(args.seeds)
    n_cubes = args.n_cubes if args.n_cubes is not None else SceneConfig().n_cubes
    generate_dataset(out, seeds, n_cubes=n_cubes, overwrite=args.overwrite)
    return 0
