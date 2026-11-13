"""Isaac Sim 6.0 backend (GPU-host path).

The CPU scene's robot is a visual chain: its rigid bodies are nested and its
joints sit outside the articulation root, so PhysX cannot simulate it.  This
adapter keeps the canonical stage (table, bin, cubes, camera) and builds a
clean, flat articulation at runtime under ``/World/RobotIsaac`` from the same
:class:`~isaac_starter_lab.config.ArmConfig` dimensions and joint names.  The
canonical file and its pinned hash are untouched.

The runtime arm has five revolute joints plus two prismatic finger joints.  It
is position-controlled: the controller's velocity commands are integrated into
position targets each tick, and the cubes are moved only by PhysX contact and
friction.  ``grasped`` is a state estimate (fingers closed and a cube at the
tool tip); the cube's motion is never attached to the gripper.
"""

from __future__ import annotations

import math
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from ..config import LAB_SEED, ArmConfig, CameraIntrinsics, SceneConfig
from .schema import CubePoseArray, JointState, RgbFrame

__all__ = ["IsaacSimBackend", "IsaacUnavailableError"]

CONTAINER_IMAGE = "nvcr.io/nvidia/isaac-sim:6.0.0"
DOCKER_RUN = (
    "docker run --rm -it --gpus all --network host "
    "-e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y "
    "-e LAB_BACKEND=isaac -e LAB_BRIDGE=ros2 "
    '-v "$HOME/.cache/ov:/root/.cache/ov" '
    '-v "$HOME/.cache/pip:/root/.cache/pip" '
    '-v "$HOME/.cache/nvidia:/root/.cache/nvidia" '
    '-v "$HOME/.local/share/ov:/root/.local/share/ov" '
    "isaac-starter-lab:gpu"
)

ARM_ROOT = "/World/RobotIsaac"
CANONICAL_ROBOT = "/World/Robot"
GRIPPER_OPEN = 0.07  # metres of travel of the moving jaw
LINK_MASSES = (0.1, 0.02, 0.02, 0.01, 0.01)
FINGER_Y = 0.055
FINGER_THICKNESS = 0.008
DRIVE_KP = 1.0e5
DRIVE_KD = 2.0e3
# USD +Y rotates a +X link downward; the CPU FK uses positive = lift.
JOINT_SIGNS = np.array([1.0, -1.0, -1.0, -1.0, 1.0, 1.0])
MAX_TARGET_STEP = 0.01


class IsaacUnavailableError(RuntimeError):
    """Raised when the Isaac Sim runtime is not importable on this host."""


def _unavailable(detail: str) -> IsaacUnavailableError:
    return IsaacUnavailableError(
        "Isaac Sim is not available on this machine "
        f"({detail}).\n"
        f"Required container: {CONTAINER_IMAGE}\n"
        "Required host: NVIDIA GPU (RTX) + driver >= 580.65.06 + NVIDIA Container Toolkit.\n"
        f"Run: {DOCKER_RUN}\n"
        "Then set LAB_BACKEND=isaac (and LAB_BRIDGE=ros2)."
    )


def _import_simulation_app():
    try:  # Isaac Sim 4.x/5.x/6.x Python package
        from isaacsim import SimulationApp  # type: ignore[import-not-found]

        return SimulationApp
    except ImportError:
        pass
    try:  # older Isaac Sim layout
        from omni.isaac.kit import SimulationApp  # type: ignore[import-not-found]

        return SimulationApp
    except ImportError as exc:
        raise _unavailable("neither isaacsim.SimulationApp nor omni.isaac.kit is importable") from exc


class IsaacSimBackend:
    """Real-API adapter around ``isaacsim.SimulationApp`` plus a runtime arm."""

    def __init__(
        self,
        scene: SceneConfig | None = None,
        arm: ArmConfig | None = None,
        seed: int = LAB_SEED,
        usda_path: str | Path = "usd/tabletop_seed7.usda",
        headless: bool = True,
        enable_ros2: bool = False,
    ) -> None:
        self.scene = scene or SceneConfig()
        self.arm = arm or ArmConfig()
        self.camera = CameraIntrinsics()
        self.seed = seed
        self.usda_path = Path(usda_path)
        self.headless = headless
        self.enable_ros2 = enable_ros2
        self._app: Any | None = None
        self._stage: Any | None = None
        self._sim: Any | None = None
        self._articulation: Any | None = None
        self._camera: Any | None = None
        self._ros_bridge: Any | None = None
        self._joint_velocity_command = np.zeros(5, dtype=float)
        self._gripper_closure = 0.0
        self._gripper_command = 0.0
        self._physics_material: Any | None = None
        self._grasped_name: str | None = None
        self.tick = 0
        self.time_s = 0.0

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def start(self) -> IsaacSimBackend:
        SimulationApp = _import_simulation_app()
        self._app = SimulationApp({"headless": self.headless, "anti_aliasing": 0, "denoiser": False})
        if not self.usda_path.exists():
            raise FileNotFoundError(
                f"USD stage not found: {self.usda_path}. Run `lab-scene --seed 7` first."
            )
        self._open_stage()
        self._build_arm()
        self._start_physics()
        self._setup_camera()
        if self.enable_ros2:
            self._enable_ros2_bridge()
        return self

    def _open_stage(self) -> None:
        import omni.usd  # type: ignore[import-not-found]

        context = omni.usd.get_context()
        if not context.open_stage(str(self.usda_path.resolve())):
            raise RuntimeError(f"Isaac Sim could not open {self.usda_path}")
        self._stage = context.get_stage()
        # The CPU track renders flat, fully saturated cube colours. RTX shades
        # them with a white dome light and desaturates them below the detector's
        # threshold, so make the cube materials emissive and lower the dome.
        from pxr import Sdf, UsdShade  # type: ignore[import-not-found]

        for color in ("Red", "Green", "Blue", "Yellow", "Magenta"):
            shader = UsdShade.Shader(
                self._stage.GetPrimAtPath(f"/World/Materials/{color}/PreviewSurface")
            )
            if not shader:
                continue
            diffuse = shader.GetInput("diffuseColor").Get()
            shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(diffuse * 0.6)
        dome = self._stage.GetPrimAtPath("/World/Lights/DomeLight")
        if dome:
            dome.GetAttribute("inputs:intensity").Set(100.0)
        camera_prim = self._stage.GetPrimAtPath("/World/Camera")
        if camera_prim:
            camera_prim.GetAttribute("fStop").Set(64.0)
            camera_prim.GetAttribute("focusDistance").Set(1.0)
        # High-friction physics material so the parallel jaws can retain a cube.
        from pxr import UsdPhysics as _UsdPhysics
        from pxr import UsdShade as _UsdShade

        physics_mat = _UsdShade.Material.Define(self._stage, "/World/PhysicsMat")
        pm = _UsdPhysics.MaterialAPI.Apply(physics_mat.GetPrim())
        pm.CreateStaticFrictionAttr(1.2)
        pm.CreateDynamicFrictionAttr(1.2)
        pm.CreateRestitutionAttr(0.0)
        self._physics_material = physics_mat
        for index in range(self.scene.n_cubes):
            prim = self._stage.GetPrimAtPath(f"/World/Cubes/Cube_{index:02d}")
            _UsdShade.MaterialBindingAPI.Apply(prim).Bind(
                physics_mat, _UsdShade.Tokens.weakerThanDescendants, "physics"
            )

    # ------------------------------------------------------------------
    # runtime arm (canonical stage stays untouched)
    # ------------------------------------------------------------------
    def _build_arm(self) -> None:
        from pxr import Gf, Sdf, UsdGeom, UsdPhysics  # type: ignore[import-not-found]

        stage = self._stage
        assert stage is not None
        old = stage.GetPrimAtPath(CANONICAL_ROBOT)
        if old:
            old.SetActive(False)

        root = UsdGeom.Xform.Define(stage, ARM_ROOT)
        root.GetPrim().ApplyAPI(UsdPhysics.ArticulationRootAPI)
        # Adjacent link colliders overlap at the joints; PhysX self-collision
        # would make the stiff drives explode. Cubes still collide with the arm.
        root.GetPrim().CreateAttribute(
            "physxArticulation:enabledSelfCollisions", Sdf.ValueTypeNames.Bool, custom=True
        ).Set(False)

        def link(name: str, xyz: Sequence[float], mass: float):
            xform = UsdGeom.Xform.Define(stage, f"{ARM_ROOT}/{name}")
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
            joint = UsdPhysics.RevoluteJoint.Define(stage, f"{ARM_ROOT}/{name}")
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

        bx, by, bz = self.arm.base_position
        shoulder = (bx, by, bz + self.arm.base_height)
        l1, l2 = self.arm.link1_length, self.arm.link2_length
        wrist_len, tool_len = self.arm.wrist_length, self.arm.tool_length

        base = link("base", (bx, by, bz), 0.5)
        # Visual column only: a collider here intersects link0 at the shoulder
        # and jams the base yaw at ~39 degrees.
        column = UsdGeom.Cube.Define(stage, f"{ARM_ROOT}/base/Column")
        column.CreateSizeAttr(1.0)
        UsdGeom.Xformable(column).AddTranslateOp().Set(
            Gf.Vec3d(0.0, 0.0, self.arm.base_height / 2.0)
        )
        UsdGeom.Xformable(column).AddScaleOp().Set(
            Gf.Vec3f(0.07, 0.07, self.arm.base_height)
        )
        anchor = UsdPhysics.FixedJoint.Define(stage, f"{ARM_ROOT}/anchor")
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

        limits = self.arm.joint_limits
        revolute("joint_base_yaw", base, link0, "Z", (0.0, 0.0, self.arm.base_height), (0.0, 0.0, 0.0), limits[0])
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
        if self._physics_material is not None:
            from pxr import UsdShade  # type: ignore[import-not-found]

            for prim_path in (f"{gripper.GetPath()}/FixedJaw", f"{jaw.GetPath()}/Visual"):
                UsdShade.MaterialBindingAPI.Apply(
                    stage.GetPrimAtPath(prim_path)
                ).Bind(self._physics_material, UsdShade.Tokens.weakerThanDescendants, "physics")
        joint = UsdPhysics.PrismaticJoint.Define(stage, f"{ARM_ROOT}/jaw_joint")
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

    def _start_physics(self) -> None:
        from isaacsim.core.api import SimulationContext  # type: ignore[import-not-found]
        from isaacsim.core.prims import Articulation  # type: ignore[import-not-found]

        self._sim = SimulationContext(
            physics_dt=1.0 / 240.0,
            rendering_dt=1.0 / 60.0,
            stage_units_in_meters=1.0,
        )
        self._sim.initialize_physics()
        self._sim.reset()
        self._articulation = Articulation(prim_paths_expr=ARM_ROOT)
        self._articulation.initialize()
        n = int(self._articulation.num_dof)
        self._articulation.set_gains(
            kps=np.full(n, DRIVE_KP), kds=np.full(n, DRIVE_KD)
        )
        self._joint_velocity_command = np.zeros(n, dtype=float)
        # Hold the assembled pose while the camera warms up; otherwise the arm
        # falls under gravity before the first controller tick.
        q = self.joint_positions
        self._articulation.set_joint_position_targets(q.reshape(1, -1))

    def _setup_camera(self) -> None:
        try:
            from isaacsim.sensors.camera import Camera  # type: ignore[import-not-found]
        except ImportError:
            from omni.isaac.sensor import Camera  # type: ignore[import-not-found]

        self._camera = Camera(
            prim_path="/World/Camera",
            resolution=(self.camera.width, self.camera.height),
        )
        self._camera.initialize()
        # Warm the render product so the first get_rgba() has data.
        for _ in range(10):
            self._sim.render()

    def _enable_ros2_bridge(self) -> None:
        try:
            from isaacsim.core.utils.extensions import enable_extension  # type: ignore
        except ImportError:
            from omni.isaac.core.utils.extensions import enable_extension  # type: ignore

        for extension in ("isaacsim.ros2.bridge", "omni.isaac.ros2_bridge"):
            try:
                enable_extension(extension)
                break
            except Exception:
                continue
        try:
            from ..bridge.ros2_bridge import Ros2Bridge

            self._ros_bridge = Ros2Bridge(node_name="isaac_starter_lab")
        except Exception as exc:  # pragma: no cover - GPU host only
            raise RuntimeError(
                "ROS 2 bridge was requested but rclpy is not available inside the "
                "Isaac Sim container. Source /opt/ros/humble/setup.bash or set "
                "LAB_BRIDGE=localbus."
            ) from exc

    # ------------------------------------------------------------------
    # observation
    # ------------------------------------------------------------------
    @property
    def joint_positions(self) -> np.ndarray:
        if self._articulation is None:
            raise RuntimeError("articulation is not initialized")
        return np.asarray(self._articulation.get_joint_positions(), dtype=float).ravel()

    def _cpu_positions(self) -> np.ndarray:
        return self.joint_positions * JOINT_SIGNS

    def joint_state(self) -> JointState:
        if self._articulation is None:
            raise RuntimeError("articulation is not initialized")
        positions = self._cpu_positions()[:5]
        velocities = (
            np.asarray(self._articulation.get_joint_velocities(), dtype=float).ravel()[:5]
            * JOINT_SIGNS[:5]
        )
        return JointState(
            stamp=self.time_s,
            names=self.arm.joint_names,
            positions=tuple(float(v) for v in positions),
            velocities=tuple(float(v) for v in velocities),
            gripper=float(self._gripper_closure),
        )

    def cube_pose_array(self) -> CubePoseArray:
        from pxr import UsdGeom  # type: ignore[import-not-found]

        assert self._stage is not None
        names, colors, positions = [], [], []
        for index in range(self.scene.n_cubes):
            prim = self._stage.GetPrimAtPath(f"/World/Cubes/Cube_{index:02d}")
            translate = UsdGeom.Xformable(prim).GetLocalTransformation().ExtractTranslation()
            names.append(f"Cube_{index:02d}")
            colors.append(str(prim.GetAttribute("lab:colorName").Get() or "unknown"))
            positions.append((float(translate[0]), float(translate[1]), float(translate[2])))
        return CubePoseArray(
            stamp=self.time_s,
            names=tuple(names),
            positions=tuple(positions),
            colors=tuple(colors),
            grasped=self._estimate_grasp(names, positions),
        )

    def _estimate_grasp(self, names, positions) -> str | None:
        """Report which cube is at the closed fingers; motion stays in PhysX."""
        if self._gripper_closure < 0.7:
            self._grasped_name = None
            return None
        from .kinematics import tool_tip

        tip = tool_tip(self.arm, self._cpu_positions()[:5])
        best_name = None
        best = 0.05
        for name, position in zip(names, positions, strict=True):
            distance = float(np.linalg.norm(np.asarray(position) - tip))
            if distance < best:
                best = distance
                best_name = name
        self._grasped_name = best_name
        return best_name

    def camera_pose(self):
        """Return the live USD camera pose in the CPU ``CameraPose`` convention."""
        from scipy.spatial.transform import Rotation  # type: ignore[import-not-found]

        from ..render.pinhole import CameraPose

        position, quat = self._camera.get_world_pose()
        rotation = Rotation.from_quat(
            [float(quat[1]), float(quat[2]), float(quat[3]), float(quat[0])]
        ).as_matrix()
        right, up, backward = rotation[:, 0], rotation[:, 1], rotation[:, 2]
        return CameraPose(
            position=np.asarray(position, dtype=float),
            rotation=np.vstack([right, -up, -backward]),
            look_at=np.asarray(self.scene.camera_look_at, dtype=float),
            up=np.asarray(self.scene.camera_up, dtype=float),
        )

    def rgb_frame(self) -> RgbFrame:
        if self._camera is None:
            raise RuntimeError("camera is not initialized")
        rgba = None
        for _ in range(10):
            rgba = self._camera.get_rgba()
            if rgba is not None and np.asarray(rgba).size:
                break
            if self._sim is not None:
                self._sim.render()
        if rgba is None or not np.asarray(rgba).size:
            raise RuntimeError("Isaac Sim camera returned an empty frame")
        rgba = np.asarray(rgba, dtype=np.uint8)
        rgb = np.ascontiguousarray(rgba[..., :3])
        return RgbFrame(
            stamp=self.time_s,
            width=self.camera.width,
            height=self.camera.height,
            encoding="rgb8",
            data=rgb.tobytes(),
        )

    # ------------------------------------------------------------------
    # control
    # ------------------------------------------------------------------
    def apply_joint_velocities(self, velocities: Sequence[float]) -> None:
        values = np.asarray(velocities, dtype=float)
        if values.shape != (5,):
            raise ValueError("joint velocity command must have 5 values")
        self._joint_velocity_command[:5] = values

    def apply_gripper(self, closure: float) -> None:
        self._gripper_command = float(np.clip(closure, 0.0, 1.0))

    def step(self) -> None:
        if self._articulation is None or self._sim is None:
            raise RuntimeError("start() must be called first")
        q = self._cpu_positions()
        target = q.copy()
        # The controller publishes v = 5 * (target - q), so q + v/5 recovers
        # its joint-space target. Bound the lead to keep the drives stable.
        lead = np.clip(self._joint_velocity_command[:5] / 5.0, -0.05, 0.05)
        target[:5] = q[:5] + lead
        for index, (low, high) in enumerate(self.arm.joint_limits):
            target[index] = min(max(target[index], low), high)
        # Ramp the close so the first jaw contact cannot flick the cube away.
        self._gripper_closure += float(
            np.clip(self._gripper_command - self._gripper_closure, -0.1, 0.1)
        )
        # The right jaw drive is sign-inverted; the same positive target closes
        # both jaws toward the tool axis.
        target[5] = GRIPPER_OPEN * self._gripper_closure
        physical = target * JOINT_SIGNS
        self._articulation.set_joint_position_targets(physical.reshape(1, -1))
        self._sim.step(render=True)
        self.tick += 1
        self.time_s = self.tick / 60.0

    def publish_all(self) -> None:
        if self._ros_bridge is None:
            return
        self._ros_bridge.publish("/lab/joint_states", self.joint_state())
        self._ros_bridge.publish("/lab/cube_poses", self.cube_pose_array())
        self._ros_bridge.publish("/lab/rgb", self.rgb_frame())

    def close(self) -> None:
        if self._ros_bridge is not None:
            self._ros_bridge.close()
        # Isaac Sim 6.0 can hang or fault in close(); artifacts are already written.
        if self._app is not None:
            self._app = None


if os.environ.get("LAB_BACKEND") == "isaac":  # pragma: no cover - GPU host only
    pass
