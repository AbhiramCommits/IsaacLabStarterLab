"""ROS 2 controller node: a thin wrapper around ``PickPlaceController``.

Run:

    ros2 run starter_lab controller_node --ros-args -p target_color:=green

The node uses the shared :class:`~isaac_starter_lab.bridge.ros2_bridge.Ros2Bridge`
for both directions, so the exact state machine that runs against the local bus
also runs here.  It publishes a compact JSON status on ``/lab/controller_state``.
"""

from __future__ import annotations

import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from isaac_starter_lab.bridge.ros2_bridge import Ros2Bridge
from isaac_starter_lab.config import ArmConfig, CameraIntrinsics, SceneConfig
from isaac_starter_lab.controller import PickPlaceController


class ControllerNode(Node):
    def __init__(self) -> None:
        super().__init__("starter_lab_controller")
        self.declare_parameter("target_color", "green")
        self.declare_parameter("max_ticks", 4000)
        target = self.get_parameter("target_color").get_parameter_value().string_value
        max_ticks = self.get_parameter("max_ticks").get_parameter_value().integer_value
        self._bridge = Ros2Bridge(node_name="starter_lab_controller_bridge")
        self._controller = PickPlaceController(
            SceneConfig(),
            ArmConfig(),
            CameraIntrinsics(),
            self._bridge,
            target_color=target,
            max_ticks=max_ticks,
        )
        self._status = self.create_publisher(String, "/lab/controller_state", 10)
        self._timer = self.create_timer(1.0 / 60.0, self._on_timer)

    def _on_timer(self) -> None:
        self._bridge.spin_once()
        self._controller.step()
        message = String()
        message.data = json.dumps(
            {
                "state": self._controller.state,
                "success": self._controller.success,
                "failure_reason": self._controller.failure_reason,
                "tick": self._controller.tick,
            },
            sort_keys=True,
        )
        self._status.publish(message)

    def destroy_node(self) -> bool:
        self._bridge.close()
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ControllerNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
