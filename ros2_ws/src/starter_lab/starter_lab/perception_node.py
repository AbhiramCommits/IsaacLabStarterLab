"""ROS 2 perception node: a thin wrapper around ``isaac_starter_lab.perception``.

Run:

    ros2 run starter_lab perception_node --ros-args -p target_color:=green

It subscribes to ``/lab/rgb`` and publishes JSON detections on
``/lab/perception`` so ``ros2 topic echo /lab/perception`` shows the exact
centroids and back-projected grasp poses a learner is debugging.
"""

from __future__ import annotations

import json

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

from isaac_starter_lab.perception import detect_cubes
from isaac_starter_lab.sim.schema import RgbFrame


class PerceptionNode(Node):
    def __init__(self) -> None:
        super().__init__("starter_lab_perception")
        self.declare_parameter("target_color", "green")
        self._publisher = self.create_publisher(String, "/lab/perception", 10)
        self._subscription = self.create_subscription(
            Image, "/lab/rgb", self._on_image, 10
        )

    def _on_image(self, message: Image) -> None:
        frame = RgbFrame(
            stamp=message.header.stamp.sec + message.header.stamp.nanosec * 1e-9,
            width=message.width,
            height=message.height,
            encoding=message.encoding,
            data=bytes(message.data),
        )
        target = self.get_parameter("target_color").get_parameter_value().string_value
        detections = [d.to_dict() for d in detect_cubes(frame, target)]
        payload = String()
        payload.data = json.dumps(detections, sort_keys=True)
        self._publisher.publish(payload)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = PerceptionNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
