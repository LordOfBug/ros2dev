# Autoware Development Environment (ROS 2 Humble)

This document describes the **recommended Autoware development setup** built around the
`ros2dev` Docker image (see `../docker/Dockerfile`). It explains the overall
architecture, how to build/run the environment, and the day-to-day DEV & test workflow.

---

## Recommended Environment Layout

We deliberately split the workload between the host and the container so each side stays
simple and focused:

| Component | Where it runs | Purpose |
|---|---|---|
| Ubuntu **host server** | host | Headless simulation (Gazebo), RViz2/visualization, GPU + NVIDIA driver |
| `ros2dev` **Docker container** | container | Autoware DEV, compilation, debugging & testing against the host sim |
| **Autoware sources** | host (git) | Managed with git/vcs on the host; mounted read-write into the container |
| **acados sources** | host (git) | Pinned to `v0.5.3`; mounted into the container (binaries built in-container) |

**Why build inside the container?** The container is a reproducible toolchain (ROS 2 Humble,
CUDA 12.9, TensorRT, compiler). Binary artifacts must match *this* toolchain — not whatever
happens to be installed on the host — so the container compiles while the host only holds the
source code.

```
+--------------------------------------------------------------------------------------+
| UBUNTU HOST SERVER                                                                   |
|   NVIDIA Driver  |  Gazebo / RViz2  |  git-managed sources                           |
|         |                |                 |                                         |
|         | GPU pass (--gpus) | ROS2 topics / shared network & IPC                     |
|         v                v                 v                                         |
|  +-----------------------------------------------------------------------------+     |
|  | DOCKER CONTAINER  ros2dev  (network=host, ipc=host, --gpus all)             |     |
|  |                                                                             |     |
|  |  /opt/autoware  <- bind mount of host Autoware sources (build/install/log   |     |
|  |                  kept in anonymous volumes, NOT in the source tree)         |     |
|  |  /opt/acados    <- bind mount of host acados checkout (v0.5.3)              |     |
|  |                                                                             |     |
|  |  CUDA 12.9 + TensorRT | ROS 2 Humble | colcon / ccache | build-autoware     |     |
|  +-----------------------------------------------------------------------------+     |
+--------------------------------------------------------------------------------------+
```

---

## Host Prerequisites

1. **NVIDIA driver** installed natively on the host:

   ```bash
   nvidia-smi          # verify the driver works
   ```

2. **Docker** with the **NVIDIA Container Toolkit** (lets containers use the GPU):

   ```bash
   sudo apt-get update
   sudo apt-get install -y nvidia-container-toolkit
   sudo systemctl restart docker
   ```

3. **X11 socket** shared with the container so RViz2/other GUI tools can display
   (see the run examples below). For a headless host, run the GUI tools on the host and
   keep only the computational nodes in the container.

---

## Build the Image

The image already contains ROS 2 Humble (desktop), CUDA 12.9, TensorRT (built for CUDA 12.x),
XFCE + RDP (port `3389`), Foxglove bridge (port `8765`), `ccache`, and the Autoware helper
scripts. Rebuild it from the repo root:

```bash
cd docker
./build.sh          # docker build -f Dockerfile . -t ros2dev:latest
```

Or manually:

```bash
docker build -f docker/Dockerfile . -t ros2dev:latest
```

---

## Prepare the Sources on the Host

The sources live **only on the host**. The container never modifies them (its own helper
scripts only patch *installed* system files, never `/opt/autoware` or `/opt/acados`).

### 1. Autoware

```bash
cd ~/work
git clone https://github.com/autowarefoundation/autoware.git ./autoware
cd autoware && git submodule update --init --recursive
```

### 2. acados (pinned to v0.5.3)

Autoware's `autoware_path_optimizer` requires the **v0.5.3** acados API. The `setup-autoware-env`
helper checks the mounted checkout and **aborts the build** if the version does not match, so
make sure you follow these steps exactly:

```bash
cd ~/work
git clone https://github.com/acados/acados.git ./acados
cd acados
git fetch --tags --all
git checkout v0.5.3
git submodule update --init --recursive
```

> If your acados checkout is already in a broken/inconsistent state (dirty source, mismatched
> submodules, half-finished rebase, etc.), see [Disaster Recovery](#disaster-recovery-acados)
> below instead of forcing a reset here.

---

## Disaster Recovery: acados

If your acados checkout has drifted into a broken state (compiled binaries from a different
version, dirty tracked files, uninitialized/mismatched submodules), do **not** try to patch it
in place. Force-reset everything back to a clean `v0.5.3` checkout:

```bash
cd ~/work/acados

# 1. discard any local modifications to tracked files
git reset --hard HEAD

# 2. switch to the required tag
git checkout v0.5.3

# 3. force-reset + clean every submodule to its pinned state
git submodule foreach --recursive 'git reset --hard HEAD && git clean -fdx'
git submodule update --init --recursive
```

> [!WARNING]
> The `reset --hard` / `clean -fdx` commands **discard all local changes** in the checkout
> (tracked files and untracked build artifacts). This is intentional — it restores a pristine
> `v0.5.3` tree. Note that `/opt/acados/.venv`, `build/`, `lib/` etc. live inside this checkout;
> `setup-autoware-env` will re-create/re-provision them on the next run.

After the reset, either restart the container or re-run the setup helpers:

```bash
docker exec -it ros2dev bash
setup-autoware-env       # rebuilds acados + venv from the clean checkout
build-autoware           # full build
```

---

## Run the DEV Container

### Option A: `docker run`

```bash
docker run -d \
  --name ros2dev \
  --gpus all \
  --network host \
  --ipc host \
  --pid host \
  --privileged \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -v /etc/localtime:/etc/localtime:ro \
  -v ~/work/autoware:/opt/autoware \
  -v ~/work/acados:/opt/acados \
  -v /opt/autoware/build \
  -v /opt/autoware/install \
  -v /opt/autoware/log \
  ros2dev:latest
```

> [!IMPORTANT]
> `build/`, `install/` and `log/` inside `/opt/autoware` are mounted as **anonymous volumes**.
> This keeps all compilation artifacts out of the host source tree (so `git status` on the host
> stays clean), while persisting them across container restarts.

### Option B: `docker compose`

```yaml
# docker-compose.yaml
services:
  ros2dev:
    image: ros2dev:latest
    container_name: ros2dev
    network_mode: host
    ipc: host
    pid: host
    privileged: true
    tty: true
    stdin_open: true
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics
    volumes:
      - ~/work/autoware:/opt/autoware
      - ~/work/acados:/opt/acados
      - /opt/autoware/build
      - /opt/autoware/install
      - /opt/autoware/log
      - /tmp/.X11-unix:/tmp/.X11-unix:rw
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

---

## First-Time Setup Inside the Container

Everything is automated through two helpers installed in the image:

- **`setup-autoware-env`** — verifies the acados version, builds acados if the binaries are
  missing/stale, downloads `t_renderer`, provisions the `/opt/acados/.venv` Python environment,
  and exports the CUDA/acados env vars.
- **`build-autoware [workspace] [colcon args...]`** — sources ROS 2, runs `setup-autoware-env`,
  applies a tinyxml2_vendor CMake workaround, runs `rosdep install`, then `colcon build`.

```bash
# attach to the running container
docker exec -it ros2dev bash

# full build (defaults to /opt/autoware). Takes ~1h on the first run.
build-autoware

# build a subset, e.g. only autoware_launch and its dependencies
build-autoware /opt/autoware --packages-up-to autoware_launch
```

> [!NOTE]
> **tinyxml2_vendor workaround** — `build-autoware` patches the *installed*
> `tinyxml2_vendor-extras.cmake` (a known upstream bug: a third-party `FindTinyXML2.cmake`
> leaves `TINYXML2_LIBRARY` empty, which crashes CMake with *"Unable to extract the library
> file path from"*). The patch is applied idempotently at build time, so it always works
> even after the image is rebuilt.

### Verify the build

```bash
# inside the container
build-autoware
# ... wait for completion ...
# expected summary (no "packages failed" line):
#   Summary: 487 packages finished [..]
#   X packages had stderr output: ...   <- only warnings, NOT errors

# source the workspace and check your packages
source /opt/autoware/install/setup.bash
ros2 pkg list | grep autoware_launch
```

---

## Daily Development Workflow

1. **On the host** — edit code, switch branches, run git (the container never touches the
   source tree):

   ```bash
   cd ~/work/autoware
   git checkout feature/my-algorithm
   ```

2. **Inside the container** — compile and test:

   ```bash
   docker exec -it ros2dev bash
   build-autoware /opt/autoware --packages-select my_package   # fast incremental build
   source /opt/autoware/install/setup.bash
   ros2 launch autoware_launch autoware.launch.xml
   ```

3. **On the host** — run the simulation (Gazebo) and RViz2 directly on the host:

   ```bash
   source /opt/ros/humble/setup.bash
   gz sim -r --headless-rendering your_autoware_world.sdf
   ```

   Because the container shares `network`, `ipc` and `pid` namespaces with the host, the
   containerized Autoware nodes consume topics straight from the host Gazebo simulation.

---

## Image Contents & Helper Scripts (Reference)

| Path | Description |
|---|---|
| `/usr/local/bin/setup-autoware-env` | acados version gate + build + venv + env vars |
| `/usr/local/bin/build-autoware` | one-shot ROS2 env + rosdep + colcon build |
| `/opt/ros/humble` | ROS 2 Humble desktop install |
| `/usr/local/cuda` | CUDA 12.9 toolkit + TensorRT (CUDA 12.x build) |
| `/etc/profile.d/autoware.sh` | persisted CUDA/acados env vars (generated) |

RDP access (optional GUI): connect to `localhost:3389`, user `root`, password `ros2dev`.
Foxglove bridge listens on port `8765`.

---

## Troubleshooting

### `[ERROR] acados version mismatch!  Found : unknown`

The container runs as `root` but the mounted acados repo is owned by your host user. Git
refuses with *"detected dubious ownership"*, so `git describe` fails. The helper sets
`safe.directory` automatically, but if you ever see this, run once:

```bash
git config --global --add safe.directory /opt/acados
```

### `acados binaries were built from v0.6.0, but the source is now v0.5.3`

The compiled `libacados.so` in the mounted checkout was built from a different source version.
`setup-autoware-env` detects this via a version stamp and rebuilds automatically — no action
needed, just re-run it.

### I still see `Unable to extract the library file path from`

Confirm the tinyxml2 patch was applied by `build-autoware` (it logs `tinyxml2_vendor CMake fix
applied`). If you invoke `colcon build` directly instead of through `build-autoware`, run the
helper first:

```bash
source /opt/ros/humble/setup.bash
build-autoware --help   # just run it; the patch step runs before any build
```

### `colcon build finished with errors` but the log only shows warnings

A "packages had stderr output" line only lists packages that printed *warnings* — that is
normal. A real failure produces a `Failed <<< package` line and a non-zero exit code. Inspect
a specific package log if unsure:

```bash
cat /opt/autoware/log/latest_build/<package>/stdout_stderr.log
```
