"""Schema round-trips, LocalBus ordering, bridge selection and ROS 2 packaging."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from isaac_starter_lab.bridge import LocalBus, Ros2UnavailableError, make_bridge
from isaac_starter_lab.bridge.ros2_bridge import Ros2Bridge
from isaac_starter_lab.config import ArmConfig
from isaac_starter_lab.sim.schema import (
    GRIPPER_CMD_TOPIC,
    JOINT_STATES_TOPIC,
    MESSAGE_TYPES,
    CubePoseArray,
    GripperCommand,
    JointCommand,
    JointState,
    LabStatus,
    RgbFrame,
)

ROOT = Path(__file__).resolve().parents[1]


def sample_messages():
    return [
        JointState(
            stamp=1.25,
            names=ArmConfig().joint_names,
            positions=(0.1, 0.2, -0.3, 0.4, 0.5),
            velocities=(0.01, 0.02, 0.03, 0.04, 0.05),
            gripper=0.5,
        ),
        RgbFrame(
            stamp=2.5,
            width=2,
            height=2,
            encoding="rgb8",
            data=bytes(range(12)),
        ),
        CubePoseArray(
            stamp=3.0,
            names=("Cube_00", "Cube_01"),
            positions=((0.1, 0.2, 0.775), (0.3, -0.1, 0.775)),
            colors=("red", "blue"),
            grasped="Cube_01",
        ),
        JointCommand(stamp=4.0, velocities=(0.1, -0.1, 0.2, 0.0, 0.3)),
        GripperCommand(stamp=5.0, closure=0.75),
        LabStatus(stamp=6.0, tick=360, state="DONE", success=True, message=""),
    ]


def test_localbus_round_trips_every_message_type():
    bus = LocalBus()
    received = []

    for topic in MESSAGE_TYPES:
        bus.subscribe(topic, lambda message, t=topic: received.append((t, message)))

    messages = sample_messages()
    for message in messages:
        bus.publish(message.TOPIC, message)
    count = bus.spin_once()
    assert count == len(messages)
    assert [topic for topic, _ in received] == [message.TOPIC for message in messages]
    for (topic, message), original in zip(received, messages, strict=True):
        assert message.to_dict() == original.to_dict()
        assert type(message).__name__ == MESSAGE_TYPES[topic].__name__


def test_localbus_is_fifo_and_defers_callback_publication():
    bus = LocalBus()
    order = []

    def on_joint(_message):
        order.append("joint")
        bus.publish(GRIPPER_CMD_TOPIC, GripperCommand(stamp=0.0, closure=0.0))

    bus.subscribe(JOINT_STATES_TOPIC, on_joint)
    bus.subscribe(GRIPPER_CMD_TOPIC, lambda _message: order.append("gripper"))
    bus.publish(
        JOINT_STATES_TOPIC,
        JointState(
            stamp=0.0,
            names=("a",),
            positions=(0.0,),
            velocities=(0.0,),
            gripper=0.0,
        ),
    )
    bus.spin_once()
    assert order == ["joint"]
    bus.spin_once()
    assert order == ["joint", "gripper"]


def test_localbus_rejects_wrong_types_and_topics():
    bus = LocalBus()
    with pytest.raises(ValueError, match="unknown lab topic"):
        bus.publish("/nope", LabStatus(stamp=0, tick=0, state="DONE", success=True))
    with pytest.raises(TypeError, match="expects JointState"):
        bus.publish(JOINT_STATES_TOPIC, LabStatus(stamp=0, tick=0, state="DONE", success=True))
    with pytest.raises(ValueError):
        bus.subscribe("/nope", lambda _: None)


def test_make_bridge_default_and_env(monkeypatch):
    monkeypatch.delenv("LAB_BRIDGE", raising=False)
    assert isinstance(make_bridge(None), LocalBus)
    monkeypatch.setenv("LAB_BRIDGE", "localbus")
    assert isinstance(make_bridge(None), LocalBus)
    with pytest.raises(ValueError, match="unknown bridge"):
        make_bridge("carrier-pigeon")


def test_ros2_bridge_reports_missing_rclpy(monkeypatch):
    monkeypatch.setitem(sys.modules, "rclpy", None)
    monkeypatch.setitem(sys.modules, "sensor_msgs", None)
    with pytest.raises(Ros2UnavailableError) as excinfo:
        Ros2Bridge()
    message = str(excinfo.value)
    assert "rclpy" in message
    assert "source /opt/ros" in message
    assert "LAB_BRIDGE=localbus" in message


def test_schema_validation():
    with pytest.raises(ValueError):
        JointState(stamp=0, names=("a",), positions=(0.0, 1.0), velocities=(0.0,), gripper=0)
    with pytest.raises(ValueError):
        RgbFrame(stamp=0, width=2, height=2, encoding="rgb8", data=b"short")
    with pytest.raises(ValueError):
        CubePoseArray(stamp=0, names=("a",), positions=(), colors=("red",))
    with pytest.raises(ValueError):
        GripperCommand(stamp=0, closure=1.5)
    with pytest.raises(ValueError):
        RgbFrame(stamp=0, width=1, height=1, encoding="bgr8", data=b"abc")


def test_schema_json_serialisable():
    for message in sample_messages():
        encoded = json.dumps(message.to_dict(), sort_keys=True)
        decoded = MESSAGE_TYPES[message.TOPIC].from_dict(json.loads(encoded))
        assert decoded.to_dict() == message.to_dict()


def test_ros2_package_is_a_real_ament_python_package():
    package = ROOT / "ros2_ws" / "src" / "starter_lab"
    assert (package / "package.xml").exists()
    assert (package / "setup.py").exists()
    assert (package / "setup.cfg").exists()
    assert (package / "resource" / "starter_lab").exists()
    assert (package / "starter_lab" / "perception_node.py").exists()
    assert (package / "starter_lab" / "controller_node.py").exists()
    package_xml = (package / "package.xml").read_text()
    assert "<name>starter_lab</name>" in package_xml
    assert "<exec_depend>rclpy</exec_depend>" in package_xml
    setup_py = (package / "setup.py").read_text()
    assert "perception_node = starter_lab.perception_node:main" in setup_py
    assert "controller_node = starter_lab.controller_node:main" in setup_py
