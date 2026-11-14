"""OpenUSD construction of the flat runtime arm, shared by the GPU and CPU paths.

The canonical tabletop stage's robot is a nested visual chain that PhysX cannot
simulate.  This module authors a flat articulation (base, five revolute links,
a fixed jaw and one moving jaw) from :class:`~isaac_starter_lab.config.ArmConfig`
dimensions.  The Isaac Sim backend calls :func:`build_runtime_arm` on its live
stage; ``scripts/make_lab_task_usd.py`` calls the same function on a CPU stage and
exports ``usd/lab_arm.usda`` for the Isaac Lab task, so the RL robot and the
PhysX episode robot are authored by one code path.

``pxr`` is imported inside the functions: the CPU test suite imports this module
through ``isaac_backend`` without an Isaac Sim runtime.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from ..config import ArmConfig

__all__ = [
    "ARM_ROOT",
    "CANONICAL_ROBOT",
    "DRIVE_KD",
    "DRIVE_KP",
    "FINGER_THICKNESS",
    "FINGER_Y",
    "GRIPPER_OPEN",
    "LINK_MASSES",
    "build_runtime_arm",
    "make_physics_material",
]

ARM_ROOT = "/World/RobotIsaac"
CANONICAL_ROBOT = "/World/Robot"
GRIPPER_OPEN = 0.07  # metres of travel of the moving jaw
LINK_MASSES = (0.1, 0.02, 0.02, 0.01, 0.01)
FINGER_Y = 0.055
FINGER_THICKNESS = 0.008
DRIVE_KP = 1.0e5
DRIVE_KD = 2.0e3


def make_physics_material(stage: Any, path: str = "/World/PhysicsMat") -> Any:
    """Author the high-friction material used by the jaws and the cubes."""
    from pxr import UsdPhysics, UsdShade  # type: ignore[import-not-found]

    material = UsdShade.Material.Define(stage, path)
    api = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
    api.CreateStaticFrictionAttr(1.2)
    api.CreateDynamicFrictionAttr(1.2)
    api.CreateRestitutionAttr(0.0)
    return material


def build_runtime_arm(
    stage: Any,
    arm: ArmConfig,
    physics_material: Any | None = None,
    root_path: str = ARM_ROOT,
    canonical_robot: str | None = CANONICAL_ROBOT,
) -> None:
    """Author the runtime arm under ``root_path`` on ``stage``."""
    from pxr import Gf, Sdf, UsdGeom, UsdPhysics  # type: ignore[import-not-found]

    if canonical_robot is not None:
        old = stage.GetPrimAtPath(canonical_robot)
        if old:
            old.SetActive(False)

    root = UsdGeom.Xform.Define(stage, root_path)
    root.GetPrim().ApplyAPI(UsdPhysics.ArticulationRootAPI)
    # Adjacent link colliders overlap at the joints; PhysX self-collision
    # would make the stiff drives explode. Cubes still collide with the arm.
    root.GetPrim().CreateAttribute(
        "physxArticulation:enabledSelfCollisions", Sdf.ValueTypeNames.Bool, custom=True
    ).Set(False)

    def link(name: str, xyz: Sequence[float], mass: float):
        xform = UsdGeom.Xform.Define(stage, f"{root_path}/{name}")
        UsdGeom.Xformable(xform).AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in xyz]))
        prim = xform.GetPrim()
        UsdPhysics.RigidBodyAPI.Apply(prim)
        UsdPhysics.MassAPI.Apply(prim).CreateMassAttr(float(mass))
        return prim

    def collider(parent, name: str, offset: Sequence[float], size: Sequence[float]) -> None:
        cube = UsdGeom.Cube.Define(stage, f"{parent.GetPath()}/{name}")
        cube.CreateSizeAttr(1.0)
        UsdGeom.Xformable(cube).AddTranslateOp().Set(
            Gf.Vec3d(*[float(v) for v in offset])
        )
        UsdGeom.Xformable(cube).AddScaleOp().Set(
            Gf.Vec3f(*[float(v) for v in size])
        )
        UsdPhysics.CollisionAPI.Apply(cube.GetPrim())

    def revolute(name, body0, body1, axis, p0, p1, limits_rad):
        joint = UsdPhysics.RevoluteJoint.Define(stage, f"{root_path}/{name}")
        joint.CreateAxisAttr(axis)
        if body0 is not None:
            joint.CreateBody0Rel().SetTargets([str(body0.GetPath())])
        joint.CreateBody1Rel().SetTargets([str(body1.GetPath())])
        joint.CreateLocalPos0Attr(Gf.Vec3f(*[float(v) for v in p0]))
        joint.CreateLocalPos1Attr(Gf.Vec3f(*[float(v) for v in p1]))
        # USD revolute limits are degrees.
        joint.CreateLowerLimitAttr(float(math.degrees(limits_rad[0])))
        joint.CreateUpperLimitAttr(float(math.degrees(limits_rad[1])))
        drive = UsdPhysics.DriveAPI.Apply(joint.GetPrim(), "angular")
        drive.CreateTypeAttr("force")
        drive.CreateStiffnessAttr(DRIVE_KP)
        drive.CreateDampingAttr(DRIVE_KD)
        drive.CreateMaxForceAttr(200.0)
        return joint

    bx, by, bz = arm.base_position
    shoulder = (bx, by, bz + arm.base_height)
    l1, l2 = arm.link1_length, arm.link2_length
    wrist_len, tool_len = arm.wrist_length, arm.tool_length

    base = link("base", (bx, by, bz), 0.5)
    # Visual column only: a collider here intersects link0 at the shoulder
    # and jams the base yaw at ~39 degrees.
    column = UsdGeom.Cube.Define(stage, f"{root_path}/base/Column")
    column.CreateSizeAttr(1.0)
    UsdGeom.Xformable(column).AddTranslateOp().Set(
        Gf.Vec3d(0.0, 0.0, arm.base_height / 2.0)
    )
    UsdGeom.Xformable(column).AddScaleOp().Set(
        Gf.Vec3f(0.07, 0.07, arm.base_height)
    )
    anchor = UsdPhysics.FixedJoint.Define(stage, f"{root_path}/anchor")
    anchor.CreateBody1Rel().SetTargets([str(base.GetPath())])
    anchor.CreateLocalPos0Attr(Gf.Vec3f(float(bx), float(by), float(bz)))
    anchor.CreateLocalPos1Attr(Gf.Vec3f(0.0, 0.0, 0.0))

    link0 = link("link0", shoulder, LINK_MASSES[0])
    collider(link0, "Visual", (0.0, 0.0, 0.0), (0.06, 0.06, 0.06))
    link1 = link("link1", shoulder, LINK_MASSES[1])
    collider(link1, "Visual", (l1 / 2.0, 0.0, 0.0), (l1, 0.045, 0.045))
    link2 = link("link2", (shoulder[0] + l1, shoulder[1], shoulder[2]), LINK_MASSES[2])
    collider(link2, "Visual", (l2 / 2.0, 0.0, 0.0), (l2, 0.04, 0.04))
    wrist = link("wrist", (shoulder[0] + l1 + l2, shoulder[1], shoulder[2]), LINK_MASSES[3])
    collider(wrist, "Visual", (0.0, 0.0, 0.0), (0.06, 0.05, 0.05))
    gripper = link(
        "gripper",
        (shoulder[0] + l1 + l2 + wrist_len, shoulder[1], shoulder[2]),
        LINK_MASSES[4],
    )
    # The gripper body is visual only; the fingers are the contact surfaces.

    limits = arm.joint_limits
    revolute("joint_base_yaw", base, link0, "Z", (0.0, 0.0, arm.base_height), (0.0, 0.0, 0.0), limits[0])
    revolute("joint_shoulder", link0, link1, "Y", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (-limits[1][1], -limits[1][0]))
    revolute("joint_elbow", link1, link2, "Y", (l1, 0.0, 0.0), (0.0, 0.0, 0.0), (-limits[2][1], -limits[2][0]))
    revolute("joint_wrist_pitch", link2, wrist, "Y", (l2, 0.0, 0.0), (0.0, 0.0, 0.0), (-limits[3][1], -limits[3][0]))
    revolute("joint_wrist_roll", wrist, gripper, "X", (wrist_len, 0.0, 0.0), (0.0, 0.0, 0.0), limits[4])

    tip_x = shoulder[0] + l1 + l2 + wrist_len + tool_len
    # Fixed right jaw is part of the gripper body; one moving left jaw is
    # the only gripper DOF, which makes its sign unambiguous.
    collider(gripper, "FixedJaw", (tool_len, FINGER_Y, 0.0),
             (0.06, FINGER_THICKNESS, 0.03))
    jaw = link("jaw", (tip_x, shoulder[1] - FINGER_Y, shoulder[2]), 0.005)
    collider(jaw, "Visual", (0.0, 0.0, 0.0), (0.06, FINGER_THICKNESS, 0.03))
    if physics_material is not None:
        from pxr import UsdShade  # type: ignore[import-not-found]

        for prim_path in (f"{gripper.GetPath()}/FixedJaw", f"{jaw.GetPath()}/Visual"):
            UsdShade.MaterialBindingAPI.Apply(
                stage.GetPrimAtPath(prim_path)
            ).Bind(physics_material, UsdShade.Tokens.weakerThanDescendants, "physics")
    joint = UsdPhysics.PrismaticJoint.Define(stage, f"{root_path}/jaw_joint")
    joint.CreateAxisAttr("Y")
    joint.CreateBody0Rel().SetTargets([str(gripper.GetPath())])
    joint.CreateBody1Rel().SetTargets([str(jaw.GetPath())])
    joint.CreateLocalPos0Attr(Gf.Vec3f(float(tool_len), float(-FINGER_Y), 0.0))
    joint.CreateLocalPos1Attr(Gf.Vec3f(0.0, 0.0, 0.0))
    joint.CreateLowerLimitAttr(0.0)
    joint.CreateUpperLimitAttr(GRIPPER_OPEN)
    drive = UsdPhysics.DriveAPI.Apply(joint.GetPrim(), "linear")
    drive.CreateTypeAttr("force")
    drive.CreateStiffnessAttr(DRIVE_KP)
    drive.CreateDampingAttr(DRIVE_KD)
    drive.CreateMaxForceAttr(50.0)
