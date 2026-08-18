#!/bin/bash

# =============================================================================
# setup-autoware-env — prepare the acados dependency required by Autoware.
#
# This container is a BASE for Autoware development: the acados source is
# managed on the HOST and mounted into the container at /opt/acados. Call this
# script after the container spins up (or manually) so that:
#   1. acados is compiled and installed into its own source tree (/opt/acados)
#      if the binaries are not present yet.
#   2. The acados version is verified against what Autoware expects
#      (v0.5.3) -- mismatches abort so autoware_path_optimizer cannot fail
#      late with a code-generator TypeError (acados >= 0.6 removed json_file).
#   3. The t_renderer code generator (required by acados solver code-gen used
#      inside Autoware's MPC / path optimizer) is downloaded.
#   4. The acados Python interface (acados_template) and casadi are installed
#      into /opt/acados/.venv (the interpreter autoware_path_optimizer uses).
#   5. The CUDA/acados environment variables are exported for the CURRENT shell
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
# Version of acados that Autoware's autoware_path_optimizer is compatible with.
# It calls AcadosOcpSolver.generate(ocp, json_file=...); acados >= 0.6.0 removed
# the json_file argument, so the build fails with a TypeError on newer acados.
EXPECTED_ACADOS_VERSION="${EXPECTED_ACADOS_VERSION:-v0.5.3}"

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
# 2. Verify the acados version matches what Autoware expects
# ---------------------------------------------------------------------------
# The mounted acados source is owned by the HOST user, so container root runs
# git with a different UID. Mark it safe BEFORE running any git command,
# otherwise git refuses with "detected dubious ownership in repository" and
# `git describe` fails (making the version look "unknown"). The same setting
# is also required later for setuptools_scm when installing acados_template.
git config --global --add safe.directory "$ACADOS_DIR" 2>/dev/null || true

ACADOS_VERSION="$(git -C "$ACADOS_DIR" describe --tags 2>/dev/null || true)"
ACADOS_VERSION="${ACADOS_VERSION:-unknown}"
case "$ACADOS_VERSION" in
    "$EXPECTED_ACADOS_VERSION"|"$EXPECTED_ACADOS_VERSION"-*)
        echo "acados version OK: $ACADOS_VERSION (Autoware expects $EXPECTED_ACADOS_VERSION)"
        ;;
    *)
        echo "----------------------------------------------------------------------"
        echo "  [ERROR] acados version mismatch!"
        echo ""
        echo "  Found   : $ACADOS_VERSION"
        echo "  Expected: $EXPECTED_ACADOS_VERSION"
        echo ""
        echo "  If 'Found' shows 'unknown', git could not read the mounted repo."
        echo "  This container runs as root but the mounted acados sources are owned"
        echo "  by the HOST user; a 'dubious ownership' refusal makes git describe"
        echo "  fail. The fix (also applied automatically by this script) is:"
        echo "    git config --global --add safe.directory /opt/acados"
        echo ""
        echo "  Autoware's autoware_path_optimizer calls the acados Python code"
        echo "  generator with the v0.5.x API (AcadosOcpSolver.generate(ocp, json_file=...))."
        echo "  acados >= v0.6.0 removed the json_file argument, so the Autoware build"
        echo "  fails with a TypeError. To reject mismatches early, this script aborts."
        echo ""
        echo "  Fix on the HOST (the container must NOT modify the mounted sources):"
        echo "    cd <path-to-your-acados-checkout>   # the dir mounted at $ACADOS_DIR"
        echo "    git fetch --tags --all"
        echo "    git checkout $EXPECTED_ACADOS_VERSION"
        echo "    git submodule update --init --recursive"
        echo "    # then restart the container or re-run setup-autoware-env"
        echo ""
        echo "  To accept a different version explicitly, set:"
        echo "    EXPECTED_ACADOS_VERSION=<your-version> setup-autoware-env"
        echo "  (only do this if you know the code generator is compatible!)"
        echo "----------------------------------------------------------------------"
        return 1 2>/dev/null || exit 1
        ;;
esac

# ---------------------------------------------------------------------------
# 3. Build acados if the compiled libraries are missing OR built from a
#    different source version.
# ---------------------------------------------------------------------------
# The libraries live inside the host-mounted source tree. If the HOST checkout
# was moved to another version (e.g. v0.6.0 -> v0.5.3), the old compiled
# libacados.so is stale and would be linked against by generated solver code
# -- an ABI mismatch that fails late with confusing errors. Track which
# version the binaries were built from in a stamp file and rebuild when the
# checked-out version differs.
ACADOS_VERSION_STAMP="$ACADOS_DIR/build/.setup-autoware-env.version"
NEED_BUILD=0
if [ ! -f "$ACADOS_DIR/lib/libacados.so" ] && [ ! -f "$ACADOS_DIR/lib/libacados.a" ]; then
    NEED_BUILD=1
elif [ ! -f "$ACADOS_VERSION_STAMP" ]; then
    # Binaries exist but were never stamped (built by an older version of this
    # script, e.g. before the v0.6.0->v0.5.3 version gate was added). We cannot
    # know which version they came from, so rebuild once to be safe.
    echo "acados binaries exist but no version stamp found (pre-version-gate build)."
    echo "Removing them and rebuilding from $ACADOS_VERSION..."
    rm -rf "$ACADOS_DIR/lib" "$ACADOS_DIR/build"
    NEED_BUILD=1
elif [ "$(cat "$ACADOS_VERSION_STAMP")" != "$ACADOS_VERSION" ]; then
    echo "acados binaries were built from $(cat "$ACADOS_VERSION_STAMP"), but the source is now $ACADOS_VERSION."
    echo "Removing stale binaries and rebuilding..."
    rm -rf "$ACADOS_DIR/lib" "$ACADOS_DIR/build"
    NEED_BUILD=1
fi

if [ "$NEED_BUILD" -eq 1 ]; then
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

    # Record which source version these binaries were built from.
    mkdir -p "$ACADOS_DIR/build"
    echo "$ACADOS_VERSION" > "$ACADOS_VERSION_STAMP"

    echo "=== acados built successfully inside container! ==="
else
    echo "acados binaries verified at $ACADOS_DIR/lib."
fi

# ---------------------------------------------------------------------------
# 4. t_renderer — acados C-code generator used by Autoware's MPC / path
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
# 5. acados Python interface + casadi (solver generation / training helpers)
# ---------------------------------------------------------------------------
# Autoware's autoware_path_optimizer invokes the acados code generator via
# ${ACADOS_SOURCE_DIR}/.venv/bin/python3 (hardcoded in its CMakeLists), so the
# Python packages MUST be installed into /opt/acados/.venv -- installing into
# the system python alone is NOT sufficient. The official Autoware ansible
# role creates exactly this venv (see ansible/roles/acados/tasks/main.yaml).
# The mounted acados source is owned by the HOST user, so container root runs
# git with a different UID. Mark it as safe, otherwise setuptools_scm's git
# introspection (used by acados_template's setup.py) fails with
# "detected dubious ownership in repository".
git config --global --add safe.directory "$ACADOS_DIR" 2>/dev/null || true

ACADOS_VENV="$ACADOS_DIR/.venv"

# Create the venv if it does not exist yet.
if [ ! -x "$ACADOS_VENV/bin/python3" ]; then
    echo "Creating acados venv at $ACADOS_VENV ..."
    python3 -m venv "$ACADOS_VENV" || {
        echo "[ERROR] Failed to create $ACADOS_VENV. The image needs python3-venv:"
        echo "        apt-get install -y python3-venv"
        return 1 2>/dev/null || exit 1
    }
fi

# Install into the venv (this is what autoware_path_optimizer actually uses).
"$ACADOS_VENV/bin/pip" install --quiet --upgrade pip
if ! "$ACADOS_VENV/bin/python" -c "import casadi, sympy" 2>/dev/null; then
    "$ACADOS_VENV/bin/pip" install --quiet casadi sympy || {
        echo "[ERROR] Failed to install casadi/sympy into $ACADOS_VENV. See output above."
        return 1 2>/dev/null || exit 1
    }
fi
if ! "$ACADOS_VENV/bin/python" -c "import acados_template" 2>/dev/null; then
    "$ACADOS_VENV/bin/pip" install --quiet -e "$ACADOS_DIR/interfaces/acados_template" || {
        echo "[ERROR] Failed to install acados_template (editable) into $ACADOS_VENV."
        echo "        See output above."
        return 1 2>/dev/null || exit 1
    }
fi
echo "acados venv verified at $ACADOS_VENV (casadi + acados_template)"

# Also make the packages available to the system python (convenience for
# interactive shells; not required by the Autoware build itself).
if ! python3 -c "import casadi" 2>/dev/null; then
    pip3 install --quiet casadi || {
        echo "[WARN] Failed to install casadi into system python (non-fatal)."
    }
fi

if ! python3 -c "import acados_template" 2>/dev/null; then
    pip3 install --quiet -e "$ACADOS_DIR/interfaces/acados_template" || {
        echo "[WARN] Failed to install acados_template into system python (non-fatal)."
    }
fi

# ---------------------------------------------------------------------------
# 6. Persist env vars for all future (login) shells
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
# 7. Export env vars for the current shell (in case this script is sourced)
# ---------------------------------------------------------------------------
export CUDA_HOME=/usr/local/cuda
export ACADOS_SOURCE_DIR="$ACADOS_DIR"
export CMAKE_PREFIX_PATH="$ACADOS_DIR${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}"
export PATH="/usr/local/cuda/bin${PATH:+:$PATH}"
export LD_LIBRARY_PATH="$ACADOS_DIR/lib:/usr/local/cuda/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

echo "=== [Autoware Env Setup] Environment successfully configured! ==="