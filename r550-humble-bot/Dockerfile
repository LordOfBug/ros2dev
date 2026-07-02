# syntax=docker/dockerfile:1

# =========================================================================
# STAGE 1: Builder (Compiles source code under emulation)
# =========================================================================
FROM arm64v8/ros:humble-perception AS builder

ENV DEBIAN_FRONTEND=noninteractive

# Install build dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-colcon-common-extensions \
    libpcap-dev

# Setup workspace
WORKDIR /workspace

# Copy Lslidar ROS2 driver source code
COPY assets/Lslidar_ROS2_driver /workspace/src/Lslidar_ROS2_driver

# Compile the driver workspace (release mode)
RUN . /opt/ros/humble/setup.sh && \
    colcon build --merge-install --cmake-args -DCMAKE_BUILD_TYPE=Release

# =========================================================================
# STAGE 2: Runner (Clean, optimized production image for the robot)
# =========================================================================
FROM arm64v8/ros:humble-perception

ENV DEBIAN_FRONTEND=noninteractive

# SYSTEM LAYER: Base acceleration packages
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends eatmydata

# LAYER 1: Core Navigation & Heavy Stacks (Permanently Cached 🛡️)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && eatmydata apt-get install -y --no-install-recommends \
    ros-humble-turtlesim \
    ros-humble-nav2-msgs \
    ros-humble-navigation2 \
    ros-humble-nav2-common

# LAYER 2: Modeling, States, & Math Tools (Cached unless modified 📦)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    eatmydata apt-get install -y --no-install-recommends \
    ros-humble-joint-state-publisher \
    ros-humble-robot-state-publisher \
    ros-humble-xacro \
    ros-humble-tf-transformations \
    python3-transforms3d

# LAYER 3: Dynamic Hardware Drivers & Testing (Fast Iteration Zone ⚡)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    eatmydata apt-get install -y --no-install-recommends \
    ros-humble-imu-filter-madgwick \
    ros-humble-robot-localization \
    ros-humble-teleop-twist-keyboard \
    ros-humble-orbbec-camera \
    ros-humble-depthimage-to-laserscan \
    libpcap-dev

# Copy the compiled binaries and installations from the builder stage
COPY --from=builder /workspace/install /workspace/install

# Set the default workspace folder
WORKDIR /workspace
