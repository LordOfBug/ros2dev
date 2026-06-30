# syntax=docker/dockerfile:1
# Use the official multi-platform ROS 2 Humble base image (fully QEMU-compatible)
FROM ros:humble-ros-base-jammy

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
    apt-get update && \
    eatmydata apt-get install -y --no-install-recommends \
    python3-colcon-common-extensions \
    ros-humble-nav2-msgs \
    lld && \
    rm -f /usr/bin/ld /usr/bin/aarch64-linux-gnu-ld && \
    ln -s /usr/bin/ld.lld /usr/bin/ld && \
    ln -s /usr/bin/ld.lld /usr/bin/aarch64-linux-gnu-ld

# Copy local source tarball assets (must run ./download_assets.sh on host first)
COPY assets/ /assets/

# =========================================================================
# LAYER 3: Build custom overlays and ros1_bridge
# Unpack, compile, and clean up build-time artifacts to keep the image small.
# =========================================================================
ARG ADD_ros_tutorials=1
ARG ADD_custom_action_mapping=1

# Use bash for shell commands to enable sourcing setup files
SHELL ["/bin/bash", "-o", "pipefail", "-o", "errexit", "-c"]

RUN if [[ "$ADD_ros_tutorials" = "1" ]]; then \
      mkdir -p /ros_tutorials && tar -xzf /assets/ros_tutorials.tar.gz -C /ros_tutorials --strip-components=1 && rm -rf /ros_tutorials/turtlesim; \
      cd /ros_tutorials; \
      unset ROS_DISTRO; \
      ulimit -s unlimited || true; \
      MEMG=$(free -g 2>/dev/null | awk '/^Mem:/{print $2}'); \
      [[ -z "$MEMG" || "$MEMG" -eq 0 ]] && MEMG=8; \
      NPROC=$(nproc 2>/dev/null || echo 4); \
      JOBS=$((MEMG / 2)); \
      [[ $JOBS -lt 1 ]] && JOBS=1; \
      MIN=$((JOBS < NPROC ? JOBS : NPROC)); \
      [[ $MIN -gt 4 ]] && MIN=4; \
      echo "System Info: Host RAM: ${MEMG}G | CPU Cores: ${NPROC} | Selected Jobs: ${MIN}"; \
      MAKEFLAGS="-j $MIN" colcon build --executor sequential --parallel-workers 1 --cmake-args -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=MinSizeRel -DCMAKE_NO_SYSTEM_FROM_IMPORTED=ON -DCMAKE_SHARED_LINKER_FLAGS="-fuse-ld=lld" -DCMAKE_EXE_LINKER_FLAGS="-fuse-ld=lld" -DCMAKE_MODULE_LINKER_FLAGS="-fuse-ld=lld" || exit 1; \
      if [[ "$PWD" = "/ros_tutorials" ]]; then mv install /tmp_install && rm -rf * && mv /tmp_install install; fi; \
    fi

RUN if [[ "$ADD_ros_tutorials" = "1" ]]; then \
      source /ros_tutorials/install/setup.bash; \
      mkdir -p /common_tutorials && tar -xzf /assets/common_tutorials.tar.gz -C /common_tutorials --strip-components=1; \
      cd /common_tutorials; \
      unset ROS_DISTRO; \
      ulimit -s unlimited || true; \
      MEMG=$(free -g 2>/dev/null | awk '/^Mem:/{print $2}'); \
      [[ -z "$MEMG" || "$MEMG" -eq 0 ]] && MEMG=8; \
      NPROC=$(nproc 2>/dev/null || echo 4); \
      JOBS=$((MEMG / 2)); \
      [[ $JOBS -lt 1 ]] && JOBS=1; \
      MIN=$((JOBS < NPROC ? JOBS : NPROC)); \
      [[ $MIN -gt 4 ]] && MIN=4; \
      echo "System Info: Host RAM: ${MEMG}G | CPU Cores: ${NPROC} | Selected Jobs: ${MIN}"; \
      MAKEFLAGS="-j $MIN" colcon build --executor sequential --parallel-workers 1 --cmake-args -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=MinSizeRel -DCMAKE_NO_SYSTEM_FROM_IMPORTED=ON -DCMAKE_SHARED_LINKER_FLAGS="-fuse-ld=lld" -DCMAKE_EXE_LINKER_FLAGS="-fuse-ld=lld" -DCMAKE_MODULE_LINKER_FLAGS="-fuse-ld=lld" || exit 1; \
      if [[ "$PWD" = "/common_tutorials" ]]; then mv install /tmp_install && rm -rf * && mv /tmp_install install; fi; \
    fi

RUN if [[ "$ADD_custom_action_mapping" = "1" ]]; then \
      mkdir -p /control_msgs_ros1 && tar -xzf /assets/control_msgs_ros1.tar.gz -C /control_msgs_ros1 --strip-components=1; \
      cd /control_msgs_ros1; \
      unset ROS_DISTRO; \
      ulimit -s unlimited || true; \
      MEMG=$(free -g 2>/dev/null | awk '/^Mem:/{print $2}'); \
      [[ -z "$MEMG" || "$MEMG" -eq 0 ]] && MEMG=8; \
      NPROC=$(nproc 2>/dev/null || echo 4); \
      JOBS=$((MEMG / 2)); \
      [[ $JOBS -lt 1 ]] && JOBS=1; \
      MIN=$((JOBS < NPROC ? JOBS : NPROC)); \
      [[ $MIN -gt 4 ]] && MIN=4; \
      echo "System Info: Host RAM: ${MEMG}G | CPU Cores: ${NPROC} | Selected Jobs: ${MIN}"; \
      MAKEFLAGS="-j $MIN" colcon build --executor sequential --parallel-workers 1 --cmake-args -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=MinSizeRel -DCMAKE_NO_SYSTEM_FROM_IMPORTED=ON -DCMAKE_SHARED_LINKER_FLAGS="-fuse-ld=lld" -DCMAKE_EXE_LINKER_FLAGS="-fuse-ld=lld" -DCMAKE_MODULE_LINKER_FLAGS="-fuse-ld=lld" || exit 1; \
      if [[ "$PWD" = "/control_msgs_ros1" ]]; then mv install /tmp_install && rm -rf * && mv /tmp_install install; fi; \
    fi

RUN if [[ "$ADD_custom_action_mapping" = "1" ]]; then \
      mkdir -p /control_msgs_ros2 && tar -xzf /assets/control_msgs_ros2.tar.gz -C /control_msgs_ros2 --strip-components=1; \
      cd /control_msgs_ros2; \
      source /opt/ros/humble/setup.bash; \
      ulimit -s unlimited || true; \
      MEMG=$(free -g 2>/dev/null | awk '/^Mem:/{print $2}'); \
      [[ -z "$MEMG" || "$MEMG" -eq 0 ]] && MEMG=8; \
      NPROC=$(nproc 2>/dev/null || echo 4); \
      JOBS=$((MEMG / 2)); \
      [[ $JOBS -lt 1 ]] && JOBS=1; \
      MIN=$((JOBS < NPROC ? JOBS : NPROC)); \
      [[ $MIN -gt 4 ]] && MIN=4; \
      echo "System Info: Host RAM: ${MEMG}G | CPU Cores: ${NPROC} | Selected Jobs: ${MIN}"; \
      MAKEFLAGS="-j $MIN" colcon build --executor sequential --parallel-workers 1 --cmake-args -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=MinSizeRel -DCMAKE_NO_SYSTEM_FROM_IMPORTED=ON -DCMAKE_SHARED_LINKER_FLAGS="-fuse-ld=lld" -DCMAKE_EXE_LINKER_FLAGS="-fuse-ld=lld" -DCMAKE_MODULE_LINKER_FLAGS="-fuse-ld=lld" || exit 1; \
      if [[ "$PWD" = "/control_msgs_ros2" ]]; then mv install /tmp_install && rm -rf * && mv /tmp_install install; fi; \
    fi

RUN if [[ "$ADD_custom_action_mapping" = "1" ]]; then \
      source /opt/ros/humble/setup.bash; \
      source /control_msgs_ros2/install/setup.bash; \
      mkdir -p /custom_action/src/bridge_mapping; \
      tar -xzf /assets/bridge_mapping.tar.gz -C /custom_action/src/bridge_mapping --strip-components=1; \
      cd /custom_action; \
      ulimit -s unlimited || true; \
      MEMG=$(free -g 2>/dev/null | awk '/^Mem:/{print $2}'); \
      [[ -z "$MEMG" || "$MEMG" -eq 0 ]] && MEMG=8; \
      NPROC=$(nproc 2>/dev/null || echo 4); \
      JOBS=$((MEMG / 2)); \
      [[ $JOBS -lt 1 ]] && JOBS=1; \
      MIN=$((JOBS < NPROC ? JOBS : NPROC)); \
      [[ $MIN -gt 4 ]] && MIN=4; \
      echo "System Info: Host RAM: ${MEMG}G | CPU Cores: ${NPROC} | Selected Jobs: ${MIN}"; \
      MAKEFLAGS="-j $MIN" colcon build --executor sequential --parallel-workers 1 --cmake-args -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=MinSizeRel -DCMAKE_NO_SYSTEM_FROM_IMPORTED=ON -DCMAKE_SHARED_LINKER_FLAGS="-fuse-ld=lld" -DCMAKE_EXE_LINKER_FLAGS="-fuse-ld=lld" -DCMAKE_MODULE_LINKER_FLAGS="-fuse-ld=lld" || exit 1; \
      if [[ "$PWD" = "/custom_action" ]]; then mv install /tmp_install && rm -rf * && mv /tmp_install install; fi; \
    fi

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    if [[ "$ADD_ros_tutorials" = "1" ]]; then \
      apt-get update && \
      eatmydata apt-get install -y --no-install-recommends \
        ros-humble-example-interfaces \
        ros-humble-action-tutorials-interfaces \
        ros-humble-action-tutorials-cpp \
        ros-humble-action-tutorials-py; \
    fi

RUN source /opt/ros/humble/setup.bash; \
    if [[ "$ADD_ros_tutorials" = "1" ]]; then \
      source /ros_tutorials/install/setup.bash; \
      source /common_tutorials/install/setup.bash; \
    fi; \
    if [[ "$ADD_custom_action_mapping" = "1" ]]; then \
      source /control_msgs_ros1/install/setup.bash; \
      source /control_msgs_ros2/install/setup.bash; \
      source /custom_action/install/setup.bash; \
    fi; \
    mkdir -p /ros-humble-ros1-bridge/src/ros1_bridge; \
    tar -xzf /assets/ros1_bridge.tar.gz -C /ros-humble-ros1-bridge/src/ros1_bridge --strip-components=1; \
    cd /ros-humble-ros1-bridge; \
    ulimit -s unlimited || true; \
    MEMG=$(free -g 2>/dev/null | awk '/^Mem:/{print $2}'); \
    [[ -z "$MEMG" || "$MEMG" -eq 0 ]] && MEMG=8; \
    NPROC=$(nproc 2>/dev/null || echo 4); \
    JOBS=$((MEMG / 2)); \
    [[ $JOBS -lt 1 ]] && JOBS=1; \
    MIN=$((JOBS < NPROC ? JOBS : NPROC)); \
    [[ $MIN -gt 4 ]] && MIN=4; \
    echo "System Info: Host RAM: ${MEMG}G | CPU Cores: ${NPROC} | Selected Jobs: ${MIN}"; \
    time MAKEFLAGS="-j $MIN" colcon build --executor sequential --parallel-workers 1 --event-handlers console_direct+ --cmake-args -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=MinSizeRel -DCMAKE_NO_SYSTEM_FROM_IMPORTED=ON -DCMAKE_SHARED_LINKER_FLAGS="-fuse-ld=lld" -DCMAKE_EXE_LINKER_FLAGS="-fuse-ld=lld" -DCMAKE_MODULE_LINKER_FLAGS="-fuse-ld=lld" || exit 1; \
    if [[ "$PWD" = "/ros-humble-ros1-bridge" ]]; then mv install /tmp_install && rm -rf * && mv /tmp_install install; fi

RUN rm -rf /assets

# Set standard workspace directory
WORKDIR /workspace

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh

# Run entrypoint script
ENTRYPOINT ["/entrypoint.sh"]
