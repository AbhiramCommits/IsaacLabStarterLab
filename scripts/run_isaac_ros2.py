#!/usr/bin/env python3
"""Run the Isaac Sim backend as a ROS 2 topic publisher for the lab nodes.

Run with the Kit Python after sourcing ROS 2 Jazzy:

    source /opt/ros/jazzy/setup.bash
    /isaac-sim/python.sh scripts/run_isaac_ros2.py --ticks 900

The separate ``perception_node``/``controller_node`` processes subscribe to the
published topics and publish the joint/gripper commands back.
"""

from __future__ import annotations

import argparse
import time

from isaac_starter_lab.sim.isaac_backend import IsaacSimBackend
from isaac_starter_lab.sim.schema import (
    CMD_JOINT_TOPIC,
    CUBE_POSES_TOPIC,
    GRIPPER_CMD_TOPIC,
    JOINT_STATES_TOPIC,
    RGB_TOPIC,
    STATUS_TOPIC,
    LabStatus,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticks", type=int, default=900)
    parser.add_argument("--usd", default="usd/tabletop_seed7.usda")
    args = parser.parse_args()
    backend = IsaacSimBackend(usda_path=args.usd, enable_ros2=True)
    backend.start()
    bridge = backend._ros_bridge
    assert bridge is not None
    bridge.subscribe(CMD_JOINT_TOPIC, lambda m: backend.apply_joint_velocities(m.velocities))
    bridge.subscribe(GRIPPER_CMD_TOPIC, lambda m: backend.apply_gripper(m.closure))
    rgb_period = 6  # 10 Hz at 60 Hz control
    period = 1.0 / 60.0
    next_time = time.monotonic()
    for tick in range(args.ticks):
        bridge.publish(JOINT_STATES_TOPIC, backend.joint_state())
        bridge.publish(CUBE_POSES_TOPIC, backend.cube_pose_array())
        if tick % rgb_period == 0:
            bridge.publish(RGB_TOPIC, backend.rgb_frame())
        bridge.publish(
            STATUS_TOPIC,
            LabStatus(
                stamp=backend.time_s,
                tick=backend.tick,
                state="ROS2",
                success=False,
                message="",
            ),
        )
        bridge.spin_once()
        # Render only for the 10 Hz RGB message; the controller runs on a
        # wall-clock timer and needs the physics loop to keep up.
        backend.step(render=False)
        next_time += period
        delay = next_time - time.monotonic()
        if delay > 0:
            time.sleep(delay)
    print(f"published {args.ticks} ticks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
