#!/bin/bash
set -e

# Source ROS 2 underlay
source /opt/ros/humble/setup.bash

# Wait for ROS1 master if running the bridge (default command)
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
    echo "ROS 1 Master is active."
fi

# Source compiled overlays (inherited from bridge image)
for ws in \
    /ros_tutorials/install/setup.bash \
    /common_tutorials/install/setup.bash \
    /control_msgs_ros1/install/setup.bash \
    /control_msgs_ros2/install/setup.bash \
    /custom_action/install/setup.bash \
    /ros-humble-ros1-bridge/install/setup.bash; do
    [ -f "$ws" ] && source "$ws"
done

# Source the relay node workspace
[ -f "/workspace/install/setup.bash" ] && source /workspace/install/setup.bash

if [ "$#" -eq 0 ]; then
    # Start ros1_bridge in background
    echo "Starting ros1_bridge dynamic_bridge..."
    ros2 run ros1_bridge dynamic_bridge &
    BRIDGE_PID=$!

    # Start relay node in foreground (keeps container alive)
    echo "Starting r550_autoware_relay..."
    exec ros2 launch r550_autoware_relay relay_launch.py
else
    exec "$@"
fi
