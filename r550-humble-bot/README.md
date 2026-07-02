# R550 ROS 2 Humble Bot Container

This directory contains the Docker environment for running the ROS 2 Humble navigation and driver stack on the R550 robot.

---

## Build Commands

To build the image (which will automatically clone/update the required `Lslidar_ROS2_driver` dependency into an `assets` folder before building):
```bash
./release.sh
```

Alternatively, to build manually if the assets are already populated:
```bash
docker buildx build --platform linux/arm64 -t r550-humble-bot:latest .
```

---

## Compiled Driver Packages (`assets/`)

To keep the ROS 2 runtime environment on the Jetson Nano fully self-contained, `release.sh` downloads and compiles the following hardware driver packages inside the container:

### 1. `Lslidar_ROS2_driver` (Branch: `LS-S1_V1.0`)
* **Purpose**: Driver for the **Lslidar N10** 2D laser scanner mounted on the R550.
* **What it does**: Establishes a high-speed serial connection (at 230400 bps) with the LiDAR device over `/dev/wheeltec_lidar` (or `/dev/r550_lidar`) and publishes the 2D planar point cloud data on the `/scan` topic at 10Hz.
* **Why we need it**: The laser scan data `/scan` is the primary sensor stream used by SLAM (to build the occupancy grid map) and Nav2 (to populate local/global costmaps and avoid static/dynamic obstacles).

### 2. `rplidar_ros` (Branch: `ros2`)
* **Purpose**: Driver for Slamtec **RPLiDAR** series laser scanners (A1, A2, A3, S1, S2, S3, C1).
* **What it does**: Reads serial scanner packages and publishes standard `sensor_msgs/LaserScan` messages on the `/scan` topic.
* **Why we need it**: Provides plug-and-play support for alternative R550 configurations that run Slamtec LiDARs instead of Lslidar N10 sensors.

### 3. `serial-ros2`
* **Purpose**: A ROS 2 wrapper for the cross-platform `serial` library.
* **What it does**: Handles raw, low-level RS-232 serial communication with the robot's onboard microcontroller (STM32).
* **Why we need it**: The main control node (`turn_on_wheeltec_robot`) depends on this package to write wheel velocity targets and read physical encoder speeds and battery telemetry over the USB-to-serial connection `/dev/wheeltec_robot`.

### 4. `turn_on_wheeltec_robot` (Extracted from `wuyang156/wheeltec_WS_src`)
* **Purpose**: Wheeltec physical robot chassis coordinator node.
* **What it does**: 
  * Subscribes to `/cmd_vel` velocity target topics.
  * Computes differential kinematics (translates overall linear/angular velocities to individual wheel spin rates).
  * Commands the STM32 board via the serial port connection.
  * Receives physical encoder ticks to compute and publish wheel odometry coordinates (`odom_combined` $\rightarrow$ `base_footprint` TF transform and `/odom` topic).
  * Publishes voltage and battery alerts on the `/PowerVoltage` topic.
* **Why we need it**: This is the core logical link between your autonomous navigation algorithms (which output velocity vectors on `/cmd_vel`) and the physical motors on the floor.

### 5. `wheeltec_robot_msg` (Extracted from `wuyang156/wheeltec_WS_src`)
* **Purpose**: Custom ROS 2 message interface files for the Wheeltec chassis.
* **What it does**: Defines unique data structures, such as `/PowerVoltage` (custom battery status).
* **Why we need it**: Required at compile-time and runtime by `turn_on_wheeltec_robot` and monitoring scripts.

### 6. `wheeltec_robot_urdf` (Extracted from `wuyang156/wheeltec_WS_src`)
* **Purpose**: Unified Robot Description Format (URDF) description.
* **What it does**: Specifies the physical dimensions and coordinate frames of the R550 (e.g., distance from wheel centers to chassis origin, and position/rotation offset of the LiDAR and camera relative to the base center).
* **Why we need it**: Generates the static transforms (`tf_static`) between `base_footprint`, `base_link`, `laser`, and `camera_link`. Without it, Nav2 cannot coordinate sensor positions relative to the wheels, leading to immediate transform errors.

---

## Cross-Platform Build Workflow

When developing on a standard x86_64 development PC, you can compile the target ARM64 image using QEMU emulation:

```
 [ Ubuntu Dev PC (x86_64) ] 
            │
            ▼ (QEMU emulating ARM64 instructions)
 [ Docker Buildx Cross-Compiler ] ──( Fast Compile )──> [ Physical linux/arm64 Image ]
                                                                 │
                                                   ┌─────────────┴─────────────┐
                                                   ▼ (Method A: LAN Offline)   ▼ (Method B: Cloud Push)
                                             [ scp .tar package ]        [ Docker Registry ]
                                                   │                           │
                                                   └─────────────┬─────────────┘
                                                                 ▼ (Import and Run)
                                                      [ R550 Robot (ARM64) ]
```

### Steps for Setup & Compilation (Emulation Mode)

Follow these steps on your development PC to set up a modern, stable multi-platform builder and run emulated builds:

1. **Install the modern, official QEMU binfmt handlers:**
   Do not use the old, deprecated `multiarch/qemu-user-static` image. Instead, register the modern Docker-supported handlers:
   ```bash
   docker run --privileged --rm tonistiigi/binfmt --uninstall qemu-*
   docker run --privileged --rm tonistiigi/binfmt --install all
   ```

2. **Automated Workaround for Emulated Linker Segfaults (Bypass ASLR):**
   QEMU user-mode emulation has a known issue where host Address Space Layout Randomization (ASLR) collides with the guest VM's memory maps, causing random compiler/linker segmentation faults during multi-threaded compiles.
   
   To handle this, `release.sh` **automatically** disables ASLR on your host (`sudo sysctl kernel.randomize_va_space=0`) before the build starts and uses a bash `trap` to safely restore it back to its original state when the script exits, even if the build fails or is canceled. *(Note: You will be prompted for your host sudo password once to authorize this system call).*

3. **Create and select a new multi-platform builder instance:**
   ```bash
   docker buildx create --name r550_builder --use
   ```

4. **Initialize the builder:**
   ```bash
   docker buildx inspect --bootstrap
   ```

5. **Build and load the image:**
   ```bash
   docker buildx build --platform linux/arm64 -t r550-humble-bot:latest --load .
   ```
   *(With host ASLR disabled, you can raise compilation concurrency inside your Dockerfile safely).*

---

### Alternative: Native Remote Builds (Recommended for Speed)

To completely bypass QEMU overhead and emulation bugs, you can configure your host to build natively on the robot's physical ARM64 CPU:

1. **Add the robot as a Docker context on your host:**
   ```bash
   docker context create r550-robot --docker host=ssh://username@robot-ip-address
   ```
2. **Create a builder instance that uses the robot's native Docker engine:**
   ```bash
   docker buildx create --name native-builder --use default
   docker buildx create --append --name native-builder r550-robot
   ```
3. **Build natively:**
   ```bash
   docker buildx build --platform linux/arm64 -t r550-humble-bot:latest --load .
   ```

---

## Base Image Selection

### Why we use `arm64v8/ros:humble-perception`
For the robot navigation and control stack image, we keep the hardware-optimized **`arm64v8/ros:humble-perception`** base image.
* **No Source Compilation During Build:** The bot's Dockerfile only installs packages via `apt-get` and does not compile C++ source code during the build. This means there are no complex linking processes that trigger QEMU emulator collisions on your development host.
* **Native Runtime Optimization:** When deployed to the physical R550 robot, it runs natively on ARM64 hardware. The hardware-specific optimizations (such as Neon vector instructions, CPU-specific extensions, and GPU bindings) built into the `perception` image are highly beneficial here, providing low-latency execution for `navigation2`, sensor processing, and localization tasks on the robot's hardware.

---

## Running & Deploying on the Robot

A sample **[`docker-compose.yaml`](file:///home/coder/work/ros2/r550/r550-humble-bot/docker-compose.yaml)** is provided to run all hardware drivers inside the built image natively on the robot's Jetson Nano.

### 1. Hardware Device Mapping (Host to Container)
The Compose file maps your physical USB devices to the exact virtual nodes needed inside the container:
* **STM32 Controller**: `/dev/wheeltec_controller` $\rightarrow$ Mounts as `/dev/wheeltec_controller` (Chassis node default).
* **Lslidar N10**: `/dev/wheeltec_lidar` $\rightarrow$ Mounts as `/dev/wheeltec_lidar` (Lslidar node default).
* **IMU / GPS**: `/dev/wheeltec_gps` $\rightarrow$ Mounts as `/dev/wheeltec_gps`.
* **Astra Camera**: `/dev/bus/usb` $\rightarrow$ Mounts the raw USB bus (required for LibUSB-based depth cameras).

### 2. Custom Lslidar N10 Parameters
To prevent rebuilding the Docker image for config modifications, we mount a custom local YAML file:
* **File**: **[`config/lslidar_x10.yaml`](file:///home/coder/work/ros2/r550/r550-humble-bot/config/lslidar_x10.yaml)**
* **Parameters**: Sets `lidar_model: "N10"`, `serial_port: "/dev/wheeltec_lidar"`, and `use_high_precision: true`.

### 3. Deploy and Run
Copy the `docker-compose.yaml` and `config/` directory to the robot's directory, and spin it up:
```bash
# Run in the foreground to monitor driver logs
docker compose up

# Run in the background (Daemon mode)
docker compose up -d
```

### 4. Verify Nodes and Topics
Open a shell inside the running container (or on the robot's host terminal if ROS 2 is sourced) to verify that sensors are communicating properly:
```bash
# Enter the running drivers container
docker exec -it r550_drivers bash

# Sourced automatically or manually
source /opt/ros/humble/setup.bash

# Check if topics are active
ros2 topic list
# You should see:
# - /scan (Planar LiDAR scanner)
# - /odom (Robot wheel odometry)
# - /cmd_vel (Robot velocity command subscriber)

# Echo the scan data to verify N10 output
ros2 topic echo /scan --limit 1
```
