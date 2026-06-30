#!/bin/bash
set -e

# Source ROS 2 underlay
source /opt/ros/humble/setup.bash

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
