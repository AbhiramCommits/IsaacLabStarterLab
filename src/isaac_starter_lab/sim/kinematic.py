"""Deterministic fixed-timestep kinematic simulator.

This is the CPU backend used by the lab, CI and every measured result in this
repository.  It implements the same topic schema, camera intrinsics and artifact
format as the Isaac Sim backend, but replaces rigid-body physics and RTX
rendering with analytic forward kinematics and a NumPy ray caster.

State advances only in ``step(dt)`` with ``dt = 1/60``.  There is no wall-clock
dependency and no RNG after construction, so two runs with the same seed and
commands produce byte-identical trajectories.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ..config import LAB_SEED, ArmConfig, CameraIntrinsics, SceneConfig
from ..scene.build_scene import CubePlacement, sample_cube_layout
from .kinematics import tool_tip
from .schema import CubePoseArray, JointState

__all__ = ["KinematicSim"]

DT = 1.0 / 60.0
GRAVITY = 9.81


@dataclass
class Cube:
    name: str
    color_name: str
    rgb: tuple[int, int, int]
    position: np.ndarray
    fall_speed: float = 0.0

    def copy(self) -> Cube:
        return Cube(
            name=self.name,
            color_name=self.color_name,
            rgb=self.rgb,
            position=self.position.copy(),
            fall_speed=self.fall_speed,
        )


class KinematicSim:
    """Fixed-step tabletop simulator with a 5-DOF arm and graspable cubes."""

    def __init__(
        self,
        scene: SceneConfig | None = None,
        arm: ArmConfig | None = None,
        seed: int = LAB_SEED,
        placements: Sequence[CubePlacement] | None = None,
    ) -> None:
        self.scene = scene or SceneConfig()
        self.arm = arm or ArmConfig()
        self.seed = seed
        if placements is None:
            placements = sample_cube_layout(self.scene, seed)
        self._placements = tuple(placements)
        self._initial_joints = np.asarray(self.arm.home_pose, dtype=float)
        self.reset()

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def reset(self, joints: Sequence[float] | None = None) -> None:
        start = self._initial_joints if joints is None else np.asarray(joints, dtype=float)
        if start.shape != (5,):
            raise ValueError("expected 5 joint values")
        self.joint_positions = start.copy()
        self.joint_velocities = np.zeros(5, dtype=float)
        self.gripper_closure = 0.0
        self.gripper_target = 0.0
        self.grasped_index: int | None = None
        self._grasp_offset = np.zeros(3, dtype=float)
        self.cubes = [
            Cube(
                name=p.name,
                color_name=p.color_name,
                rgb=p.rgb,
                position=np.asarray(p.position, dtype=float),
            )
            for p in self._placements
        ]
        self.tick = 0
        self.time_s = 0.0

    # ------------------------------------------------------------------
    # commands
    # ------------------------------------------------------------------
    def command_joint_velocities(self, velocities: Sequence[float]) -> None:
        values = np.asarray(velocities, dtype=float)
        if values.shape != (5,):
            raise ValueError("joint velocity command must have 5 values")
        self.joint_velocities = np.clip(values, -self.arm.max_joint_velocity, self.arm.max_joint_velocity)

    def command_gripper(self, closure: float) -> None:
        self.gripper_target = float(np.clip(closure, 0.0, 1.0))

    # ------------------------------------------------------------------
    # observation
    # ------------------------------------------------------------------
    @property
    def tool_tip(self) -> np.ndarray:
        return tool_tip(self.arm, self.joint_positions)

    @property
    def grasped_cube(self) -> Cube | None:
        return None if self.grasped_index is None else self.cubes[self.grasped_index]

    def cube_positions(self) -> np.ndarray:
        return np.asarray([c.position for c in self.cubes], dtype=float)

    def joint_state(self) -> JointState:
        return JointState(
            stamp=self.time_s,
            names=self.arm.joint_names,
            positions=tuple(float(v) for v in self.joint_positions),
            velocities=tuple(float(v) for v in self.joint_velocities),
            gripper=float(self.gripper_closure),
        )

    def cube_pose_array(self) -> CubePoseArray:
        return CubePoseArray(
            stamp=self.time_s,
            names=tuple(c.name for c in self.cubes),
            positions=tuple(tuple(float(v) for v in c.position) for c in self.cubes),
            colors=tuple(c.color_name for c in self.cubes),
            grasped=None if self.grasped_index is None else self.cubes[self.grasped_index].name,
        )

    def cube_in_bin(self, index: int) -> bool:
        cube = self.cubes[index]
        (lo_x, lo_y, _), (hi_x, hi_y, _) = self.scene.bin_inner_aabb
        support = self.scene.table_top + self.scene.cube_size / 2.0
        return bool(
            lo_x <= cube.position[0] <= hi_x
            and lo_y <= cube.position[1] <= hi_y
            and abs(cube.position[2] - support) <= 1e-6
        )

    def render_rgb(
        self,
        intrinsics: CameraIntrinsics | None = None,
        camera_position: Sequence[float] | None = None,
        look_at: Sequence[float] | None = None,
        table_color: Sequence[int] | None = None,
        light_intensity: float | None = None,
        return_ids: bool = False,
    ):
        from ..render.pinhole import render_scene

        cubes = [(c.position, c.rgb) for c in self.cubes]
        return render_scene(
            cubes=cubes,
            scene=self.scene,
            intrinsics=intrinsics or CameraIntrinsics(),
            camera_position=camera_position or self.scene.camera_position,
            look_at=look_at or self.scene.camera_look_at,
            table_color=table_color or self.scene.table_color,
            light_intensity=self.scene.light_intensity
            if light_intensity is None
            else light_intensity,
            return_ids=return_ids,
        )

    # ------------------------------------------------------------------
    # integration
    # ------------------------------------------------------------------
    def step(self, dt: float = DT) -> None:
        self._integrate_arm(dt)
        self._integrate_gripper(dt)
        self._update_grasp()
        self._settle_cubes(dt)
        self.tick += 1
        self.time_s = self.tick * DT

    def _integrate_arm(self, dt: float) -> None:
        limits = self.arm.joint_limits
        previous = self.joint_positions.copy()
        target = previous + self.joint_velocities * dt
        clamped = np.array(
            [min(max(value, low), high) for value, (low, high) in zip(target, limits, strict=True)]
        )
        self.joint_positions = clamped
        self.joint_velocities = (clamped - previous) / dt

    def _integrate_gripper(self, dt: float) -> None:
        rate = 8.0  # full travel in 0.125 s
        delta = self.gripper_target - self.gripper_closure
        max_delta = rate * dt
        self.gripper_closure += float(np.clip(delta, -max_delta, max_delta))
        self.gripper_closure = float(np.clip(self.gripper_closure, 0.0, 1.0))

    def _update_grasp(self) -> None:
        if self.grasped_index is None:
            if self.gripper_closure < 0.75:
                return
            tip = self.tool_tip
            best_index: int | None = None
            best_distance = float("inf")
            for index, cube in enumerate(self.cubes):
                distance = float(np.linalg.norm(cube.position - tip))
                if distance < self.scene.cube_size * 0.8 and distance < best_distance:
                    best_index = index
                    best_distance = distance
            if best_index is not None:
                self.grasped_index = best_index
                self._grasp_offset = self.cubes[best_index].position - tip
                self.cubes[best_index].fall_speed = 0.0
        else:
            if self.gripper_closure <= 0.2:
                self.grasped_index = None
                return
            if self.gripper_closure > 0.2:
                cube = self.cubes[self.grasped_index]
                cube.position = self.tool_tip + self._grasp_offset

    def _settle_cubes(self, dt: float) -> None:
        support = self.scene.table_top + self.scene.cube_size / 2.0
        for index, cube in enumerate(self.cubes):
            if index == self.grasped_index:
                continue
            if cube.position[2] > support + 1e-9:
                cube.fall_speed = min(cube.fall_speed + GRAVITY * dt, 2.0)
                cube.position[2] = max(support, cube.position[2] - cube.fall_speed * dt)
            else:
                cube.position[2] = support
                cube.fall_speed = 0.0

    # ------------------------------------------------------------------
    # deterministic scripted helpers (tests and tutorials)
    # ------------------------------------------------------------------
    def set_joint_positions(self, joints: Sequence[float]) -> None:
        """Teleport the arm.  Only used by tests and scripted tutorials."""
        values = np.asarray(joints, dtype=float)
        if values.shape != (5,):
            raise ValueError("expected 5 joint values")
        for value, (low, high) in zip(values, self.arm.joint_limits, strict=True):
            if not low - 1e-9 <= value <= high + 1e-9:
                raise ValueError(f"joint value {value} outside limits")
        self.joint_positions = values.copy()
        self.joint_velocities = np.zeros(5, dtype=float)
