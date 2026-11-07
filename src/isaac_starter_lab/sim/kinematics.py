"""Analytic forward and inverse kinematics for the 5-DOF tabletop arm.

Conventions
-----------
* world is Z up, the arm base sits at ``ArmConfig.base_position``
* joint 0 yaws the whole arm around +Z
* joints 1 and 2 are shoulder/elbow pitch around +Y in the arm plane
* joint 3 is wrist pitch around +Y
* joint 4 rolls the gripper around its tool axis (+X)
* ``q1``/``q2`` are measured from horizontal; positive rotation lifts the link

The tool tip is ``wrist_length + tool_length`` past the wrist centre along the
tool axis.  The controller keeps the tool vertical at the grasp point, which
makes the inverse kinematics a planar two-link solve plus a wrist correction.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ..config import ArmConfig

__all__ = ["ArmPose", "forward_kinematics", "inverse_kinematics", "tool_tip"]


@dataclass(frozen=True)
class ArmPose:
    base: tuple[float, float, float]
    shoulder: tuple[float, float, float]
    elbow: tuple[float, float, float]
    wrist: tuple[float, float, float]
    tip: tuple[float, float, float]
    tool_pitch: float


def forward_kinematics(arm: ArmConfig, joints: Sequence[float]) -> ArmPose:
    q = [float(v) for v in joints]
    if len(q) != 5:
        raise ValueError("expected 5 joint values")
    bx, by, bz = arm.base_position
    yaw, q1, q2, q3, _roll = q
    shoulder = (bx, by, bz + arm.base_height)

    radial_elbow = arm.link1_length * math.cos(q1)
    vertical_elbow = arm.link1_length * math.sin(q1)
    radial_wrist = radial_elbow + arm.link2_length * math.cos(q1 + q2)
    vertical_wrist = vertical_elbow + arm.link2_length * math.sin(q1 + q2)
    total_pitch = q1 + q2 + q3
    radial_tip = radial_wrist + arm.tool_offset * math.cos(total_pitch)
    vertical_tip = vertical_wrist + arm.tool_offset * math.sin(total_pitch)

    cy, sy = math.cos(yaw), math.sin(yaw)

    def world(radial: float, vertical: float) -> tuple[float, float, float]:
        return (bx + radial * cy, by + radial * sy, shoulder[2] + vertical)

    return ArmPose(
        base=(bx, by, bz),
        shoulder=shoulder,
        elbow=world(radial_elbow, vertical_elbow),
        wrist=world(radial_wrist, vertical_wrist),
        tip=world(radial_tip, vertical_tip),
        tool_pitch=total_pitch,
    )


def tool_tip(arm: ArmConfig, joints: Sequence[float]) -> np.ndarray:
    return np.asarray(forward_kinematics(arm, joints).tip, dtype=float)


def inverse_kinematics(
    arm: ArmConfig,
    target: Sequence[float],
    tool_pitch: float = -math.pi / 2.0,
    elbow_up: bool = False,
) -> np.ndarray | None:
    """Solve joint angles that put the tool tip at ``target``.

    Returns ``None`` when the target is outside the workspace or the required
    angles violate the configured joint limits.  ``tool_pitch`` is the world
    pitch of the tool axis; the default points the gripper straight down.
    """
    if len(target) != 3:
        raise ValueError("target must be a 3-vector")
    bx, by, _bz = arm.base_position
    x, y, z = (float(v) for v in target)
    dx, dy = x - bx, y - by
    yaw = math.atan2(dy, dx)
    radius = math.hypot(dx, dy)

    # Move the target back along the tool axis to the wrist centre.
    wrist_radius = radius - arm.tool_offset * math.cos(tool_pitch)
    wrist_height = (z - arm.tool_offset * math.sin(tool_pitch)) - arm.shoulder_z

    reach_sq = wrist_radius**2 + wrist_height**2
    l1, l2 = arm.link1_length, arm.link2_length
    cos_elbow = (reach_sq - l1 * l1 - l2 * l2) / (2.0 * l1 * l2)
    if not -1.0 <= cos_elbow <= 1.0:
        return None
    elbow = math.acos(max(-1.0, min(1.0, cos_elbow)))
    if not elbow_up:
        elbow = -elbow
    shoulder = math.atan2(wrist_height, wrist_radius) - math.atan2(
        l2 * math.sin(elbow), l1 + l2 * math.cos(elbow)
    )
    wrist = tool_pitch - shoulder - elbow
    joints = np.array([yaw, shoulder, elbow, wrist, 0.0], dtype=float)
    for value, (low, high) in zip(joints, arm.joint_limits, strict=True):
        if not low - 1e-9 <= value <= high + 1e-9:
            return None
    return joints
