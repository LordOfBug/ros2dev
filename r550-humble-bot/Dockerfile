# syntax=docker/dockerfile:1

# =========================================================================
# STAGE 1: Builder (Compiles source code under emulation)
# =========================================================================
FROM arm64v8/ros:humble-perception AS builder

ENV DEBIAN_FRONTEND=noninteractive
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

# Install build dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-colcon-common-extensions \
    libpcap-dev \
    ros-humble-turtlesim \
    ros-humble-nav2-msgs \
    ros-humble-navigation2 \
    ros-humble-nav2-common \
    ros-humble-joint-state-publisher \
    ros-humble-robot-state-publisher \
    ros-humble-xacro \
    ros-humble-tf-transformations \
    python3-transforms3d \
    ros-humble-imu-filter-madgwick \
    ros-humble-robot-localization \
    ros-humble-teleop-twist-keyboard \
    ros-humble-image-geometry \
    ros-humble-image-publisher \
    ros-humble-depthimage-to-laserscan \
    ros-humble-rmw-cyclonedds-cpp \
    ros-humble-diagnostic-updater \
    libgflags-dev \
    libgoogle-glog-dev \
    libuvc-dev \
    libusb-1.0-0-dev \
    libeigen3-dev

# Setup workspace
WORKDIR /workspace

# 1. Copy stable dependency packages first (cached layer)
COPY assets/serial-ros2 /workspace/src/serial-ros2
COPY assets/rplidar_ros /workspace/src/rplidar_ros
COPY assets/wheeltec_robot_msg /workspace/src/wheeltec_robot_msg

# Compile stable dependencies
RUN . /opt/ros/humble/setup.sh && \
    colcon build --merge-install --cmake-args -DCMAKE_BUILD_TYPE=Release

# 2. Copy the remaining driver packages
COPY assets/ /workspace/src/

# Compile the remaining packages (colcon will skip the already compiled ones)
RUN . /opt/ros/humble/setup.sh && \
    colcon build --merge-install --cmake-args -DCMAKE_BUILD_TYPE=Release

# =========================================================================
# STAGE 2: Runner (Clean, optimized production image for the robot)
# =========================================================================
FROM arm64v8/ros:humble-perception

ENV DEBIAN_FRONTEND=noninteractive
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

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
    ros-humble-image-geometry \
    ros-humble-image-publisher \
    ros-humble-depthimage-to-laserscan \
    ros-humble-rmw-cyclonedds-cpp \
    ros-humble-diagnostic-updater \
    libgflags-dev \
    libgoogle-glog-dev \
    libuvc-dev \
    libusb-1.0-0-dev \
    libeigen3-dev \
    libpcap-dev

# Copy the compiled binaries and installations from the builder stage
COPY --from=builder /workspace/install /workspace/install

# Set the default workspace folder
WORKDIR /workspace
