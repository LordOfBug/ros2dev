#!/bin/bash

# =============================================================================
# build-autoware — build the Autoware source workspace mounted into this container.
#
# This container is a BASE image: the Autoware sources are managed on the HOST
# (git + vcs import) and mounted in. This script performs the in-container
# build steps from the official Autoware source-installation docs:
#   1. source ROS 2
#   2. setup-autoware-env  -> ensures acados is built + env vars exported
#   3. rosdep install      -> installs all ROS package dependencies
#   4. colcon build        -> Release + symlink-install
#
# Usage:
#   build-autoware [workspace-path] [extra colcon args...]
#
#   workspace-path   Autoware workspace root containing src/  (default: /opt/autoware)
#   extra args       appended to the colcon build command, e.g.
#                    build-autoware /opt/autoware --packages-up-to autoware_launch
#
# Env overrides:
#   ROS_DISTRO  (default: humble)
# =============================================================================

set -euo pipefail

ROS_DISTRO="${ROS_DISTRO:-humble}"

AUTOWARE_WS="${1:-/opt/autoware}"
if [ "$#" -gt 0 ]; then
    shift
fi

# ---------------------------------------------------------------------------
# 1. ROS 2 environment
# ---------------------------------------------------------------------------
# ROS 2 setup scripts (and setup-autoware-env) reference possibly-unset vars
# such as AMENT_TRACE_SETUP_FILES / CMAKE_PREFIX_PATH and are NOT safe under
# set -u. Disable nounset while sourcing, then restore it.
set +u
source "/opt/ros/$ROS_DISTRO/setup.bash"
set -u
echo "==> ROS 2 distro: $ROS_DISTRO"

# ---------------------------------------------------------------------------
# 2. Ensure acados is built and env vars are exported.
#    Sourced (not executed) so the exported vars apply to this build shell.
# ---------------------------------------------------------------------------
set +u
source /usr/local/bin/setup-autoware-env
set -u

# ---------------------------------------------------------------------------
# 3. Workspace sanity check
# ---------------------------------------------------------------------------
if [ ! -d "$AUTOWARE_WS/src" ]; then
    echo "[ERROR] Autoware workspace not found at $AUTOWARE_WS (no src/ directory)."
    echo "        Make sure the host-synced Autoware sources are mounted there, e.g.:"
    echo "          docker run -v /path/to/autoware:$AUTOWARE_WS ..."
    exit 1
fi
cd "$AUTOWARE_WS"
echo "==> Building Autoware workspace at: $AUTOWARE_WS"

# ---------------------------------------------------------------------------
# 4. Install ROS dependencies (rosdep)
# ---------------------------------------------------------------------------
rosdep update
rosdep install -y --from-paths src --ignore-src --rosdistro "$ROS_DISTRO"

# ---------------------------------------------------------------------------
# 5. Build (Release, symlink-install; mirrors official Autoware docs)
# ---------------------------------------------------------------------------
echo "==> colcon build (this may take a long time)..."
set +e
colcon build \
    --symlink-install \
    --continue-on-error \
    --cmake-args -DCMAKE_BUILD_TYPE=Release \
    "$@"
BUILD_STATUS=$?
set -e

if [ "$BUILD_STATUS" -ne 0 ]; then
    echo "==> [WARN] colcon build finished with errors (status $BUILD_STATUS). Inspect the log above."
    exit "$BUILD_STATUS"
fi

echo "==> Autoware build succeeded! Source the workspace with:"
echo "    source $AUTOWARE_WS/install/setup.bash"