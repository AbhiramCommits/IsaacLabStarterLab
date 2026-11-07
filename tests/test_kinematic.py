"""Kinematics and deterministic kinematic-backend tests."""

from __future__ import annotations

import math

import numpy as np
import pytest

from isaac_starter_lab.config import ArmConfig, SceneConfig
from isaac_starter_lab.scene.build_scene import CubePlacement
from isaac_starter_lab.sim.kinematic import KinematicSim
from isaac_starter_lab.sim.kinematics import forward_kinematics, inverse_kinematics, tool_tip


def test_forward_kinematics_zero_pose_hand_computed():
    arm = ArmConfig()
    pose = forward_kinematics(arm, (0.0, 0.0, 0.0, 0.0, 0.0))
    assert pose.shoulder == pytest.approx((0.0, -0.32, 1.10))
    assert pose.elbow == pytest.approx((0.30, -0.32, 1.10))
    assert pose.wrist == pytest.approx((0.60, -0.32, 1.10))
    assert pose.tip == pytest.approx((0.72, -0.32, 1.10))
    assert pose.tool_pitch == 0.0


def test_forward_kinematics_vertical_pose_hand_computed():
    arm = ArmConfig()
    pose = forward_kinematics(arm, (0.0, math.pi / 2, 0.0, -math.pi, 0.0))
    # The upper arm and forearm both point up; the tool points down again.
    assert pose.elbow[2] == pytest.approx(1.40)
    assert pose.wrist[2] == pytest.approx(1.70)
    assert pose.tip == pytest.approx((0.0, -0.32, 1.58), abs=1e-9)


def test_inverse_kinematics_round_trip():
    arm = ArmConfig()
    for target in ((0.2, 0.0, 0.775), (0.25, 0.14, 0.86), (0.0, -0.05, 0.775), (-0.1, 0.08, 0.8)):
        joints = inverse_kinematics(arm, target)
        assert joints is not None, target
        recovered = forward_kinematics(arm, joints).tip
        assert recovered == pytest.approx(target, abs=1e-9)
        for value, (low, high) in zip(joints, arm.joint_limits, strict=True):
            assert low - 1e-9 <= value <= high + 1e-9


def test_inverse_kinematics_rejects_unreachable_target():
    assert inverse_kinematics(ArmConfig(), (1.2, 0.0, 0.8)) is None


def test_identical_seeds_produce_identical_trajectories():
    def run() -> tuple[np.ndarray, np.ndarray, list[dict]]:
        sim = KinematicSim(SceneConfig(), ArmConfig(), seed=7)
        samples = []
        for _ in range(180):
            sim.command_joint_velocities((0.4, -0.2, 0.3, 0.1, 0.5))
            sim.command_gripper(1.0)
            sim.step()
            samples.append(sim.joint_state().to_dict())
        return sim.joint_positions.copy(), sim.cube_positions(), samples

    first = run()
    second = run()
    assert np.array_equal(first[0], second[0])
    assert np.array_equal(first[1], second[1])
    assert first[2] == second[2]


def test_joint_limits_are_enforced():
    sim = KinematicSim(seed=7)
    for _ in range(500):
        sim.command_joint_velocities((100.0, -100.0, 100.0, 100.0, 100.0))
        sim.step()
    for value, (low, high) in zip(sim.joint_positions, sim.arm.joint_limits, strict=True):
        assert low <= value <= high


def _graspable(cube_position=(0.2, 0.0, 0.775)) -> tuple[KinematicSim, np.ndarray]:
    placement = CubePlacement(
        name="Cube_00",
        position=tuple(cube_position),
        color_name="red",
        rgb=(220, 30, 30),
    )
    sim = KinematicSim(seed=7, placements=(placement,))
    joints = inverse_kinematics(sim.arm, cube_position)
    assert joints is not None
    sim.set_joint_positions(joints)
    sim.command_gripper(1.0)
    for _ in range(20):
        sim.step()
    return sim, joints


def test_grasp_and_release_invariants():
    sim, grasp_joints = _graspable()
    assert sim.grasped_index == 0
    cube = sim.cubes[0]
    assert cube.position == pytest.approx(sim.tool_tip, abs=1e-9)

    lift_joints = inverse_kinematics(sim.arm, (0.2, 0.0, 0.9))
    assert lift_joints is not None
    for _ in range(120):
        error = lift_joints - sim.joint_positions
        sim.command_joint_velocities(np.clip(4.0 * error, -1.8, 1.8))
        sim.step()
    lifted_z = sim.cubes[0].position[2]
    assert lifted_z > 0.85
    assert sim.cubes[0].position == pytest.approx(sim.tool_tip, abs=1e-9)

    sim.command_joint_velocities(np.zeros(5))
    sim.command_gripper(0.0)
    for _ in range(12):
        sim.step()
    assert sim.grasped_index is None
    for _ in range(240):
        sim.step()
    assert sim.cubes[0].position[2] == pytest.approx(0.775, abs=1e-9)
    assert not sim.cube_in_bin(0)


def test_transfer_into_bin():
    sim, _ = _graspable()
    release_joints = inverse_kinematics(sim.arm, (0.25, 0.14, 0.86))
    assert release_joints is not None
    sim.set_joint_positions(release_joints)
    sim.step()
    sim.command_joint_velocities(np.zeros(5))
    sim.command_gripper(0.0)
    for _ in range(12):
        sim.step()
    for _ in range(240):
        sim.step()
    assert sim.grasped_index is None
    assert sim.cube_in_bin(0)
    assert sim.cubes[0].position[2] == pytest.approx(0.775, abs=1e-9)


def test_cube_in_bin_rejects_outside_cube():
    sim = KinematicSim(seed=7)
    assert not any(sim.cube_in_bin(i) for i in range(sim.scene.n_cubes))


def test_gripper_command_validation():
    sim = KinematicSim(seed=7)
    sim.command_gripper(2.0)
    assert sim.gripper_target == 1.0
    sim.command_gripper(-1.0)
    assert sim.gripper_target == 0.0
    with pytest.raises(ValueError):
        sim.command_joint_velocities((1.0, 2.0))
    with pytest.raises(ValueError):
        sim.set_joint_positions((0.0, 0.0, 0.0, 0.0, 99.0))


def test_tool_tip_helper_matches_forward_kinematics():
    arm = ArmConfig()
    assert tool_tip(arm, arm.home_pose) == pytest.approx(
        forward_kinematics(arm, arm.home_pose).tip
    )
