"""End-to-end controller, episode and trajectory-determinism tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from isaac_starter_lab.bridge.localbus import LocalBus
from isaac_starter_lab.config import ArmConfig, CameraIntrinsics, SceneConfig
from isaac_starter_lab.controller import STATE_SEQUENCE, PickPlaceController
from isaac_starter_lab.episode import run_episode
from isaac_starter_lab.sim.schema import (
    CMD_JOINT_TOPIC,
    CUBE_POSES_TOPIC,
    GRIPPER_CMD_TOPIC,
    JOINT_STATES_TOPIC,
    RGB_TOPIC,
    CubePoseArray,
    JointState,
)


@pytest.mark.slow
def test_pinned_seed_reaches_done(tmp_path):
    summary = run_episode(7, out_dir=tmp_path, verbose=False)
    assert summary["success"] is True
    assert summary["state"] == "DONE"
    assert summary["failure_reason"] is None
    assert summary["ticks"] > 50
    assert summary["cycle_time_s"] > 0
    assert summary["target_color"] == "green"
    assert summary["target_cube"] == "Cube_01"

    out = Path(tmp_path)
    assert (out / "summary.json").exists()
    assert (out / "frame_000.png").exists()
    assert (out / "frame_final.png").exists()
    lines = (out / "trajectory.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == summary["ticks"]
    first = json.loads(lines[0])
    assert set(first["messages"]) >= {JOINT_STATES_TOPIC, CUBE_POSES_TOPIC}
    assert first["messages"]["/lab/joint_states"]["names"][0] == "joint_base_yaw"


@pytest.mark.slow
def test_identical_seed_is_byte_identical(tmp_path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = run_episode(7, out_dir=first_dir, verbose=False)
    second = run_episode(7, out_dir=second_dir, verbose=False)
    assert first["trajectory_sha256"] == second["trajectory_sha256"]
    for name in ("trajectory.jsonl", "summary.json", "frame_000.png", "frame_final.png"):
        assert hashlib.sha256((first_dir / name).read_bytes()).hexdigest() == hashlib.sha256(
            (second_dir / name).read_bytes()
        ).hexdigest()


def test_unreachable_target_fails_with_reason(tmp_path):
    summary = run_episode(
        7,
        out_dir=tmp_path,
        target_override=(1.5, 0.0, 0.8),
        verbose=False,
    )
    assert summary["success"] is False
    assert summary["state"] == "FAILED"
    assert summary["failure_reason"] == "IK_UNREACHABLE"
    assert summary["ticks"] < 20


def test_max_ticks_is_a_real_failure(tmp_path):
    summary = run_episode(7, out_dir=tmp_path, max_ticks=15, verbose=False)
    assert summary["success"] is False
    assert summary["failure_reason"] in ("MAX_TICKS", "TIMEOUT_LOCATE", "TIMEOUT_HOME")


def test_state_sequence_is_stable():
    assert STATE_SEQUENCE[0] == "HOME"
    assert STATE_SEQUENCE[-1] == "DONE"
    assert len(STATE_SEQUENCE) == 10
    assert STATE_SEQUENCE == (
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


def test_controller_publishes_commands_from_schema_messages():
    bus = LocalBus()
    received: list[str] = []
    bus.subscribe(CMD_JOINT_TOPIC, lambda m: received.append("joint"))
    bus.subscribe(GRIPPER_CMD_TOPIC, lambda m: received.append("gripper"))
    controller = PickPlaceController(
        SceneConfig(), ArmConfig(), CameraIntrinsics(), bus, target_color="green"
    )
    bus.publish(
        JOINT_STATES_TOPIC,
        JointState(
            stamp=0.0,
            names=ArmConfig().joint_names,
            positions=ArmConfig().home_pose,
            velocities=(0.0,) * 5,
            gripper=0.0,
        ),
    )
    bus.publish(
        CUBE_POSES_TOPIC,
        CubePoseArray(
            stamp=0.0,
            names=("Cube_00",),
            positions=((0.0, 0.0, 0.775),),
            colors=("green",),
        ),
    )
    bus.spin_once()
    controller.step()
    bus.spin_once()
    assert "joint" in received
    assert "gripper" in received
    assert controller.state in STATE_SEQUENCE


def test_controller_reports_no_detection(tmp_path):
    # A green target with a red-only cube cannot be found.
    from isaac_starter_lab.scene.build_scene import CubePlacement
    from isaac_starter_lab.sim.kinematic import KinematicSim

    placement = CubePlacement("Cube_00", (0.2, 0.0, 0.775), "red", (220, 30, 30))
    sim = KinematicSim(seed=7, placements=(placement,))
    bus = LocalBus()
    bus.subscribe(CMD_JOINT_TOPIC, lambda m: sim.command_joint_velocities(m.velocities))
    bus.subscribe(GRIPPER_CMD_TOPIC, lambda m: sim.command_gripper(m.closure))
    controller = PickPlaceController(
        SceneConfig(), ArmConfig(), CameraIntrinsics(), bus, target_color="green"
    )
    for tick in range(80):
        bus.publish(JOINT_STATES_TOPIC, sim.joint_state())
        bus.publish(CUBE_POSES_TOPIC, sim.cube_pose_array())
        if tick % 30 == 0:
            from isaac_starter_lab.sim.schema import RgbFrame

            image = sim.render_rgb()
            bus.publish(
                RGB_TOPIC,
                RgbFrame(
                    stamp=sim.time_s,
                    width=640,
                    height=480,
                    encoding="rgb8",
                    data=image.tobytes(),
                )
            )
        bus.spin_once()
        controller.step()
        bus.spin_once()
        sim.step()
    assert controller.state == "FAILED"
    assert controller.failure_reason == "NO_DETECTION"
