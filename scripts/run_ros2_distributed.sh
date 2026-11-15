#!/usr/bin/env bash
# Run the distributed ROS 2 track: Isaac Sim publisher + controller + perception.
#
# Prerequisites inside the Isaac Sim 6.0 pod:
#   - ROS 2 Jazzy installed at /opt/ros/jazzy
#   - the ament package built: (cd ros2_ws && colcon build --packages-select starter_lab)
#   - isaac_starter_lab installed in BOTH /usr/bin/python3 and /isaac-sim/python.sh
#
# Usage: bash scripts/run_ros2_distributed.sh [ticks]
set -u

TICKS="${1:-3600}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck disable=SC1091
source /opt/ros/jazzy/setup.bash
# shellcheck disable=SC1091
source "${REPO_DIR}/ros2_ws/install/setup.bash"
cd "${REPO_DIR}" || exit 1

pkill -x controller_node 2>/dev/null || true
pkill -x perception_node 2>/dev/null || true
pkill -f 'scripts/run_isaac_ros2.py' 2>/dev/null || true
sleep 2

nohup /isaac-sim/python.sh scripts/run_isaac_ros2.py --ticks "${TICKS}" \
  > /tmp/ros_sim.log 2>&1 &

# Wait for a real joint-state message, not just a stale topic registration.
for _ in $(seq 1 90); do
  if timeout 3 ros2 topic echo /lab/joint_states --once >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

nohup ros2 run starter_lab controller_node \
  --ros-args -p target_color:=green -p center_offset:=true \
  > /tmp/controller_node.log 2>&1 &
nohup ros2 run starter_lab perception_node \
  --ros-args -p target_color:=green \
  > /tmp/perception_node.log 2>&1 &

echo "nodes_started"
