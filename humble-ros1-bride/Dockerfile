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
# LAYER 1: ROS 1 Base Libraries (Ubuntu 22.04 universe)
# Temporarily disable ROS 2 sources to avoid conflicts when installing
# ROS 1 core libraries.
# =========================================================================
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    mv /etc/apt/sources.list.d/ros2.sources /root/ && \
    apt-get update && \
    sed -i -e 's|^Conflicts: catkin|#Conflicts: catkin|' /var/lib/dpkg/status && \
    apt-get install -f && \
    apt-get download python3-catkin-pkg python3-rospkg python3-rosdistro && \
    dpkg --force-overwrite -i python3-catkin-pkg*.deb python3-rospkg*.deb python3-rosdistro*.deb && \
    rm -f python3-catkin-pkg*.deb python3-rospkg*.deb python3-rosdistro*.deb && \
    apt-get install -f && \
    eatmydata apt-get install -y --no-install-recommends ros-desktop-dev && \
    if [[ $(uname -m) = "arm64" || $(uname -m) = "aarch64" ]]; then \
      cp /usr/lib/x86_64-linux-gnu/pkgconfig/* /usr/lib/aarch64-linux-gnu/pkgconfig/; \
    fi && \
    mv /root/ros2.sources /etc/apt/sources.list.d/ && \
    apt-get update

# =========================================================================
# LAYER 2: ROS 2 Dependencies & Build Tools
# Install colcon and specific ROS 2 messages needed for the bridge.
# =========================================================================
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    eatmydata apt-get install -y --no-install-recommends \
    python3-colcon-common-extensions \
    ros-humble-nav2-msgs

# =========================================================================
# LAYER 3: Build custom overlays and ros1_bridge
# Clone, compile, and clean up build-time artifacts to keep the image small.
# We install git, perform our checkouts/builds, and purge git afterwards.
# =========================================================================
ARG ADD_ros_tutorials=1
ARG ADD_custom_action_mapping=1

# Use bash for shell commands to enable sourcing setup files
SHELL ["/bin/bash", "-o", "pipefail", "-o", "errexit", "-c"]

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    eatmydata apt-get install -y --no-install-recommends git && \
    # \
    # 3.1) Build ros_tutorials (ROS 1) \
    if [[ "$ADD_ros_tutorials" = "1" ]]; then \
      git clone -b noetic-devel --depth=1 https://github.com/ros/ros_tutorials.git /ros_tutorials; \
      cd /ros_tutorials; \
      unset ROS_DISTRO; \
      colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release; \
      mv install /tmp_install && rm -rf * && mv /tmp_install install; \
      \
      source /ros_tutorials/install/setup.bash; \
      git clone -b fuerte-devel --depth=1 https://github.com/ros/common_tutorials.git /common_tutorials; \
      cd /common_tutorials; \
      unset ROS_DISTRO; \
      colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release; \
      mv install /tmp_install && rm -rf * && mv /tmp_install install; \
    fi && \
    # \
    # 3.2) Build custom action mapping \
    if [[ "$ADD_custom_action_mapping" = "1" ]]; then \
      git clone --depth=1 -b kinetic-devel https://github.com/ros-controls/control_msgs.git /control_msgs_ros1; \
      cd /control_msgs_ros1; \
      unset ROS_DISTRO; \
      colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release; \
      mv install /tmp_install && rm -rf * && mv /tmp_install install; \
      \
      git clone --depth=1 -b humble https://github.com/ros-controls/control_msgs.git /control_msgs_ros2; \
      cd /control_msgs_ros2; \
      source /opt/ros/humble/setup.bash; \
      colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release; \
      mv install /tmp_install && rm -rf * && mv /tmp_install install; \
      \
      mkdir -p /custom_action/src; \
      git clone --depth=1 https://github.com/smith-doug/bridge_mapping.git /custom_action/src/bridge_mapping; \
      cd /custom_action; \
      source /opt/ros/humble/setup.bash; \
      colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release; \
      mv install /tmp_install && rm -rf * && mv /tmp_install install; \
    fi && \
    # \
    # 3.3) Build ros1_bridge \
    source /opt/ros/humble/setup.bash && \
    if [[ "$ADD_ros_tutorials" = "1" ]]; then \
      source /ros_tutorials/install/setup.bash; \
      source /common_tutorials/install/setup.bash; \
      eatmydata apt-get install -y --no-install-recommends \
        ros-humble-example-interfaces \
        ros-humble-action-tutorials-interfaces \
        ros-humble-action-tutorials-cpp \
        ros-humble-action-tutorials-py; \
      source /opt/ros/humble/setup.bash; \
    fi && \
    if [[ "$ADD_custom_action_mapping" = "1" ]]; then \
      source /control_msgs_ros1/install/setup.bash; \
      source /control_msgs_ros2/install/setup.bash; \
      source /custom_action/install/setup.bash; \
    fi && \
    mkdir -p /ros-humble-ros1-bridge/src; \
    git clone -b action_bridge_humble --depth=1 https://github.com/smith-doug/ros1_bridge.git /ros-humble-ros1-bridge/src/ros1_bridge; \
    cd /ros-humble-ros1-bridge; \
    MEMG=$(printf "%.0f" $(free -g | awk '/^Mem:/{print $2}')); \
    NPROC=$(nproc); MIN=$((MEMG<NPROC ? MEMG : NPROC)); \
    [[ $MIN -lt 1 ]] && MIN=1; \
    echo "Running $MIN concurrent jobs to build ros1_bridge"; \
    time MAKEFLAGS="-j $MIN" colcon build --event-handlers console_direct+ --cmake-args -DCMAKE_BUILD_TYPE=Release && \
    mv install /tmp_install && rm -rf * && mv /tmp_install install; \
    # \
    # 3.4) Purge git and other build tools to clean image \
    apt-get purge -y --auto-remove git && \
    apt-get clean all && \
    rm -rf /var/lib/apt/lists/*

# Set standard workspace directory
WORKDIR /workspace

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh

# Run entrypoint script
ENTRYPOINT ["/entrypoint.sh"]
