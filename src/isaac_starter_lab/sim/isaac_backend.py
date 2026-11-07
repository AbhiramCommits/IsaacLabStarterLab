"""Isaac Sim 4.5 backend (GPU-host path).

This adapter is **not executed on the build machine** (no NVIDIA GPU, no Isaac
Sim install).  It is guarded so importing this module is always safe: the heavy
Omniverse imports happen lazily inside :meth:`IsaacSimBackend.start`, and a
missing runtime raises :class:`IsaacUnavailableError` with the exact container
and ``docker run`` command to use.

It emits the same :mod:`isaac_starter_lab.sim.schema` messages as
:class:`~isaac_starter_lab.sim.kinematic.KinematicSim`, so learner perception and
controller code is unchanged between the CPU and GPU tracks.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from ..config import LAB_SEED, ArmConfig, CameraIntrinsics, SceneConfig
from .schema import CubePoseArray, JointState, RgbFrame

__all__ = ["IsaacSimBackend", "IsaacUnavailableError"]

CONTAINER_IMAGE = "nvcr.io/nvidia/isaac-sim:4.5.0"
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


class IsaacUnavailableError(RuntimeError):
    """Raised when the Isaac Sim runtime is not importable on this host."""


def _unavailable(detail: str) -> IsaacUnavailableError:
    return IsaacUnavailableError(
        "Isaac Sim is not available on this machine "
        f"({detail}).\n"
        f"Required container: {CONTAINER_IMAGE}\n"
        "Required host: NVIDIA GPU + driver >= 535.129.03 + NVIDIA Container Toolkit.\n"
        f"Run: {DOCKER_RUN}\n"
        "Then set LAB_BACKEND=isaac (and LAB_BRIDGE=ros2)."
    )


def _import_simulation_app():
    try:  # Isaac Sim 4.5 Python package
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
    """Thin, real-API adapter around ``isaacsim.SimulationApp``.

    Construction never imports Omniverse.  Call :meth:`start` on the GPU host.
    """

    def __init__(
        self,
        scene: SceneConfig | None = None,
        arm: ArmConfig | None = None,
        seed: int = LAB_SEED,
        usda_path: str | Path = "usd/tabletop_seed7.usda",
        headless: bool = True,
        enable_ros2: bool = True,
    ) -> None:
        self.scene = scene or SceneConfig()
        self.arm = arm or ArmConfig()
        self.camera = CameraIntrinsics()
        self.seed = seed
        self.usda_path = Path(usda_path)
        self.headless = headless
        self.enable_ros2 = enable_ros2
        self._app: Any | None = None
        self._articulation: Any | None = None
        self._camera: Any | None = None
        self._ros_bridge: Any | None = None
        self.tick = 0
        self.time_s = 0.0

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def start(self) -> IsaacSimBackend:
        SimulationApp = _import_simulation_app()
        self._app = SimulationApp({"headless": self.headless, "renderer": "RayTracedLighting"})
        if not self.usda_path.exists():
            raise FileNotFoundError(
                f"USD stage not found: {self.usda_path}. Run `lab-scene --seed 7` first."
            )
        self._open_stage()
        self._setup_articulation()
        self._setup_camera()
        if self.enable_ros2:
            self._enable_ros2_bridge()
        return self

    def _open_stage(self) -> None:
        import omni.usd  # type: ignore[import-not-found]

        context = omni.usd.get_context()
        if not context.open_stage(str(self.usda_path.resolve())):
            raise RuntimeError(f"Isaac Sim could not open {self.usda_path}")
        self._update(60)

    def _setup_articulation(self) -> None:
        try:
            from isaacsim.core.prims import Articulation  # type: ignore[import-not-found]
        except ImportError:
            from omni.isaac.core.articulations import Articulation  # type: ignore[import-not-found]

        self._articulation = Articulation(prim_paths_expr="/World/Robot/base")
        self._articulation.initialize()

    def _setup_camera(self) -> None:
        try:
            from isaacsim.sensors.camera import Camera  # type: ignore[import-not-found]
        except ImportError:
            from omni.isaac.sensor import Camera  # type: ignore[import-not-found]

        self._camera = Camera(
            prim_path="/World/Camera",
            resolution=(self.camera.width, self.camera.height),
            frequency=30,
        )
        self._camera.initialize()

    def _enable_ros2_bridge(self) -> None:
        try:
            from isaacsim.core.utils.extensions import enable_extension  # type: ignore
        except ImportError:
            from omni.isaac.core.utils.extensions import enable_extension  # type: ignore

        for extension in ("isaacsim.ros2.bridge", "omni.isaac.ros2_bridge"):
            try:
                enable_extension(extension)
                break
            except Exception:  # extension name differs between Isaac Sim versions
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

    def _update(self, count: int = 1) -> None:
        if self._app is None:
            raise RuntimeError("IsaacSimBackend.start() must be called first")
        for _ in range(count):
            self._app.update()

    # ------------------------------------------------------------------
    # observation
    # ------------------------------------------------------------------
    @property
    def joint_positions(self) -> np.ndarray:
        if self._articulation is None:
            raise RuntimeError("articulation is not initialized")
        return np.asarray(self._articulation.get_joint_positions(), dtype=float)

    def joint_state(self) -> JointState:
        positions = self.joint_positions
        return JointState(
            stamp=self.time_s,
            names=self.arm.joint_names,
            positions=tuple(float(v) for v in positions),
            velocities=tuple(float(v) for v in self._articulation.get_joint_velocities()),
            gripper=0.0,
        )

    def cube_pose_array(self) -> CubePoseArray:
        import omni.usd  # type: ignore[import-not-found]
        from pxr import UsdGeom

        stage = omni.usd.get_context().get_stage()
        names, colors, positions = [], [], []
        for index in range(self.scene.n_cubes):
            prim = stage.GetPrimAtPath(f"/World/Cubes/Cube_{index:02d}")
            translate = UsdGeom.Xformable(prim).GetLocalTransformation().ExtractTranslation()
            names.append(f"Cube_{index:02d}")
            colors.append(
                str(prim.GetAttribute("lab:colorName").Get() or "unknown")
            )
            positions.append((float(translate[0]), float(translate[1]), float(translate[2])))
        return CubePoseArray(
            stamp=self.time_s,
            names=tuple(names),
            positions=tuple(positions),
            colors=tuple(colors),
        )

    def rgb_frame(self) -> RgbFrame:
        if self._camera is None:
            raise RuntimeError("camera is not initialized")
        rgba = np.asarray(self._camera.get_rgba(), dtype=np.uint8)
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
        if self._articulation is None:
            raise RuntimeError("articulation is not initialized")
        self._articulation.set_joint_velocity_targets(np.asarray(velocities, dtype=float))

    def apply_gripper(self, closure: float) -> None:
        # The teaching gripper has a single prismatic finger joint.  Its USD name
        # is resolved at runtime so the adapter keeps working if the asset changes.
        if self._articulation is None:
            return
        names = list(self._articulation.joint_names)
        if "finger_joint" in names:
            index = names.index("finger_joint")
            target = float(self.arm.gripper_open + closure * (self.arm.gripper_closed - self.arm.gripper_open))
            self._articulation.set_joint_position_targets(
                np.asarray([target]), joint_indices=np.asarray([index])
            )

    def step(self) -> None:
        self._update(1)
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
        if self._app is not None:
            self._app.close()
            self._app = None


if os.environ.get("LAB_BACKEND") == "isaac":  # pragma: no cover - GPU host only
    # A convenience for `python -m isaac_starter_lab.sim.isaac_backend`; importing
    # the module alone never touches Omniverse.
    pass
