#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Get script directory and change to it
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Create assets directory if it doesn't exist
mkdir -p assets

# 2. Clone or update the Lslidar driver repository in the assets directory
DRIVER_DIR="assets/Lslidar_ROS2_driver"
if [ ! -d "$DRIVER_DIR" ]; then
    echo "=================================================="
    echo "📥 Cloning Lslidar_ROS2_driver (branch: LS-S1_V1.0)..."
    echo "=================================================="
    git clone -b LS-S1_V1.0 https://github.com/Lslidar/Lslidar_ROS2_driver.git "$DRIVER_DIR"
else
    echo "=================================================="
    echo "🔄 Lslidar_ROS2_driver already exists. Updating..."
    echo "=================================================="
    cd "$DRIVER_DIR"
    git pull origin LS-S1_V1.0
    cd "$SCRIPT_DIR"
fi

# 3. Build the docker image
echo "=================================================="
echo "🚀 Building target arm64 Docker image..."
echo "=================================================="
docker buildx build --platform linux/arm64 -t r550-humble-bot:latest .
