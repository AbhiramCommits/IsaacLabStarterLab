"""ROS 2 transport using ``rclpy``.

Imports are guarded: constructing this class on a machine without ROS 2 raises
:class:`Ros2UnavailableError` with the setup commands instead of an ImportError
traceback.  Image and joint data use real ``sensor_msgs`` types; the remaining
lab messages travel as JSON in ``std_msgs/String`` so the schema stays observable
with ``ros2 topic echo``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ..sim.schema import (
    JOINT_STATES_TOPIC,
    MESSAGE_TYPES,
    RGB_TOPIC,
    JointState,
    RgbFrame,
)

__all__ = ["Ros2Bridge", "Ros2UnavailableError"]


class Ros2UnavailableError(RuntimeError):
    """Raised when ``rclpy`` cannot be imported or initialised."""


class Ros2Bridge:
    def __init__(self, node_name: str = "isaac_starter_lab") -> None:
        try:
            import rclpy
            from geometry_msgs.msg import TransformStamped  # noqa: F401
            from sensor_msgs.msg import Image
            from sensor_msgs.msg import JointState as RosJointState
            from std_msgs.msg import String
        except ImportError as exc:
            raise Ros2UnavailableError(
                "ROS 2 Python bindings (rclpy) are not available in this Python.\n"
                "Install ROS 2 Humble/Jazzy and source it before running the lab:\n"
                "  source /opt/ros/humble/setup.bash\n"
                "  python -c 'import rclpy; print(rclpy.__file__)'\n"
                "Or keep the CPU track: LAB_BRIDGE=localbus."
            ) from exc

        self._rclpy = rclpy
        self._Image = Image
        self._RosJointState = RosJointState
        self._String = String
        self._owns_context = not rclpy.ok()
        if self._owns_context:
            rclpy.init()
        self._node = rclpy.create_node(node_name)
        self._publishers: dict[str, Any] = {}
        self._subscriptions: dict[str, list[Callable[[Any], None]]] = {}
        self._ros_subscriptions = []
        for topic in MESSAGE_TYPES:
            ros_type = self._ros_type(topic)
            self._publishers[topic] = self._node.create_publisher(ros_type, topic, 10)
        self._node.get_logger().info(f"IsaacLabStarterLab ROS 2 bridge up on {node_name}")

    # ------------------------------------------------------------------
    # conversions
    # ------------------------------------------------------------------
    def _ros_type(self, topic: str):
        if topic == JOINT_STATES_TOPIC:
            return self._RosJointState
        if topic == RGB_TOPIC:
            return self._Image
        return self._String

    def _stamp(self, message: Any):
        stamp = self._rclpy.time.Time(seconds=float(message.stamp)).to_msg()
        return stamp

    def _to_ros(self, topic: str, message: Any):
        if topic == JOINT_STATES_TOPIC:
            ros = self._RosJointState()
            ros.header.stamp = self._stamp(message)
            ros.name = list(message.names) + ["gripper"]
            ros.position = list(message.positions) + [float(message.gripper)]
            ros.velocity = list(message.velocities) + [0.0]
            return ros
        if topic == RGB_TOPIC:
            ros = self._Image()
            ros.header.stamp = self._stamp(message)
            ros.height = message.height
            ros.width = message.width
            ros.encoding = message.encoding
            ros.is_bigendian = 0
            ros.step = message.width * 3
            ros.data = message.data
            return ros
        ros = self._String()
        ros.data = json.dumps(message.to_dict(), sort_keys=True, separators=(",", ":"))
        return ros

    def _from_ros(self, topic: str, ros: Any):
        if topic == JOINT_STATES_TOPIC:
            names = list(ros.name)
            positions = list(ros.position)
            gripper = 0.0
            if names and names[-1] == "gripper":
                names = names[:-1]
                gripper = float(positions.pop())
            return JointState(
                stamp=ros.header.stamp.sec + ros.header.stamp.nanosec * 1e-9,
                names=tuple(names),
                positions=tuple(float(v) for v in positions),
                velocities=tuple(float(v) for v in list(ros.velocity)[: len(names)]),
                gripper=gripper,
            )
        if topic == RGB_TOPIC:
            return RgbFrame(
                stamp=ros.header.stamp.sec + ros.header.stamp.nanosec * 1e-9,
                width=int(ros.width),
                height=int(ros.height),
                encoding=str(ros.encoding),
                data=bytes(ros.data),
            )
        payload = json.loads(ros.data)
        return MESSAGE_TYPES[topic].from_dict(payload)

    # ------------------------------------------------------------------
    # Bridge protocol
    # ------------------------------------------------------------------
    def publish(self, topic: str, message: Any) -> None:
        if topic not in MESSAGE_TYPES:
            raise ValueError(f"unknown lab topic {topic!r}")
        expected = MESSAGE_TYPES[topic]
        if not isinstance(message, expected):
            raise TypeError(f"topic {topic} expects {expected.__name__}")
        self._publishers[topic].publish(self._to_ros(topic, message))

    def subscribe(self, topic: str, callback: Callable[[Any], None]) -> None:
        if topic not in MESSAGE_TYPES:
            raise ValueError(f"unknown lab topic {topic!r}")
        self._subscriptions.setdefault(topic, []).append(callback)
        ros_type = self._ros_type(topic)

        def _dispatch(ros_message):
            message = self._from_ros(topic, ros_message)
            for registered in list(self._subscriptions[topic]):
                registered(message)

        self._ros_subscriptions.append(
            self._node.create_subscription(ros_type, topic, _dispatch, 10)
        )

    def spin_once(self) -> int:
        self._rclpy.spin_once(self._node, timeout_sec=0.0)
        return 1

    def close(self) -> None:
        for subscription in self._ros_subscriptions:
            self._node.destroy_subscription(subscription)
        self._ros_subscriptions.clear()
        self._node.destroy_node()
        if self._owns_context:
            self._rclpy.shutdown()
