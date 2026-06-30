#!/bin/bash
set -e

# Source ROS 2 underlay
source /opt/ros/humble/setup.bash

# Check if launching the bridge, and if so, wait for ROS1 master (port 11311)
if [ "$#" -eq 0 ] || { [ "$1" = "ros2" ] && [ "$2" = "run" ] && [ "$3" = "ros1_bridge" ]; }; then
    URI="${ROS_MASTER_URI:-http://localhost:11311}"
    HOSTPORT="${URI#*//}"
    HOST="${HOSTPORT%%:*}"
    PORT="${HOSTPORT##*:}"
    PORT="${PORT%%/*}"

    echo "Waiting for ROS 1 Master (roscore) at $HOST:$PORT..."
    until timeout 1 bash -c "cat < /dev/tcp/$HOST/$PORT" 2>/dev/null; do
        sleep 1
    done
    echo "ROS 1 Master is active. Starting the bridge..."
fi

# Source compiled ROS1 packages (if built)
if [ -f "/ros_tutorials/install/setup.bash" ]; then
    source /ros_tutorials/install/setup.bash
fi

if [ -f "/common_tutorials/install/setup.bash" ]; then
    source /common_tutorials/install/setup.bash
fi

if [ -f "/control_msgs_ros1/install/setup.bash" ]; then
    source /control_msgs_ros1/install/setup.bash
fi

# Source compiled ROS2 packages (if built)
if [ -f "/control_msgs_ros2/install/setup.bash" ]; then
    source /control_msgs_ros2/install/setup.bash
fi

if [ -f "/custom_action/install/setup.bash" ]; then
    source /custom_action/install/setup.bash
fi

# Source the built ros1_bridge
if [ -f "/ros-humble-ros1-bridge/install/setup.bash" ]; then
    source /ros-humble-ros1-bridge/install/setup.bash
fi

# If no command is provided, run the dynamic bridge
if [ "$#" -eq 0 ]; then
    exec ros2 run ros1_bridge dynamic_bridge
else
    exec "$@"
fi
