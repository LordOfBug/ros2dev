# syntax=docker/dockerfile:1
# Use the official hardware-optimized ARM64 ROS 2 Humble base image
FROM arm64v8/ros:humble-perception

# Prevent interactive prompts during apt installations
ENV DEBIAN_FRONTEND=noninteractive

# =========================================================================
# SYSTEM LAYER: Base acceleration packages
# Mounts the host package caches to completely bypass slow re-indexing
# =========================================================================
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends eatmydata

# =========================================================================
# LAYER 1: Core Navigation & Heavy Stacks (Permanently Cached 🛡️)
# This takes 15+ minutes on a clean run, but will NEVER be redownloaded.
# =========================================================================
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && eatmydata apt-get install -y --no-install-recommends \
    ros-humble-turtlesim \
    ros-humble-nav2-msgs \
    ros-humble-navigation2 \
    ros-humble-nav2-common

# =========================================================================
# LAYER 2: Modeling, States, & Math Tools (Cached unless modified 📦)
# Standard modeling layout items.
# =========================================================================
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    eatmydata apt-get install -y --no-install-recommends \
    ros-humble-joint-state-publisher \
    ros-humble-robot-state-publisher \
    ros-humble-xacro \
    ros-humble-tf-transformations \
    python3-transforms3d

# =========================================================================
# LAYER 3: Dynamic Hardware Drivers & Testing (Fast Iteration Zone ⚡)
# If you add or remove packages here, BuildKit will resolve dependencies 
# incrementally in seconds using the cached apt index! No 'rm' cleanup needed!
# =========================================================================
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    eatmydata apt-get install -y --no-install-recommends \
    ros-humble-imu-filter-madgwick \
    ros-humble-robot-localization \
    ros-humble-teleop-twist-keyboard

# Set the default workspace folder
WORKDIR /workspace
