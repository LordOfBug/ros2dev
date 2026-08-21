# syntax=docker/dockerfile:1
# ============================================================================
# r550-autoware: extends humble-ros1-bridge with a relay node for Autoware
#
# Adds the relay_node package on top of the existing bridge image.
# The bridge provides: ros1_bridge, bridge_mapping, control_msgs, overlays.
# This image adds: relay_node (sensor/control topic bridge to remote Autoware).
#
# Prerequisites: r550-ros1-bridge:latest must be built first.
#
# Build: ./release.sh  OR  docker buildx build --platform linux/arm64 -t r550-autoware:latest .
# ============================================================================
FROM r550-ros1-bridge:latest

# Install pip for relay_node installation
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends python3-pip

# Install relay node (pure Python, no C++ compilation needed)
COPY relay_node/ /relay_node/
RUN pip install --no-cache-dir /relay_node && rm -rf /relay_node

# Override entrypoint to also launch the relay node
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
