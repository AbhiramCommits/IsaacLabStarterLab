#!/usr/bin/env python3
"""Author one OpenUSD stage per DR seed for the RTX perception comparison.

The pinhole DR dataset has the exact camera, table, light and cube colours in
its label.  This script rebuilds that scene with the same camera/light and
rebinds each cube to its labelled colour, then deactivates the visual robot so
the RTX frame contains only the table, bin and cubes (matching the pinhole
renderer).  Run on a machine with ``pxr``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pxr import Gf, UsdGeom, UsdShade

from isaac_starter_lab.config import SceneConfig
from isaac_starter_lab.scene.build_scene import build_stage


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="datasets/dr")
    parser.add_argument("--out", default="usd/rtx_seeds")
    args = parser.parse_args()
    dataset = Path(args.dataset)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["entries"]:
        label = json.loads((dataset / entry["label"]).read_text(encoding="utf-8"))
        camera = label["camera"]
        cfg = SceneConfig(
            table_color=tuple(int(v) for v in label["table_color"]),
            camera_position=tuple(float(v) for v in camera["position"]),
            camera_look_at=tuple(float(v) for v in camera["look_at"]),
            light_intensity=float(label["light_intensity"]),
            n_cubes=int(label["n_cubes"]),
        )
        stage = build_stage(cfg, int(label["seed"]))
        robot = stage.GetPrimAtPath("/World/Robot")
        if robot:
            robot.SetActive(False)
        for index, cube in enumerate(label["cubes"]):
            prim = stage.GetPrimAtPath(f"/World/Cubes/Cube_{index:02d}")
            color_name = str(cube["color"])
            rgb = [float(v) / 255.0 for v in cube["rgb"]]
            prim.GetAttribute("lab:colorName").Set(color_name)
            UsdGeom.Cube(prim).CreateDisplayColorAttr([Gf.Vec3f(*rgb)])
            material = stage.GetPrimAtPath(f"/World/Materials/{color_name.capitalize()}")
            UsdShade.MaterialBindingAPI.Apply(prim).Bind(UsdShade.Material(material))
        out = out_dir / f"seed_{int(label['seed']):04d}.usda"
        stage.GetRootLayer().Export(str(out))
        print(f"{out} seed={label['seed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
