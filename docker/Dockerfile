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
    build-essential \
    ros-humble-xacro \
    ros-humble-joint-state-publisher-gui \
    ros-humble-foxglove-bridge

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
RUN apt-get install -y --no-install-recommends mesa-utils \
    && apt-get install -y /tmp/virtualgl.deb 

RUN rm -rf /var/lib/apt/lists/* /tmp/virtualgl.deb

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

# 6. Initialize rosdep (Crucial for resolving future package dependencies)
# RUN rosdep init || true \
#     && rosdep update

# 7. Expose the default RDP port, 8765 for Foxglove
EXPOSE 3389
EXPOSE 8765

# 8. Start the XRDP service and keep the container alive
CMD ["/bin/bash", "-c", "mkdir -p /var/run/dbus && dbus-daemon --system && service xrdp start && tail -f /var/log/xrdp.log"]
