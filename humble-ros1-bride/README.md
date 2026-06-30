## Build Setup (Offline-Friendly)

To build the bridge image, you must first download the source code zip archives on your host machine (which has internet access), and then build the container (which compiles them offline).

### 1. Download Source Archives on Host
Run the download script from the host to download all 6 required repositories into an `assets/` subdirectory:
```bash
./download_assets.sh
```

### 2. Configure Your Host for Emulated Build (Avoid Emulation Linker Segfaults)
QEMU user-mode emulation has a known issue where host Address Space Layout Randomization (ASLR) collides with the guest VM's memory maps, causing random compiler/linker segmentation faults during multi-threaded compiles.
To compile in parallel at full speed using multiple jobs, perform these host setup steps:

1. **Install the modern, official QEMU binfmt handlers:**
   ```bash
   docker run --privileged --rm tonistiigi/binfmt --uninstall qemu-*
   docker run --privileged --rm tonistiigi/binfmt --install all
   ```
2. **Temporarily disable ASLR on the host machine before starting the build:**
   ```bash
   sudo sysctl kernel.randomize_va_space=0
   ```
   *(Note: Remember to re-enable it by setting it back to `2` once your build completes).*

### 3. Build the Docker Image
Once the host is configured and the archives are downloaded under `assets/`, run the build command:
```bash
docker buildx build --platform linux/arm64 -t r550-ros1-bridge:latest .
```

*Tip: If you prefer to completely avoid QEMU emulation overhead, you can configure your host to build natively on the robot's physical ARM64 CPU. See the remote context instructions in the [r550-humble-bot README](../r550-humble-bot/README.md#alternative-native-remote-builds-recommended-for-speed).*

---

## Automatic Startup Port Checking

The container has built-in port checking in its entrypoint. When starting up, if the command is running the bridge (default), the container will automatically:
1. Parse the `ROS_MASTER_URI` (defaults to `http://localhost:11311`).
2. Verify if the target port 11311 is reachable.
3. Block/wait gracefully if not reachable (printing status messages).
4. Source all workspaces and launch the bridge once the ROS 1 Master becomes active.

This makes the container extremely resilient when run via orchestrators like `docker-compose` or `systemd`, preventing crash loops.

---

## Running the Container

### Option A: Docker Compose (Recommended)

Add the following service to your `docker-compose.yml`:

```yaml
version: '3.8'

services:
  ros1_bridge:
    image: r550-ros1-bridge:latest
    container_name: r550_ros1_bridge
    network_mode: host
    environment:
      - ROS_MASTER_URI=http://127.0.0.1:11311
    restart: always
```

### Option B: Docker Run

Run the container using:
```bash
docker run -d \
  --name r550_ros1_bridge \
  --network host \
  -e ROS_MASTER_URI=http://127.0.0.1:11311 \
  --restart always \
  r550-ros1-bridge:latest
```

*Note: Replace `127.0.0.1` with the IP address of the device running the ROS1 `roscore` if it is not running on the same local host.*

---

## Testing & Custom Commands

If you need to log in to the running container to debug:
```bash
docker exec -it r550_ros1_bridge bash
```

Inside the container, all environments are automatically sourced. If you need to source specific workspaces manually:
```bash
# Source ROS2:
source /opt/ros/humble/setup.bash

# Source ROS1 overlays:
source /ros_tutorials/install/setup.bash
source /common_tutorials/install/setup.bash
source /control_msgs_ros1/install/setup.bash

# Source the Bridge:
source /ros-humble-ros1-bridge/install/setup.bash
```

---

## Base Image Selection

### Why we use `ros:humble-ros-base-jammy`
For the bridge image, we use the official, generic **`ros:humble-ros-base-jammy`** base image.
* **QEMU Emulation Stability:** Since this image compiles custom C++ code (like `roscpp_tutorials` and `ros1_bridge`) during the build process, compiling under emulation (`linux/arm64` on `x86_64`) requires a generic, hardware-agnostic base.
* **Avoiding Emulator Crashes:** Hardware-optimized images (like Jetson-optimized or Nvidia-optimized `arm64v8/ros` stacks) contain processor-specific instruction set extensions (e.g., LSE atomics, vector registers) that trigger address space collisions or illegal instruction segfaults under QEMU user-mode emulation. Using the official generic base avoids these issues.
