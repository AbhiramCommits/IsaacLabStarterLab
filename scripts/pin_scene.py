#!/usr/bin/env python3
"""Regenerate the canonical teaching scene and pin its hash.

Maintainers run this after an intentional scene change::

    .venv/bin/python scripts/pin_scene.py

It rewrites ``usd/tabletop_seed7.usda`` and ``usd/EXPECTED_HASHES.json`` from
the current builder.  The lab guide tells learners to *compare* against the
pinned hash, never to update it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from isaac_starter_lab.config import CameraIntrinsics, SceneConfig  # noqa: E402
from isaac_starter_lab.scene.build_scene import build_stage, sample_cube_layout  # noqa: E402
from isaac_starter_lab.scene.hashing import stage_hash  # noqa: E402


def main() -> int:
    seed = 7
    cfg = SceneConfig()
    intrinsics = CameraIntrinsics()
    stage = build_stage(cfg, seed, intrinsics)
    digest = stage_hash(stage)
    prim_count = len(list(stage.Traverse()))
    placements = sample_cube_layout(cfg, seed)

    usd_dir = ROOT / "usd"
    usd_dir.mkdir(parents=True, exist_ok=True)
    out = usd_dir / f"tabletop_seed{seed}.usda"
    stage.GetRootLayer().Export(str(out))

    meta = {
        "schema": "isaac_starter_lab.scene_meta.v1",
        "seed": seed,
        "hash": digest,
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
    (usd_dir / f"tabletop_seed{seed}.meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    expected = {
        "schema": "isaac_starter_lab.expected_hashes.v1",
        "scenes": {
            f"tabletop_seed{seed}": {
                "seed": seed,
                "file": out.name,
                "hash": digest,
                "prim_count": prim_count,
                "n_cubes": cfg.n_cubes,
            }
        },
    }
    (usd_dir / "EXPECTED_HASHES.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {out}")
    print(f"hash: {digest}")
    print(f"prims: {prim_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
