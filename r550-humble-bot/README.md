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

2. **Workaround for Emulated Linker Segfaults (Bypass ASLR):**
   QEMU user-mode emulation has a known issue where host Address Space Layout Randomization (ASLR) collides with the guest VM's memory maps, causing random compiler/linker segmentation faults during multi-threaded compiles.
   To compile in parallel at full speed using multiple jobs, temporarily disable ASLR on your host machine before building:
   ```bash
   # Temporarily disable ASLR on host
   sudo sysctl kernel.randomize_va_space=0
   ```
   *(Note: Remember to re-enable it by setting it back to `2` once your build completes).*

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
