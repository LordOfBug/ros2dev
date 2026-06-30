## Build Setup (Offline-Friendly)

To build the bridge image, you must first download the source code zip archives on your host machine (which has internet access), and then build the container (which compiles them offline).

### 1. Download Source Archives on Host
Run the download script from the host to download all 6 required repositories into an `assets/` subdirectory:
```bash
./download_assets.sh
```

### 2. Build the Docker Image
Once the archives are downloaded under `assets/`, run the build command. The Dockerfile will copy and compile them entirely offline:
```bash
docker buildx build --platform linux/arm64 -t r550-ros1-bridge:latest .
```

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
