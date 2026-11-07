#!/usr/bin/env python3
"""Regenerate the committed reference screenshots in ``docs/img/``.

These are real lab outputs, not mockups: the scene frame comes from the same
software renderer used by the lab, the episode frames come from a seed-7 run,
and the DR sample is copied from the committed dataset.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image, ImageDraw  # noqa: E402

from isaac_starter_lab.config import CameraIntrinsics, SceneConfig  # noqa: E402
from isaac_starter_lab.episode import run_episode  # noqa: E402
from isaac_starter_lab.perception import detect_cubes  # noqa: E402
from isaac_starter_lab.render.pinhole import CameraPose, project_point, render_scene  # noqa: E402
from isaac_starter_lab.scene.build_scene import sample_cube_layout  # noqa: E402


def main() -> int:
    out = ROOT / "docs" / "img"
    out.mkdir(parents=True, exist_ok=True)
    cfg = SceneConfig()
    intrinsics = CameraIntrinsics()
    placements = sample_cube_layout(cfg, 7)
    image = render_scene(
        cubes=[(p.position, p.rgb) for p in placements],
        scene=cfg,
        intrinsics=intrinsics,
    )
    Image.fromarray(image).save(out / "scene_seed7.png")

    pose = CameraPose.from_look_at(cfg.camera_position, cfg.camera_look_at, cfg.camera_up)
    overlay = Image.fromarray(image).convert("RGB")
    draw = ImageDraw.Draw(overlay)
    for placement in placements:
        detection = detect_cubes(image, placement.color_name)[0]
        draw.ellipse(
            (
                detection.u - 6,
                detection.v - 6,
                detection.u + 6,
                detection.v + 6,
            ),
            outline=(255, 255, 255),
            width=2,
        )
        u, v, _ = project_point(placement.position, pose, intrinsics)
        draw.line((u - 8, v, u + 8, v), fill=(0, 0, 0), width=1)
        draw.line((u, v - 8, u, v + 8), fill=(0, 0, 0), width=1)
        draw.text((detection.u + 9, detection.v - 6), placement.color_name, fill=(255, 255, 255))
    overlay.save(out / "perception_overlay.png")

    summary = run_episode(
        7,
        out_dir=ROOT / "artifacts" / "episodes" / "seed_7",
        verbose=False,
    )
    if not summary["success"]:  # pragma: no cover - build-time guard
        raise SystemExit("seed-7 episode did not succeed; refusing to publish frames")
    shutil.copyfile(
        ROOT / "artifacts" / "episodes" / "seed_7" / "frame_000.png",
        out / "episode_seed7_start.png",
    )
    shutil.copyfile(
        ROOT / "artifacts" / "episodes" / "seed_7" / "frame_final.png",
        out / "episode_seed7_final.png",
    )
    shutil.copyfile(
        ROOT / "datasets" / "dr" / "images" / "seed_0000.png",
        out / "dr_seed_0000.png",
    )
    print(f"wrote reference images to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
