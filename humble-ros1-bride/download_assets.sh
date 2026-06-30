#!/bin/bash
set -e

# Directory where assets will be stored
ASSETS_DIR="$(dirname "$0")/assets"
mkdir -p "$ASSETS_DIR"

echo "Downloading source tarballs into $ASSETS_DIR..."

download_tarball() {
    local url=$1
    local dest="$ASSETS_DIR/$2"
    
    if [ -f "$dest" ]; then
        echo "Asset $2 already exists, skipping."
        return
    fi
    
    echo "Downloading $2..."
    if command -v curl >/dev/null 2>&1; then
        curl -L "$url" -o "$dest"
    elif command -v wget >/dev/null 2>&1; then
        wget "$url" -O "$dest"
    else
        echo "Error: Neither curl nor wget is installed on the host. Please install curl or wget." >&2
        exit 1
    fi
}

download_tarball "https://github.com/ros/ros_tutorials/archive/refs/heads/noetic-devel.tar.gz" "ros_tutorials.tar.gz"
download_tarball "https://github.com/ros/common_tutorials/archive/refs/heads/fuerte-devel.tar.gz" "common_tutorials.tar.gz"
download_tarball "https://github.com/ros-controls/control_msgs/archive/refs/heads/kinetic-devel.tar.gz" "control_msgs_ros1.tar.gz"
download_tarball "https://github.com/ros-controls/control_msgs/archive/refs/heads/humble.tar.gz" "control_msgs_ros2.tar.gz"
download_tarball "https://github.com/smith-doug/bridge_mapping/archive/refs/heads/master.tar.gz" "bridge_mapping.tar.gz"
download_tarball "https://github.com/smith-doug/ros1_bridge/archive/refs/heads/action_bridge_humble.tar.gz" "ros1_bridge.tar.gz"

echo "All assets downloaded successfully!"
