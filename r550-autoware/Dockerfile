# syntax=docker/dockerfile:1
# ============================================================================
# r550-autoware: extends humble-ros1-bridge with a relay node for Autoware
#
# The bridge provides: ros1_bridge, bridge_mapping, control_msgs, overlays.
# This image adds: relay_node (sensor/control topic bridge to remote Autoware).
#
# Prerequisites: r550-ros1-bridge:latest must be built first.
#
# Build: ./release.sh  OR  docker buildx build --platform linux/arm64 -t r550-autoware:latest .
# ============================================================================

# =========================================================================
# STAGE 1: Builder — build the relay node using the bridge image
# =========================================================================
FROM r550-ros1-bridge:latest AS builder

WORKDIR /workspace

COPY relay_node/ /workspace/src/relay_node

RUN source /opt/ros/humble/setup.bash && \
    colcon build --packages-select r550_autoware_relay

# =========================================================================
# STAGE 2: Runner — clean bridge image + compiled relay node
# =========================================================================
FROM r550-ros1-bridge:latest

# Copy compiled relay node from builder
COPY --from=builder /workspace/install /workspace/install

# Override entrypoint to also launch the relay node
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
