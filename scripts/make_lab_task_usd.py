#!/usr/bin/env python3
"""Generate the Isaac Lab task assets: a robot-free tabletop and the arm USD.

Both files are authored with the same code the GPU backend uses, so the RL
robot is exactly the arm that ran the PhysX sweep and the task table is the
canonical tabletop without the non-simulatable visual robot.

    python scripts/make_lab_task_usd.py

Writes ``usd/lab_task_seed7.usda`` and ``usd/lab_arm.usda``.  The canonical
``usd/tabletop_seed7.usda`` and its pinned hash are never touched.
"""

from __future__ import annotations

from pathlib import Path

from pxr import Usd, UsdGeom

from isaac_starter_lab.config import ArmConfig, SceneConfig
from isaac_starter_lab.scene.build_scene import build_task_stage
from isaac_starter_lab.sim.arm_usd import (
    ARM_ROOT,
    build_runtime_arm,
    make_physics_material,
)

REPO = Path(__file__).resolve().parent.parent
USD_DIR = REPO / "usd"


def write_task_scene(path: Path) -> None:
    stage = build_task_stage(SceneConfig(), seed=7)
    stage.GetRootLayer().Export(str(path))


def write_arm(path: Path) -> None:
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    material = make_physics_material(stage, path=f"{ARM_ROOT}/Looks/PhysicsMat")
    build_runtime_arm(stage, ArmConfig(), material, canonical_robot=None, colliders="jaws")
    stage.SetDefaultPrim(stage.GetPrimAtPath(ARM_ROOT))
    stage.GetRootLayer().Export(str(path))


def main() -> int:
    USD_DIR.mkdir(parents=True, exist_ok=True)
    scene_path = USD_DIR / "lab_task_seed7.usda"
    arm_path = USD_DIR / "lab_arm.usda"
    write_task_scene(scene_path)
    write_arm(arm_path)
    print(f"wrote {scene_path} ({scene_path.stat().st_size} bytes)")
    print(f"wrote {arm_path} ({arm_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
