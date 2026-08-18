FROM osrf/ros:humble-desktop

ENV DEBIAN_FRONTEND=noninteractive

# 1. Install Essential Developer Tools & Python Pip
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-colcon-common-extensions \
    python-is-python3 \
    git \
    wget \
    curl \
    nano \
    vim \
    emacs \
    build-essential \
    ccache \
    ros-humble-xacro \
    ros-humble-foxglove-bridge \
    ros-humble-robot-state-publisher \
    ros-humble-joint-state-publisher \
    ros-humble-joint-state-publisher-gui \
    ros-humble-gazebo-ros-pkgs \
    ros-humble-gazebo-plugins \
    ros-humble-teleop-twist-keyboard \
    ros-humble-teleop-twist-joy \
    ros-humble-joy \
    ros-humble-ros2-control \
    ros-humble-ros2-controllers \
    ros-humble-gazebo-ros2-control \
    ros-humble-ackermann-msgs \
    ros-humble-navigation2 \
    ros-humble-nav2-bringup \
    ros-humble-slam-toolbox \
    ros-humble-sensor-msgs

# 1.1 Install OpenCode Desktop (Linux version)
RUN curl -fsSL -o /tmp/opencode.deb https://opencode.ai/download/stable/linux-x64-deb \
    && apt-get update \
    && apt-get install -y /tmp/opencode.deb \
    && rm /tmp/opencode.deb

# 2. Install XFCE desktop environment and XRDP
RUN apt-get install -y \
    xfce4 \
    xfce4-goodies \
    xrdp \
    xorgxrdp \
    dbus-x11 

# 1. Copy the pre-downloaded deb file from your host folder into the container's /tmp
COPY virtualgl.deb /tmp/virtualgl.deb

# 2. Update package lists, install mesa-utils, install the local VirtualGL package, and clean up layers
RUN apt-get install -y --no-install-recommends mesa-utils python3-rosdep \
    && apt-get install -y /tmp/virtualgl.deb 

# Let's keep the apt package list and in DEV env we may need to install extra package with rosdep
# RUN rm -rf /var/lib/apt/lists/*
RUN rm -f /tmp/virtualgl.deb

########################################################################
# CUDA support  etc.
RUN wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb && \
    dpkg -i cuda-keyring_1.1-1_all.deb && \
    rm cuda-keyring_1.1-1_all.deb

RUN apt-get update && apt-get install -y cuda-toolkit-12-3 libnvinfer-dev libnvinfer-plugin-dev

# of of CUDA stuff
########################################################################

# Initialize rosdep (Crucial for resolving future package dependencies)
RUN rosdep init || true && rosdep update

########################################################################
# Autoware DEV Env: external init script for autoware if user try to do autoware DEV

# Copy environment setup script into bin
COPY setup-autoware-env.sh /usr/local/bin/setup-autoware-env
RUN chmod +x /usr/local/bin/setup-autoware-env

# Copy autoware build script
COPY build-autoware.sh /usr/local/bin/build-autoware
RUN chmod +x /usr/local/bin/build-autoware

# End Autoware DEV
########################################################################

# 3. Fix the SSL certificate permission error
RUN adduser xrdp ssl-cert

# 4. Create a bulletproof startup script for XFCE that includes dbus-launch
RUN echo "#!/bin/sh" > /etc/xrdp/startwm.sh \
    && echo "export XDG_SESSION_DESKTOP=xfce" >> /etc/xrdp/startwm.sh \
    && echo "export XDG_SESSION_TYPE=x11" >> /etc/xrdp/startwm.sh \
    && echo "export XDG_CURRENT_DESKTOP=XFCE" >> /etc/xrdp/startwm.sh \
    && echo "exec dbus-launch --exit-with-session startxfce4" >> /etc/xrdp/startwm.sh \
    && chmod +x /etc/xrdp/startwm.sh

# 5. Set the root password
RUN echo 'root:ros2dev' | chpasswd

# 7. Expose the default RDP port, 8765 for Foxglove
EXPOSE 3389
EXPOSE 8765

# Fix the 1003 group error as our /dev/dri/* use vlgusers with group 1003
RUN groupadd -g 1003 vglusers || true

# 8. Start the XRDP service and keep the container alive
CMD ["/bin/bash", "-c", "mkdir -p /var/run/dbus && dbus-daemon --system && service xrdp start && tail -f /var/log/xrdp.log"]
