"""Explicit pick-and-place state machine with analytic inverse kinematics.

The controller is transport-agnostic: it consumes schema messages and publishes
``JointCommand`` / ``GripperCommand`` through a
:class:`~isaac_starter_lab.bridge.base.Bridge`.  The same class backs the local
episode runner and the ROS 2 ``controller_node``.

States::

    HOME -> LOCATE -> APPROACH -> DESCEND -> GRASP -> LIFT
         -> TRANSFER -> RELEASE -> RETREAT -> DONE

Every state has a tick timeout.  Any failure enters ``FAILED`` with a stable
reason code (``NO_DETECTION``, ``IK_UNREACHABLE``, ``GRASP_FAILED``,
``CUBE_NOT_IN_BIN`` or ``TIMEOUT_<STATE>``).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .bridge.base import Bridge
from .config import ArmConfig, CameraIntrinsics, SceneConfig
from .perception import detect_cubes
from .render.pinhole import CameraPose
from .sim.kinematics import inverse_kinematics, tool_tip
from .sim.schema import (
    CMD_JOINT_TOPIC,
    CUBE_POSES_TOPIC,
    GRIPPER_CMD_TOPIC,
    JOINT_STATES_TOPIC,
    RGB_TOPIC,
    CubePoseArray,
    GripperCommand,
    JointCommand,
    JointState,
    RgbFrame,
)

__all__ = ["PickPlaceController", "STATE_SEQUENCE"]

STATE_SEQUENCE = (
    "HOME",
    "LOCATE",
    "APPROACH",
    "DESCEND",
    "GRASP",
    "LIFT",
    "TRANSFER",
    "RELEASE",
    "RETREAT",
    "DONE",
)

STATE_TIMEOUTS = {
    "HOME": 180,
    "LOCATE": 120,
    "APPROACH": 240,
    "DESCEND": 180,
    "GRASP": 90,
    "LIFT": 240,
    "TRANSFER": 300,
    "RELEASE": 90,
    "RETREAT": 180,
}

APPROACH_HEIGHT = 0.13
LIFT_HEIGHT = 0.16
RETREAT_HEIGHT = 0.18
POSITION_GAIN = 5.0
JOINT_TOLERANCE = 0.02
FINE_TOLERANCE = 0.012


class PickPlaceController:
    def __init__(
        self,
        scene: SceneConfig,
        arm: ArmConfig,
        intrinsics: CameraIntrinsics,
        bridge: Bridge,
        *,
        target_color: str | None = None,
        target_override: Sequence[float] | None = None,
        camera_pose: CameraPose | None = None,
        center_offset: bool = False,
        max_ticks: int = 4000,
    ) -> None:
        self.scene = scene
        self.arm = arm
        self.intrinsics = intrinsics
        self.bridge = bridge
        self.target_color = target_color
        self.target_override = None if target_override is None else np.asarray(target_override, dtype=float)
        self.max_ticks = max_ticks
        self.camera_pose = camera_pose or CameraPose.from_look_at(
            scene.camera_position, scene.camera_look_at, scene.camera_up
        )
        # A rendered cube's visible-pixel centroid is on its camera-facing face,
        # about half an edge from the 3D centre. The physics grasp needs the
        # centre, so shift the target away from the camera by cube_size / 2.
        self.center_offset = center_offset

        self.state = "HOME"
        self.previous_state: str | None = None
        self.done = False
        self.success = False
        self.failure_reason: str | None = None
        self.tick = 0
        self.ticks_in_state = 0

        self.latest_joints: JointState | None = None
        self.latest_cubes: CubePoseArray | None = None
        self.latest_frame: RgbFrame | None = None
        self.target_position: np.ndarray | None = None
        self.target_cube_name: str | None = None
        self.gripper_target = 0.0

        bridge.subscribe(JOINT_STATES_TOPIC, self.on_joint_state)
        bridge.subscribe(CUBE_POSES_TOPIC, self.on_cube_poses)
        bridge.subscribe(RGB_TOPIC, self.on_frame)

    # ------------------------------------------------------------------
    # subscriptions
    # ------------------------------------------------------------------
    def on_joint_state(self, message: JointState) -> None:
        self.latest_joints = message

    def on_cube_poses(self, message: CubePoseArray) -> None:
        self.latest_cubes = message

    def on_frame(self, message: RgbFrame) -> None:
        self.latest_frame = message

    # ------------------------------------------------------------------
    # state machine
    # ------------------------------------------------------------------
    def _transition(self, state: str) -> None:
        self.previous_state = self.state
        self.state = state
        self.ticks_in_state = 0
        if state == "DONE":
            self.done = True
            self.success = bool(self._target_cube_in_bin())
            if not self.success:
                self._fail("CUBE_NOT_IN_BIN")
        elif state == "FAILED":
            self.done = True

    def abort(self, reason: str) -> None:
        """External stop (for example the episode-wide tick budget)."""
        if not self.done:
            self._fail(reason)

    def _fail(self, reason: str) -> None:
        self.failure_reason = reason
        self.previous_state = self.state if self.state != "FAILED" else self.previous_state
        self.state = "FAILED"
        self.done = True
        self.success = False

    def _target_cube_in_bin(self) -> bool:
        if self.latest_cubes is None or self.target_cube_name is None:
            return False
        if self.target_cube_name not in self.latest_cubes.names:
            return False
        index = self.latest_cubes.names.index(self.target_cube_name)
        position = self.latest_cubes.positions[index]
        (lo_x, lo_y, _), (hi_x, hi_y, _) = self.scene.bin_inner_aabb
        support = self.scene.cube_center_z
        return bool(
            lo_x <= position[0] <= hi_x
            and lo_y <= position[1] <= hi_y
            and abs(position[2] - support) <= 2e-3
        )

    def _joint_error(self, target: np.ndarray) -> float:
        if self.latest_joints is None:
            return float("inf")
        current = np.asarray(self.latest_joints.positions, dtype=float)
        return float(np.max(np.abs(target - current)))

    def _publish_commands(self, target_joints: np.ndarray | None) -> float:
        if target_joints is not None and self.latest_joints is not None:
            current = np.asarray(self.latest_joints.positions, dtype=float)
            velocities = np.clip(
                POSITION_GAIN * (target_joints - current),
                -self.arm.max_joint_velocity,
                self.arm.max_joint_velocity,
            )
            self.bridge.publish(
                CMD_JOINT_TOPIC,
                JointCommand(stamp=float(self.tick) / 60.0, velocities=tuple(float(v) for v in velocities)),
            )
        self.bridge.publish(
            GRIPPER_CMD_TOPIC,
            GripperCommand(stamp=float(self.tick) / 60.0, closure=float(self.gripper_target)),
        )
        return self._joint_error(target_joints) if target_joints is not None else float("inf")

    def _drive_to(self, target: Sequence[float]) -> float:
        joints = inverse_kinematics(self.arm, target)
        if joints is None:
            self._fail("IK_UNREACHABLE")
            return float("inf")
        error = self._publish_commands(joints)
        # A physical arm settles with a small constant joint bias; the task
        # goal is the tool tip at the target, so use that distance when it is
        # smaller than the joint-space error.
        if self.latest_joints is not None:
            tip = tool_tip(self.arm, self.latest_joints.positions)
            tip_error = float(np.linalg.norm(tip - np.asarray(target, dtype=float)))
            return min(error, tip_error)
        return error

    def _drive_joints(self, target: Sequence[float]) -> float:
        return self._publish_commands(np.asarray(target, dtype=float))

    def step(self) -> None:
        if self.done:
            return
        self.tick += 1
        self.ticks_in_state += 1
        if self.tick > self.max_ticks:
            self._fail("MAX_TICKS")
            return
        timeout = STATE_TIMEOUTS.get(self.state)
        if timeout is not None and self.ticks_in_state > timeout:
            self._fail(f"TIMEOUT_{self.state}")
            return

        if self.state == "HOME":
            error = self._drive_joints(self.arm.home_pose)
            if error <= JOINT_TOLERANCE:
                self._transition("LOCATE")

        elif self.state == "LOCATE":
            if self.target_override is not None:
                self.target_position = self.target_override.copy()
                self._transition("APPROACH")
                return
            if self.latest_frame is None:
                return
            if self.target_color is None:
                self._fail("NO_TARGET_COLOR")
                return
            detections = detect_cubes(
                self.latest_frame,
                self.target_color,
                scene=self.scene,
                intrinsics=self.intrinsics,
                pose=self.camera_pose,
            )
            if not detections:
                if self.ticks_in_state > 30:
                    self._fail("NO_DETECTION")
                return
            detection = detections[0]
            position = np.asarray(detection.position, dtype=float)
            if self.center_offset:
                ray = position[:2] - self.camera_pose.position[:2]
                norm = float(np.linalg.norm(ray))
                if norm > 1e-9:
                    position[:2] += (self.scene.cube_size / 2.0) * ray / norm
            self.target_position = position
            self.target_cube_name = self._match_cube_name(position)
            self._transition("APPROACH")

        elif self.state == "APPROACH":
            assert self.target_position is not None
            target = self.target_position + np.asarray([0.0, 0.0, APPROACH_HEIGHT])
            error = self._drive_to(target)
            if not self.done and error <= JOINT_TOLERANCE:
                self.gripper_target = 0.0
                self._transition("DESCEND")

        elif self.state == "DESCEND":
            assert self.target_position is not None
            error = self._drive_to(self.target_position)
            if not self.done and error <= FINE_TOLERANCE:
                self._transition("GRASP")

        elif self.state == "GRASP":
            self.gripper_target = 1.0
            self._drive_joints(self._current_joints())
            grasped = self.latest_cubes is not None and self.latest_cubes.grasped is not None
            if self.ticks_in_state >= 12 and grasped:
                self._transition("LIFT")
            elif self.ticks_in_state > 60:
                self._fail("GRASP_FAILED")

        elif self.state == "LIFT":
            assert self.target_position is not None
            self.gripper_target = 1.0
            target = self.target_position + np.asarray([0.0, 0.0, LIFT_HEIGHT])
            error = self._drive_to(target)
            if not self.done and error <= JOINT_TOLERANCE:
                self._transition("TRANSFER")

        elif self.state == "TRANSFER":
            self.gripper_target = 1.0
            (lo_x, lo_y, _), (hi_x, hi_y, _) = self.scene.bin_inner_aabb
            target = np.asarray(
                [
                    (lo_x + hi_x) / 2.0,
                    (lo_y + hi_y) / 2.0,
                    self.scene.bin_aabb[1][2] + self.scene.cube_size / 2.0 + 0.04,
                ]
            )
            error = self._drive_to(target)
            if not self.done and error <= JOINT_TOLERANCE:
                self._transition("RELEASE")

        elif self.state == "RELEASE":
            self.gripper_target = 0.0
            self._drive_joints(self._current_joints())
            if self.ticks_in_state >= 40:
                self._transition("RETREAT")

        elif self.state == "RETREAT":
            self.gripper_target = 0.0
            (lo_x, lo_y, _), (hi_x, hi_y, _) = self.scene.bin_inner_aabb
            target = np.asarray(
                [
                    (lo_x + hi_x) / 2.0,
                    (lo_y + hi_y) / 2.0,
                    self.scene.bin_aabb[1][2] + RETREAT_HEIGHT,
                ]
            )
            error = self._drive_to(target)
            if not self.done and (error <= JOINT_TOLERANCE or self.ticks_in_state > 90):
                self._transition("DONE")

        else:  # pragma: no cover - defensive
            self._fail(f"UNKNOWN_STATE_{self.state}")

    def _current_joints(self) -> np.ndarray:
        if self.latest_joints is None:
            return np.asarray(self.arm.home_pose, dtype=float)
        return np.asarray(self.latest_joints.positions, dtype=float)

    def _match_cube_name(self, position: Sequence[float]) -> str | None:
        if self.latest_cubes is None:
            return None
        best_name = None
        best_distance = float("inf")
        target = np.asarray(position, dtype=float)
        for name, candidate, color in zip(
            self.latest_cubes.names, self.latest_cubes.positions, self.latest_cubes.colors, strict=True
        ):
            if self.target_color is not None and color != self.target_color:
                continue
            distance = float(np.linalg.norm(np.asarray(candidate) - target))
            if distance < best_distance:
                best_name = name
                best_distance = distance
        return best_name
