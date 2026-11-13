#!/usr/bin/env python3
"""Render one RTX frame per DR seed from the pre-authored USD scenes.

Run on the Isaac Sim 6.0 GPU host (``/isaac-sim/python.sh``).  Each stage is
opened in turn; the camera is the stage's own ``/World/Camera`` and the cube
materials are made emissive so RTX frames carry the same saturated colours as
the pinhole DR dataset.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from isaacsim import SimulationApp  # type: ignore[import-not-found]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes", default="usd/rtx_seeds")
    parser.add_argument("--out", default="results/gpu/rtx_frames")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--stop", type=int, default=200)
    args = parser.parse_args()
    scenes = Path(args.scenes)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    app = SimulationApp({"headless": True, "anti_aliasing": 0, "denoiser": False})
    assert app is not None
    import numpy as np
    import omni.usd
    from isaacsim.core.api import SimulationContext  # type: ignore[import-not-found]
    from isaacsim.sensors.camera import Camera  # type: ignore[import-not-found]
    from PIL import Image
    from pxr import Sdf, UsdShade

    context = omni.usd.get_context()
    sim = None
    for seed in range(args.start, args.stop):
        path = scenes / f"seed_{seed:04d}.usda"
        if not path.exists():
            print(f"missing {path}", flush=True)
            continue
        if not context.open_stage(str(path.resolve())):
            print(f"open failed {path}", flush=True)
            continue
        if sim is None:
            sim = SimulationContext(
                physics_dt=1.0 / 240.0,
                rendering_dt=1.0 / 60.0,
                stage_units_in_meters=1.0,
            )
            sim.initialize_physics()
        sim.reset()
        stage = context.get_stage()
        dome = stage.GetPrimAtPath("/World/Lights/DomeLight")
        if dome:
            dome.GetAttribute("inputs:intensity").Set(100.0)
        camera_prim = stage.GetPrimAtPath("/World/Camera")
        if camera_prim:
            camera_prim.GetAttribute("fStop").Set(64.0)
        for color in ("Red", "Green", "Blue", "Yellow", "Magenta"):
            shader = UsdShade.Shader(
                stage.GetPrimAtPath(f"/World/Materials/{color}/PreviewSurface")
            )
            if shader:
                diffuse = shader.GetInput("diffuseColor").Get()
                shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
                    diffuse * 0.6
                )
        camera = Camera(prim_path="/World/Camera", resolution=(640, 480))
        camera.initialize()
        rgba = None
        for _ in range(20):
            sim.render()
            rgba = camera.get_rgba()
            if rgba is not None and np.asarray(rgba).size:
                break
        if rgba is None or not np.asarray(rgba).size:
            print(f"empty frame seed={seed}", flush=True)
        else:
            image = np.asarray(rgba)[..., :3]
            Image.fromarray(image.astype(np.uint8)).save(out / f"seed_{seed:04d}.png")
            print(f"rendered seed={seed} mean={image.reshape(-1, 3).mean(axis=0).round(1).tolist()}", flush=True)
        try:
            camera.destroy()
        except Exception:
            pass
    import os

    os._exit(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
