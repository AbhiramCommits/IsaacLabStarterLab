"""Deterministic OpenUSD tabletop scene construction.

The scene is generated with the real ``pxr`` Python API (``usd-core``).  It is
the canonical description of the lab world: both the CPU kinematic backend and
the Isaac Sim adapter consume the same stage, so prim paths, camera intrinsics
and cube placements never drift between tracks.

Geometry conventions
--------------------
* metres, Z up
* table top plane at ``SceneConfig.table_top``
* cubes are axis-aligned boxes of edge ``cube_size`` resting on the table
* the arm is a 5-DOF chain ``base -> link0 -> link1 -> link2 -> wrist -> gripper``
* joint axes are ``Z, Y, Y, Y, X`` (base yaw, shoulder, elbow, wrist pitch,
  wrist roll about the tool axis)

All randomness comes from ``numpy.random.default_rng(seed)``.  Cube placement
uses rejection sampling with a bounded number of attempts so a pathological
configuration fails loudly instead of hanging.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade

from ..config import ArmConfig, CameraIntrinsics, SceneConfig

__all__ = [
    "CUBES_ROOT",
    "CubePlacement",
    "SceneSamplingError",
    "build_stage",
    "sample_cube_layout",
]

CUBES_ROOT = "/World/Cubes"
MAX_PLACEMENT_ATTEMPTS = 2000


class SceneSamplingError(RuntimeError):
    """Raised when rejection sampling cannot place all cubes."""


@dataclass(frozen=True)
class CubePlacement:
    """A sampled cube: prim name, centre in metres, palette name and RGB."""

    name: str
    position: tuple[float, float, float]
    color_name: str
    rgb: tuple[int, int, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "position": list(self.position),
            "color": self.color_name,
            "rgb": list(self.rgb),
        }


def sample_cube_layout(cfg: SceneConfig, seed: int) -> tuple[CubePlacement, ...]:
    """Sample non-overlapping cube centres inside the placement rectangle.

    Separation is checked with the Chebyshev metric: two axis-aligned cubes of
    edge ``cube_size`` cannot overlap when ``max(|dx|, |dy|) >= cube_size``.
    """
    rng = np.random.default_rng(seed)
    half = cfg.cube_size / 2.0
    margin = cfg.cube_margin
    (lo_x, lo_y, _), (hi_x, hi_y, _) = cfg.placement_aabb
    x_min, x_max = lo_x + half + margin, hi_x - half - margin
    y_min, y_max = lo_y + half + margin, hi_y - half - margin
    if x_min >= x_max or y_min >= y_max:
        raise SceneSamplingError(
            "placement_aabb is too small for cube_size + margin: "
            f"x range ({x_min:.4f}, {x_max:.4f}), y range ({y_min:.4f}, {y_max:.4f})"
        )

    centres: list[tuple[float, float]] = []
    min_separation = cfg.cube_size + margin
    attempts = 0
    while len(centres) < cfg.n_cubes:
        if attempts >= MAX_PLACEMENT_ATTEMPTS:
            raise SceneSamplingError(
                f"could not place {cfg.n_cubes} cubes after {MAX_PLACEMENT_ATTEMPTS} "
                f"attempts (seed={seed}, cube_size={cfg.cube_size}, "
                f"placement_aabb={cfg.placement_aabb}); enlarge the placement area "
                "or reduce --n-cubes"
            )
        attempts += 1
        candidate = (float(rng.uniform(x_min, x_max)), float(rng.uniform(y_min, y_max)))
        if all(
            max(abs(candidate[0] - x), abs(candidate[1] - y)) >= min_separation
            for x, y in centres
        ):
            centres.append(candidate)

    palette_indices = rng.permutation(len(cfg.palette))[: cfg.n_cubes]
    placements: list[CubePlacement] = []
    for index, (x, y) in enumerate(centres):
        color_name, rgb = cfg.palette[int(palette_indices[index])]
        placements.append(
            CubePlacement(
                name=f"Cube_{index:02d}",
                position=(x, y, cfg.cube_center_z),
                color_name=color_name,
                rgb=rgb,
            )
        )
    return tuple(placements)


def _set_xform(
    prim: Usd.Prim,
    translate: Sequence[float] | None = None,
    scale: Sequence[float] | None = None,
    orient: Gf.Quatf | None = None,
) -> None:
    xformable = UsdGeom.Xformable(prim)
    xformable.ClearXformOpOrder()
    if translate is not None:
        xformable.AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in translate]))
    if orient is not None:
        xformable.AddOrientOp().Set(orient)
    if scale is not None:
        xformable.AddScaleOp().Set(Gf.Vec3f(*[float(v) for v in scale]))


def _define_cube(
    stage: Usd.Stage,
    path: str,
    translate: Sequence[float],
    scale: Sequence[float],
    color: Sequence[float],
    *,
    collision: bool = True,
    rigid_body: bool = False,
    mass: float | None = None,
    material: UsdShade.Material | None = None,
    color_name: str | None = None,
) -> Usd.Prim:
    cube = UsdGeom.Cube.Define(stage, path)
    cube.CreateSizeAttr(1.0)
    _set_xform(cube.GetPrim(), translate=translate, scale=scale)
    cube.CreateDisplayColorAttr([Gf.Vec3f(*[float(c) for c in color])])
    prim = cube.GetPrim()
    if collision:
        UsdPhysics.CollisionAPI.Apply(prim)
    if rigid_body:
        UsdPhysics.RigidBodyAPI.Apply(prim)
    if mass is not None:
        UsdPhysics.MassAPI.Apply(prim).CreateMassAttr(float(mass))
    if material is not None:
        UsdShade.MaterialBindingAPI.Apply(prim).Bind(material)
    if color_name:
        prim.CreateAttribute("lab:colorName", Sdf.ValueTypeNames.String, custom=True).Set(color_name)
    return prim


def _make_material(
    stage: Usd.Stage, name: str, rgb: Sequence[int]
) -> UsdShade.Material:
    material = UsdShade.Material.Define(stage, f"/World/Materials/{name}")
    shader = UsdShade.Shader.Define(stage, f"/World/Materials/{name}/PreviewSurface")
    shader.CreateIdAttr("UsdPreviewSurface")
    color = Gf.Vec3f(*(c / 255.0 for c in rgb))
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(color)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.55)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return material


def _camera_basis(
    position: Sequence[float], look_at: Sequence[float], up: Sequence[float]
) -> tuple[Gf.Vec3d, Gf.Vec3d, Gf.Vec3d]:
    eye = Gf.Vec3d(*[float(v) for v in position])
    target = Gf.Vec3d(*[float(v) for v in look_at])
    up_vec = Gf.Vec3d(*[float(v) for v in up])
    forward = (target - eye).GetNormalized()
    right = Gf.Cross(forward, up_vec).GetNormalized()
    true_up = Gf.Cross(right, forward).GetNormalized()
    return right, true_up, forward


def _define_camera(stage: Usd.Stage, cfg: SceneConfig, intrinsics: CameraIntrinsics) -> None:
    camera = UsdGeom.Camera.Define(stage, "/World/Camera")
    camera.CreateFocalLengthAttr(intrinsics.focal_length_mm)
    camera.CreateHorizontalApertureAttr(intrinsics.horizontal_aperture_mm)
    camera.CreateVerticalApertureAttr(intrinsics.vertical_aperture_mm)
    camera.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))
    camera.CreateFStopAttr(4.0)
    camera.CreateFocusDistanceAttr(1.0)

    right, true_up, forward = _camera_basis(
        cfg.camera_position, cfg.camera_look_at, cfg.camera_up
    )
    eye = Gf.Vec3d(*cfg.camera_position)
    matrix = Gf.Matrix4d(
        right[0], right[1], right[2], 0.0,
        true_up[0], true_up[1], true_up[2], 0.0,
        -forward[0], -forward[1], -forward[2], 0.0,
        eye[0], eye[1], eye[2], 1.0,
    )
    UsdGeom.Xformable(camera.GetPrim()).ClearXformOpOrder()
    UsdGeom.Xformable(camera.GetPrim()).AddTransformOp().Set(matrix)
    camera.GetPrim().CreateAttribute(
        "lab:lookAt", Sdf.ValueTypeNames.Double3, custom=True
    ).Set(Gf.Vec3d(*cfg.camera_look_at))


def _define_table(stage: Usd.Stage, cfg: SceneConfig) -> None:
    cube = UsdGeom.Cube.Define(stage, "/World/Table")
    cube.CreateSizeAttr(1.0)
    (lo_x, lo_y, lo_z), (hi_x, hi_y, hi_z) = cfg.table_aabb
    size = (hi_x - lo_x, hi_y - lo_y, hi_z - lo_z)
    centre = ((lo_x + hi_x) / 2, (lo_y + hi_y) / 2, (lo_z + hi_z) / 2)
    _set_xform(cube.GetPrim(), translate=centre, scale=size)
    cube.CreateDisplayColorAttr([Gf.Vec3f(*(c / 255.0 for c in cfg.table_color))])
    prim = cube.GetPrim()
    UsdPhysics.CollisionAPI.Apply(prim)
    prim.CreateAttribute("lab:aabb", Sdf.ValueTypeNames.DoubleArray, custom=True).Set(
        [lo_x, lo_y, lo_z, hi_x, hi_y, hi_z]
    )
    prim.CreateAttribute(
        "lab:tableColor", Sdf.ValueTypeNames.Double3, custom=True
    ).Set(Gf.Vec3d(*(c / 255.0 for c in cfg.table_color)))


def _define_bin(stage: Usd.Stage, cfg: SceneConfig) -> None:
    bin_xform = UsdGeom.Xform.Define(stage, "/World/Bin")
    (lo_x, lo_y, lo_z), (hi_x, hi_y, hi_z) = cfg.bin_aabb
    width = hi_x - lo_x
    depth = hi_y - lo_y
    height = hi_z - lo_z
    t = cfg.bin_wall_thickness
    z_center = lo_z + height / 2

    walls = (
        ("Wall_north", ((lo_x + hi_x) / 2, hi_y - t / 2, z_center), (width, t, height)),
        ("Wall_south", ((lo_x + hi_x) / 2, lo_y + t / 2, z_center), (width, t, height)),
        ("Wall_east", (hi_x - t / 2, (lo_y + hi_y) / 2, z_center), (t, depth, height)),
        ("Wall_west", (lo_x + t / 2, (lo_y + hi_y) / 2, z_center), (t, depth, height)),
    )
    for name, translate, scale in walls:
        _define_cube(
            stage,
            f"/World/Bin/{name}",
            translate,
            scale,
            cfg.bin_color,
            collision=True,
        )

    prim = bin_xform.GetPrim()
    prim.CreateAttribute("lab:aabb", Sdf.ValueTypeNames.DoubleArray, custom=True).Set(
        [lo_x, lo_y, lo_z, hi_x, hi_y, hi_z]
    )
    prim.CreateAttribute(
        "lab:binColor", Sdf.ValueTypeNames.Double3, custom=True
    ).Set(Gf.Vec3d(*(c / 255.0 for c in cfg.bin_color)))
    prim.CreateAttribute("lab:wallHeight", Sdf.ValueTypeNames.Double, custom=True).Set(height)
    prim.CreateAttribute(
        "lab:innerAABB", Sdf.ValueTypeNames.DoubleArray, custom=True
    ).Set(
        [
            lo_x + t,
            lo_y + t,
            lo_z,
            hi_x - t,
            hi_y - t,
            hi_z,
        ]
    )


def _define_cubes(
    stage: Usd.Stage,
    cfg: SceneConfig,
    placements: Sequence[CubePlacement],
) -> None:
    UsdGeom.Xform.Define(stage, CUBES_ROOT)
    materials = {
        name: _make_material(stage, name.capitalize(), rgb) for name, rgb in cfg.palette
    }
    for placement in placements:
        _define_cube(
            stage,
            f"{CUBES_ROOT}/{placement.name}",
            placement.position,
            (cfg.cube_size, cfg.cube_size, cfg.cube_size),
            [c / 255.0 for c in placement.rgb],
            collision=True,
            rigid_body=True,
            mass=0.05,
            material=materials[placement.color_name],
            color_name=placement.color_name,
        )


def _define_robot(stage: Usd.Stage, cfg: SceneConfig, arm: ArmConfig) -> None:
    robot = UsdGeom.Xform.Define(stage, "/World/Robot")
    base = UsdGeom.Xform.Define(stage, "/World/Robot/base")
    base.GetPrim().ApplyAPI(UsdPhysics.ArticulationRootAPI)
    UsdPhysics.RigidBodyAPI.Apply(base.GetPrim())
    UsdPhysics.MassAPI.Apply(base.GetPrim()).CreateMassAttr(5.0)
    _set_xform(base.GetPrim(), translate=arm.base_position)
    robot.GetPrim().CreateAttribute(
        "lab:jointAxes", Sdf.ValueTypeNames.StringArray, custom=True
    ).Set(list(arm.joint_axes))
    robot.GetPrim().CreateAttribute(
        "lab:jointNames", Sdf.ValueTypeNames.StringArray, custom=True
    ).Set(list(arm.joint_names))

    # Static column visual: from the table up to the shoulder axis.
    _define_cube(
        stage,
        "/World/Robot/base/Column",
        (0.0, 0.0, arm.base_height / 2.0),
        (0.07, 0.07, arm.base_height),
        (60, 60, 66),
        collision=True,
    )

    link0 = UsdGeom.Xform.Define(stage, "/World/Robot/base/link0")
    _set_xform(link0.GetPrim(), translate=(0.0, 0.0, arm.base_height))
    UsdPhysics.RigidBodyAPI.Apply(link0.GetPrim())
    UsdPhysics.MassAPI.Apply(link0.GetPrim()).CreateMassAttr(1.5)

    link1 = UsdGeom.Xform.Define(stage, "/World/Robot/base/link0/link1")
    UsdPhysics.RigidBodyAPI.Apply(link1.GetPrim())
    UsdPhysics.MassAPI.Apply(link1.GetPrim()).CreateMassAttr(1.0)
    _define_cube(
        stage,
        "/World/Robot/base/link0/link1/Visual",
        (arm.link1_length / 2.0, 0.0, 0.0),
        (arm.link1_length, 0.045, 0.045),
        (240, 150, 40),
        collision=True,
    )

    link2 = UsdGeom.Xform.Define(stage, "/World/Robot/base/link0/link1/link2")
    _set_xform(link2.GetPrim(), translate=(arm.link1_length, 0.0, 0.0))
    UsdPhysics.RigidBodyAPI.Apply(link2.GetPrim())
    UsdPhysics.MassAPI.Apply(link2.GetPrim()).CreateMassAttr(0.8)
    _define_cube(
        stage,
        "/World/Robot/base/link0/link1/link2/Visual",
        (arm.link2_length / 2.0, 0.0, 0.0),
        (arm.link2_length, 0.04, 0.04),
        (240, 170, 60),
        collision=True,
    )

    wrist = UsdGeom.Xform.Define(stage, "/World/Robot/base/link0/link1/link2/wrist")
    _set_xform(wrist.GetPrim(), translate=(arm.link2_length, 0.0, 0.0))
    UsdPhysics.RigidBodyAPI.Apply(wrist.GetPrim())
    UsdPhysics.MassAPI.Apply(wrist.GetPrim()).CreateMassAttr(0.4)

    gripper = UsdGeom.Xform.Define(
        stage, "/World/Robot/base/link0/link1/link2/wrist/gripper"
    )
    _set_xform(gripper.GetPrim(), translate=(arm.wrist_length, 0.0, 0.0))
    UsdPhysics.RigidBodyAPI.Apply(gripper.GetPrim())
    UsdPhysics.MassAPI.Apply(gripper.GetPrim()).CreateMassAttr(0.2)
    for side, y in (("FingerLeft", -0.02), ("FingerRight", 0.02)):
        _define_cube(
            stage,
            f"/World/Robot/base/link0/link1/link2/wrist/gripper/{side}",
            (arm.tool_length / 2.0, y, 0.0),
            (arm.tool_length, 0.012, 0.03),
            (80, 80, 85),
            collision=True,
        )

    joint_specs = (
        ("joint_base_yaw", "base", "base/link0", "Z", (0, 0, arm.base_height), (0, 0, 0), arm.joint_limits[0]),
        ("joint_shoulder", "base/link0", "base/link0/link1", "Y", (0, 0, 0), (0, 0, 0), arm.joint_limits[1]),
        ("joint_elbow", "base/link0/link1", "base/link0/link1/link2", "Y", (arm.link1_length, 0, 0), (0, 0, 0), arm.joint_limits[2]),
        ("joint_wrist_pitch", "base/link0/link1/link2", "base/link0/link1/link2/wrist", "Y", (arm.link2_length, 0, 0), (0, 0, 0), arm.joint_limits[3]),
        ("joint_wrist_roll", "base/link0/link1/link2/wrist", "base/link0/link1/link2/wrist/gripper", "X", (arm.wrist_length, 0, 0), (0, 0, 0), arm.joint_limits[4]),
    )
    UsdGeom.Xform.Define(stage, "/World/Robot/Joints")
    robot_root = "/World/Robot/"
    for name, body0, body1, axis, pos0, pos1, limits in joint_specs:
        joint = UsdPhysics.RevoluteJoint.Define(stage, f"/World/Robot/Joints/{name}")
        joint.CreateAxisAttr(axis)
        joint.CreateBody0Rel().SetTargets([Sdf.Path(robot_root + body0)])
        joint.CreateBody1Rel().SetTargets([Sdf.Path(robot_root + body1)])
        joint.CreateLocalPos0Attr(Gf.Vec3f(*pos0))
        joint.CreateLocalPos1Attr(Gf.Vec3f(*pos1))
        joint.CreateLocalRot0Attr(Gf.Quatf(1.0))
        joint.CreateLocalRot1Attr(Gf.Quatf(1.0))
        joint.CreateLowerLimitAttr(float(np.degrees(limits[0])))
        joint.CreateUpperLimitAttr(float(np.degrees(limits[1])))
        joint.GetPrim().CreateAttribute(
            "lab:jointName", Sdf.ValueTypeNames.String, custom=True
        ).Set(name)


def _define_light(stage: Usd.Stage, cfg: SceneConfig) -> None:
    light = UsdLux.DomeLight.Define(stage, "/World/Lights/DomeLight")
    light.CreateIntensityAttr(1000.0 * cfg.light_intensity)
    light.CreateColorAttr(Gf.Vec3f(1.0, 1.0, 1.0))
    light.GetPrim().CreateAttribute(
        "lab:normalizedIntensity", Sdf.ValueTypeNames.Double, custom=True
    ).Set(float(cfg.light_intensity))
    light.GetPrim().CreateAttribute(
        "lab:lightDirection", Sdf.ValueTypeNames.Double3, custom=True
    ).Set(Gf.Vec3d(0.3, 0.4, 0.85))


def build_stage(
    cfg: SceneConfig,
    seed: int,
    intrinsics: CameraIntrinsics | None = None,
    arm: ArmConfig | None = None,
) -> Usd.Stage:
    """Build the complete tabletop stage in memory.

    The returned stage has no time samples and no timestamps, so exporting it is
    byte-stable for a given code version, seed and configuration.
    """
    if seed < 0:
        raise ValueError("seed must be non-negative")
    intrinsics = intrinsics or CameraIntrinsics()
    arm = arm or ArmConfig()
    placements = sample_cube_layout(cfg, seed)

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    world.GetPrim().CreateAttribute("lab:seed", Sdf.ValueTypeNames.Int, custom=True).Set(
        int(seed)
    )
    world.GetPrim().CreateAttribute(
        "lab:cubeSize", Sdf.ValueTypeNames.Double, custom=True
    ).Set(float(cfg.cube_size))
    UsdGeom.Xform.Define(stage, "/World/Lights")

    _define_table(stage, cfg)
    _define_bin(stage, cfg)
    _define_cubes(stage, cfg, placements)
    _define_robot(stage, cfg, arm)
    _define_camera(stage, cfg, intrinsics)
    _define_light(stage, cfg)

    # Record the exact layout so diagnostics never need to re-sample.
    cubes = UsdGeom.Xform.Define(stage, "/World/LabMetadata")
    cubes.GetPrim().CreateAttribute(
        "lab:placements", Sdf.ValueTypeNames.StringArray, custom=True
    ).Set([f"{p.name}:{p.color_name}:{p.position[0]:.6f},{p.position[1]:.6f}" for p in placements])
    return stage
