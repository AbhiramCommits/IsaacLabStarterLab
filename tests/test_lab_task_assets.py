"""The Isaac Lab task assets: robot-free table and the runtime arm USD."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from pxr import Usd, UsdPhysics

from isaac_starter_lab.config import ArmConfig, SceneConfig
from isaac_starter_lab.scene.build_scene import build_task_stage
from isaac_starter_lab.sim.arm_usd import ARM_ROOT

REPO = Path(__file__).resolve().parents[1]
USD_DIR = REPO / "usd"
SCRIPT = REPO / "scripts" / "make_lab_task_usd.py"

EXPECTED_JOINTS = {
    "joint_base_yaw",
    "joint_shoulder",
    "joint_elbow",
    "joint_wrist_pitch",
    "joint_wrist_roll",
    "jaw_joint",
}


def _load_generator():
    spec = importlib.util.spec_from_file_location("make_lab_task_usd", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_task_stage_has_no_robot_and_no_cubes() -> None:
    stage = build_task_stage(SceneConfig(), seed=7)
    paths = {str(prim.GetPath()) for prim in stage.Traverse()}
    assert "/World/Table" in paths
    assert "/World/Bin" in paths
    assert "/World/Camera" in paths
    assert "/World/Robot" not in paths
    assert not any(path.startswith("/World/Cubes") for path in paths)


def test_task_stage_with_cubes_is_the_canonical_layout() -> None:
    stage = build_task_stage(SceneConfig(), seed=7, with_cubes=True)
    paths = {str(prim.GetPath()) for prim in stage.Traverse()}
    for index in range(SceneConfig().n_cubes):
        assert f"/World/Cubes/Cube_{index:02d}" in paths
    assert "/World/LabMetadata" in paths


def test_committed_assets_match_the_generator(tmp_path: Path) -> None:
    generator = _load_generator()
    scene = tmp_path / "scene.usda"
    arm = tmp_path / "arm.usda"
    generator.write_task_scene(scene)
    generator.write_arm(arm)
    assert scene.read_text() == (USD_DIR / "lab_task_seed7.usda").read_text()
    assert arm.read_text() == (USD_DIR / "lab_arm.usda").read_text()


def test_arm_usd_is_a_six_dof_articulation() -> None:
    stage = Usd.Stage.Open(str(USD_DIR / "lab_arm.usda"))
    root = stage.GetDefaultPrim()
    assert str(root.GetPath()) == ARM_ROOT
    assert root.HasAPI(UsdPhysics.ArticulationRootAPI)

    joints = {
        prim.GetName()
        for prim in stage.Traverse()
        if prim.IsA(UsdPhysics.RevoluteJoint) or prim.IsA(UsdPhysics.PrismaticJoint)
    }
    assert joints == EXPECTED_JOINTS

    bodies = [prim for prim in stage.Traverse() if prim.HasAPI(UsdPhysics.RigidBodyAPI)]
    assert len(bodies) == len(ArmConfig().joint_limits) + 2  # five links + base + jaw

    # Every joint body target stays inside the articulation subtree, so the USD
    # reference remaps cleanly into each Isaac Lab environment.
    for prim in stage.Traverse():
        if not (prim.IsA(UsdPhysics.RevoluteJoint) or prim.IsA(UsdPhysics.PrismaticJoint)):
            continue
        joint = UsdPhysics.Joint(prim)
        for rel in (joint.GetBody0Rel(), joint.GetBody1Rel()):
            for target in rel.GetTargets():
                assert str(target).startswith(ARM_ROOT + "/")


def test_arm_usd_keeps_the_runtime_limits() -> None:
    stage = Usd.Stage.Open(str(USD_DIR / "lab_arm.usda"))
    jaw = UsdPhysics.PrismaticJoint(stage.GetPrimAtPath(f"{ARM_ROOT}/jaw_joint"))
    assert jaw.GetLowerLimitAttr().Get() == 0.0
    assert abs(jaw.GetUpperLimitAttr().Get() - 0.07) < 1e-6
