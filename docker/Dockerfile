FROM osrf/ros:humble-desktop

ENV DEBIAN_FRONTEND=noninteractive

# 1. Install XFCE desktop environment and XRDP
RUN apt-get update

RUN apt-get install -y \
    xfce4 \
    xfce4-goodies \
    xrdp \
    xorgxrdp \    
    dbus-x11 

RUN rm -rf /var/lib/apt/lists/*

# 2. Fix the SSL certificate permission error
RUN adduser xrdp ssl-cert

# 3. Create a bulletproof startup script for XFCE that includes dbus-launch
RUN echo "#!/bin/sh" > /etc/xrdp/startwm.sh \
    && echo "export XDG_SESSION_DESKTOP=xfce" >> /etc/xrdp/startwm.sh \
    && echo "export XDG_SESSION_TYPE=x11" >> /etc/xrdp/startwm.sh \
    && echo "export XDG_CURRENT_DESKTOP=XFCE" >> /etc/xrdp/startwm.sh \
    && echo "exec dbus-launch --exit-with-session startxfce4" >> /etc/xrdp/startwm.sh \
    && chmod +x /etc/xrdp/startwm.sh

# 4. Set the root password (you can change 'ros2dev' to anything)
RUN echo 'root:ros2dev' | chpasswd

# 5. Expose the default RDP port
EXPOSE 3389

# 6. Start the XRDP service and keep the container alive
CMD ["/bin/bash", "-c", "mkdir -p /var/run/dbus && dbus-daemon --system && service xrdp start && tail -f /var/log/xrdp.log"]
