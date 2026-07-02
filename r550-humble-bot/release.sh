#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Get script directory and change to it
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Create assets directory if it doesn't exist
mkdir -p assets

# Helper function to manage standard git repositories
# Usage: manage_repo <repo_url> <branch> <target_dir>
manage_repo() {
    local url=$1
    local branch=$2
    local dir=$3
    if [ ! -d "$dir" ]; then
        echo "=================================================="
        echo "📥 Cloning $(basename "$dir") (branch: $branch)..."
        echo "=================================================="
        git clone -b "$branch" "$url" "$dir"
    else
        echo "=================================================="
        echo "🔄 $(basename "$dir") already exists. Updating..."
        echo "=================================================="
        cd "$dir"
        git pull origin "$branch"
        cd "$SCRIPT_DIR"
    fi
}

echo "=================================================="
echo "🏁 Starting Driver Source Sync..."
echo "=================================================="

# 1. Clone Lslidar ROS2 driver (branch: LS-S1_V1.0)
manage_repo "git@github.com:Lslidar/Lslidar_ROS2_driver.git" "LS-S1_V1.0" "assets/Lslidar_ROS2_driver"

# 2. Clone RPLiDAR ROS2 driver (branch: ros2)
manage_repo "git@github.com:Slamtec/rplidar_ros.git" "ros2" "assets/rplidar_ros"

# 3. Clone serial port driver
if [ ! -d "assets/serial-ros2" ]; then
    echo "=================================================="
    echo "📥 Cloning serial-ros2..."
    echo "=================================================="
    git clone git@github.com:RoverRobotics-forks/serial-ros2.git "assets/serial-ros2"
else
    echo "=================================================="
    echo "🔄 serial-ros2 already exists. Updating..."
    echo "=================================================="
    cd "assets/serial-ros2"
    git pull
    cd "$SCRIPT_DIR"
fi

# 4. Clone and extract Wheeltec proprietary packages (turn_on_wheeltec_robot, msg, urdf)
# We clone and update the main repository persistently in assets_cache to avoid slow clones
mkdir -p assets_cache

SHOULD_COPY=false
if [ ! -d "assets_cache/wheeltec_WS_src" ]; then
    echo "=================================================="
    echo "📥 Cloning wuyang156/wheeltec_WS_src..."
    echo "=================================================="
    git clone -b main git@github.com:wuyang156/wheeltec_WS_src.git assets_cache/wheeltec_WS_src
    SHOULD_COPY=true
else
    echo "=================================================="
    echo "🔄 wuyang156/wheeltec_WS_src already exists. Checking for updates..."
    echo "=================================================="
    BEFORE_HASH=$(git -C assets_cache/wheeltec_WS_src rev-parse HEAD)
    
    cd assets_cache/wheeltec_WS_src
    git pull origin main
    cd "$SCRIPT_DIR"
    
    AFTER_HASH=$(git -C assets_cache/wheeltec_WS_src rev-parse HEAD)
    if [ "$BEFORE_HASH" != "$AFTER_HASH" ]; then
        SHOULD_COPY=true
    fi
fi

# Also check if any of the target directories are missing in assets/
if [ ! -d "assets/turn_on_wheeltec_robot" ] || [ ! -d "assets/wheeltec_robot_msg" ] || [ ! -d "assets/wheeltec_robot_urdf" ]; then
    SHOULD_COPY=true
fi

if [ "$SHOULD_COPY" = true ]; then
    echo "=================================================="
    echo "📂 Copying updated Wheeltec packages to assets..."
    echo "=================================================="
    rm -rf assets/turn_on_wheeltec_robot assets/wheeltec_robot_msg assets/wheeltec_robot_urdf
    cp -r assets_cache/wheeltec_WS_src/turn_on_wheeltec_robot assets/
    cp -r assets_cache/wheeltec_WS_src/wheeltec_robot_msg assets/
    cp -r assets_cache/wheeltec_WS_src/wheeltec_robot_urdf assets/
else
    echo "=================================================="
    echo "✅ Wheeltec packages are already up-to-date. Skipping copy to preserve build cache."
    echo "=================================================="
fi

# 5. Build the docker image
# Save the host's current ASLR setting (default is 2)
ORIG_ASLR=$(cat /proc/sys/kernel/randomize_va_space 2>/dev/null || echo "2")

# Set up a trap to guarantee ASLR is restored upon exit (even on failure or Ctrl+C)
cleanup() {
    if [ "$ORIG_ASLR" != "0" ]; then
        echo "=================================================="
        echo "🔄 Restoring host ASLR setting to $ORIG_ASLR..."
        echo "=================================================="
        sudo sysctl kernel.randomize_va_space="$ORIG_ASLR" >/dev/null
    fi
}
trap cleanup EXIT INT TERM

if [ "$ORIG_ASLR" != "0" ]; then
    echo "=================================================="
    echo "⚠️  Temporarily disabling Host ASLR to prevent QEMU compiler segfaults..."
    echo "=================================================="
    sudo sysctl kernel.randomize_va_space=0
fi

echo "=================================================="
echo "🚀 Building target arm64 Docker image..."
echo "=================================================="
docker buildx build --platform linux/arm64 -t r550-humble-bot:latest .
