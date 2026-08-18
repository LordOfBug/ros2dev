#!/bin/bash

# =============================================================================
# setup-autoware-env — prepare the acados dependency required by Autoware.
#
# This container is a BASE for Autoware development: the acados source is
# managed on the HOST and mounted into the container at /opt/acados. Call this
# script after the container spins up (or manually) so that:
#   1. acados is compiled and installed into its own source tree (/opt/acados)
#      if the binaries are not present yet.
#   2. The t_renderer code generator (required by acados solver code-gen used
#      inside Autoware's MPC / path optimizer) is downloaded.
#   3. The acados Python interface (acados_template) and casadi are installed.
#   4. The CUDA/acados environment variables are exported for the CURRENT shell
#      and persisted to /etc/profile.d/autoware.sh for all future shells.
#
# Usage (works both ways):
#   source setup-autoware-env    # exports apply to this shell
#   setup-autoware-env           # standalone; env vars persist via profile.d
#
# Mount layout (managed on HOST, mounted into container):
#   acados source : /opt/acados
# =============================================================================

ACADOS_DIR="/opt/acados"
T_RENDERER_VERSION="${T_RENDERER_VERSION:-0.2.1}"

echo "=== [Autoware Env Setup] Checking acados source & binaries ==="

# ---------------------------------------------------------------------------
# 1. Verify the acados source repository is mounted
# ---------------------------------------------------------------------------
if [ ! -f "$ACADOS_DIR/CMakeLists.txt" ]; then
    echo "----------------------------------------------------------------------"
    echo "  [ERROR] acados source repository not found at $ACADOS_DIR!"
    echo ""
    echo "  Please clone acados on your host and mount it into the container:"
    echo "    git clone https://github.com/acados/acados.git ./acados"
    echo "    cd ./acados && git submodule update --recursive --init"
    echo ""
    echo "  Docker run example:"
    echo "    docker run -v \$(pwd)/acados:/opt/acados ..."
    echo ""
    echo "  Docker Compose volume entry:"
    echo "    volumes:"
    echo "      - ./acados:/opt/acados"
    echo "----------------------------------------------------------------------"
    return 1 2>/dev/null || exit 1
fi

# ---------------------------------------------------------------------------
# 2. Build acados if the compiled libraries are missing
# ---------------------------------------------------------------------------
if [ ! -f "$ACADOS_DIR/lib/libacados.so" ] && [ ! -f "$ACADOS_DIR/lib/libacados.a" ]; then
    echo "acados source found at $ACADOS_DIR, but binaries are missing. Compiling inside container..."

    # Submodules are expected to be pre-synced on the HOST -- this container
    # never mutates the mounted sources. Just verify the key ones are present.
    # NOTE: acados submodules are all GitHub-hosted; GitHub removed the git://
    # protocol (Jan 2022), so clones must use https://.
    cd "$ACADOS_DIR"

    MISSING_SUBMODULES=""
    for SUBMODULE in "external/blasfeo/CMakeLists.txt" "external/hpipm/CMakeLists.txt"; do
        if [ ! -f "$ACADOS_DIR/$SUBMODULE" ]; then
            MISSING_SUBMODULES="$MISSING_SUBMODULES $SUBMODULE"
        fi
    done

    if [ -n "$MISSING_SUBMODULES" ]; then
        echo "----------------------------------------------------------------------"
        echo "  [WARNING] acados git submodules appear to be uninitialized:"
        for SUBMODULE in $MISSING_SUBMODULES; do
            echo "    - $SUBMODULE"
        done
        echo ""
        echo "  The mounted acados source is expected to be a FULL checkout that"
        echo "  already includes submodules. Initialize them on the HOST, e.g.:"
        echo "    cd <path-to-your-acados-checkout>"
        echo "    git submodule update --init --recursive --depth 1"
        echo "    # then restart the container / re-run setup-autoware-env"
        echo ""
        echo "  Continuing anyway -- the acados build will likely FAIL without them."
        echo "----------------------------------------------------------------------"
    fi

    # Build acados using the container toolchain. acados's default install
    # prefix is the source dir itself, which is exactly the layout Autoware
    # expects (lib/, include/, bin/ inside /opt/acados).
    mkdir -p build && cd build
    cmake -DACADOS_WITH_QPOASES=ON -DACADOS_WITH_HPIPM=ON -DBUILD_SHARED_LIBS=ON .. || {
        echo "[ERROR] acados CMake configuration failed. See output above."
        return 1 2>/dev/null || exit 1
    }
    make install -j"$(nproc)" || {
        echo "[ERROR] acados build failed. See output above."
        return 1 2>/dev/null || exit 1
    }

    echo "=== acados built successfully inside container! ==="
else
    echo "acados binaries verified at $ACADOS_DIR/lib."
fi

# ---------------------------------------------------------------------------
# 3. t_renderer — acados C-code generator used by Autoware's MPC / path
#    optimizer at runtime (solver code generation).
# ---------------------------------------------------------------------------
if [ ! -x "$ACADOS_DIR/bin/t_renderer" ]; then
    case "$(uname -m)" in
        x86_64)  T_RENDERER_ARCH="amd64" ;;
        aarch64) T_RENDERER_ARCH="arm64" ;;
        *)
            echo "  [WARN] No t_renderer binary available for $(uname -m); skipping."
            echo "         Autoware MPC code generation will fail at runtime."
            T_RENDERER_ARCH=""
            ;;
    esac

    if [ -n "$T_RENDERER_ARCH" ]; then
        mkdir -p "$ACADOS_DIR/bin"
        T_RENDERER_URL="https://github.com/acados/tera_renderer/releases/download/v${T_RENDERER_VERSION}/t_renderer-v${T_RENDERER_VERSION}-linux-${T_RENDERER_ARCH}"
        echo "Downloading t_renderer v${T_RENDERER_VERSION} (${T_RENDERER_ARCH})..."
        curl -fsSL -o "$ACADOS_DIR/bin/t_renderer" "$T_RENDERER_URL"
        chmod +x "$ACADOS_DIR/bin/t_renderer"
        echo "t_renderer installed at $ACADOS_DIR/bin/t_renderer"
    fi
else
    echo "t_renderer verified at $ACADOS_DIR/bin/t_renderer"
fi

# ---------------------------------------------------------------------------
# 4. acados Python interface + casadi (solver generation / training helpers)
# ---------------------------------------------------------------------------
# The mounted acados source is owned by the HOST user, so container root runs
# git with a different UID. Mark it as safe, otherwise setuptools_scm's git
# introspection (used by acados_template's setup.py) fails with
# "detected dubious ownership in repository".
git config --global --add safe.directory "$ACADOS_DIR" 2>/dev/null || true

if ! python3 -c "import casadi" 2>/dev/null; then
    pip3 install --quiet casadi || {
        echo "[ERROR] Failed to install casadi (needed by acados_template). See output above."
        return 1 2>/dev/null || exit 1
    }
fi

if ! python3 -c "import acados_template" 2>/dev/null; then
    pip3 install --quiet -e "$ACADOS_DIR/interfaces/acados_template" || {
        echo "[ERROR] Failed to install acados_template from $ACADOS_DIR/interfaces/acados_template."
        echo "        See output above."
        return 1 2>/dev/null || exit 1
    }
fi

# ---------------------------------------------------------------------------
# 5. Persist env vars for all future (login) shells
# ---------------------------------------------------------------------------
AUTOWARE_PROFILE_FILE="/etc/profile.d/autoware.sh"
if [ -d "/etc/profile.d" ] && [ -w "/etc/profile.d" ]; then
    cat > "$AUTOWARE_PROFILE_FILE" <<EOF
# Autoware / acados environment (generated by setup-autoware-env)
export CUDA_HOME=/usr/local/cuda
export ACADOS_SOURCE_DIR=$ACADOS_DIR
export CMAKE_PREFIX_PATH=$ACADOS_DIR\${CMAKE_PREFIX_PATH:+:\$CMAKE_PREFIX_PATH}
export PATH=/usr/local/cuda/bin\${PATH:+:\$PATH}
export LD_LIBRARY_PATH=$ACADOS_DIR/lib:/usr/local/cuda/lib64\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}
EOF
    echo "Environment variables persisted to $AUTOWARE_PROFILE_FILE"
fi

# ---------------------------------------------------------------------------
# 6. Export env vars for the current shell (in case this script is sourced)
# ---------------------------------------------------------------------------
export CUDA_HOME=/usr/local/cuda
export ACADOS_SOURCE_DIR="$ACADOS_DIR"
export CMAKE_PREFIX_PATH="$ACADOS_DIR${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}"
export PATH="/usr/local/cuda/bin${PATH:+:$PATH}"
export LD_LIBRARY_PATH="$ACADOS_DIR/lib:/usr/local/cuda/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

echo "=== [Autoware Env Setup] Environment successfully configured! ==="