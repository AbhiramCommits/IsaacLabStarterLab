"""Implementation of the ``lab-scene`` command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:  # pxr is provided by Kit after SimulationApp starts on the GPU track
    from pxr import Usd
except ImportError:  # pragma: no cover - GPU host before the app starts
    Usd = None

from ..config import CameraIntrinsics, SceneConfig
from .build_scene import CubePlacement, build_stage, sample_cube_layout
from .hashing import HASH_ALGORITHM, stage_hash

__all__ = ["run_scene_command"]


def _meta_path(out: Path) -> Path:
    return out.with_name(f"{out.stem}.meta.json")


def write_meta(
    out: Path,
    seed: int,
    cfg: SceneConfig,
    intrinsics: CameraIntrinsics,
    placements: tuple[CubePlacement, ...],
    digest: str,
    prim_count: int,
) -> Path:
    meta = {
        "schema": "isaac_starter_lab.scene_meta.v1",
        "seed": seed,
        "hash": digest,
        "hash_algorithm": HASH_ALGORITHM,
        "prim_count": prim_count,
        "n_cubes": cfg.n_cubes,
        "cube_size": cfg.cube_size,
        "table_top": cfg.table_top,
        "up_axis": "Z",
        "meters_per_unit": 1.0,
        "scene_file": out.name,
        "camera": intrinsics.to_dict(),
        "cube_poses": [p.to_dict() for p in placements],
    }
    meta_path = _meta_path(out)
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return meta_path


def run_scene_command(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    out = Path(args.out) if args.out else Path(f"artifacts/scene_seed{args.seed}.usda")
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)

    cfg = SceneConfig(n_cubes=args.n_cubes if args.n_cubes is not None else SceneConfig().n_cubes)
    intrinsics = CameraIntrinsics()
    stage = build_stage(cfg, args.seed, intrinsics)
    digest = stage_hash(stage)
    placements = sample_cube_layout(cfg, args.seed)
    prim_count = len(list(stage.Traverse()))

    reused = False
    if out.exists() and not args.force:
        try:
            existing = Usd.Stage.Open(str(out))
            existing_hash = stage_hash(existing) if existing is not None else None
        except Exception:  # a corrupt artifact must never block regeneration
            existing_hash = None
        if existing_hash == digest:
            reused = True
    if not reused:
        stage.GetRootLayer().Export(str(out))

    meta_path = write_meta(out, args.seed, cfg, intrinsics, placements, digest, prim_count)

    if getattr(args, "render", None):
        from PIL import Image

        from ..render.pinhole import render_scene

        frame_path = Path(args.render)
        if not frame_path.is_absolute():
            frame_path = root / frame_path
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        image = render_scene(
            cubes=[(p.position, p.rgb) for p in placements],
            scene=cfg,
            intrinsics=intrinsics,
        )
        Image.fromarray(image).save(frame_path)
        print(f"frame: {frame_path}")

    print(f"scene: {out}")
    print(f"seed: {args.seed}")
    print(f"hash: {digest}")
    print(f"prims: {prim_count}")
    print(f"cubes: {cfg.n_cubes}")
    print(f"meta: {meta_path}")
    print("status: " + ("reused identical artifact" if reused else "wrote stage"))
    return 0
