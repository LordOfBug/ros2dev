# R550 ROS 2 Humble Bot Container

This directory contains the Docker environment for running the ROS 2 Humble navigation and driver stack on the R550 robot.

---

## Build Commands

To build the image natively or using an existing local builder:
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

### Steps for Setup & Compilation

Follow these steps on your development PC to set up the multi-platform builder and build the image:

1. **Install QEMU emulation support packages:**
   ```bash
   sudo apt-get update
   sudo apt-get install -y qemu-user-static binfmt-support
   ```

2. **Register QEMU static interpreters with Docker:**
   ```bash
   docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
   ```

3. **Create and select a new multi-platform builder instance:**
   ```bash
   docker buildx create --name r550_builder --use
   ```

4. **Initialize the builder:**
   ```bash
   docker buildx inspect --bootstrap
   ```
   *Note: In the printed output under `Platforms`, verify that both `linux/arm64` and `linux/amd64` are listed. This indicates that your builder is ready for cross-compiling.*

5. **Build and load the image into your local docker registry:**
   ```bash
   docker buildx build --platform linux/arm64 -t r550-humble-bot:latest --load .
   ```
   *Note: The `--load` flag directs the builder to export the compiled ARM64 image back into your local machine's docker image store.*
