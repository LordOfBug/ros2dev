#DEV Env Setup

## Overview

We use host ubuntu server for simulation, by sharing GPU with the dev docker container

  +---------------------------------------------------------------------------------+
  | UBUNTU HOST SYSTEM (Headless Server)                                            |
  |                                                                                 |
  |  +------------------------+                        +-------------------------+  |
  |  |     NVIDIA Driver      |                        |  Host Process: Gazebo   |  |
  |  +-----------+------------+                        +------------+------------+  |
  |              | Direct Hardware Pass                             | Shared Network|
  |              v                                                  v & IPC Memory  |
  |  +-----------+--------------------------------------------------+------------+  |
  |  | DOCKER CONTAINER (--gpus all --network=host --ipc=host)                   |  |
  |  |                                                                           |  |
  |  | +--------------------------+          +-------------------------------+   |  |
  |  | | CUDA / TensorRT Nodes    | <------> | ROS 2 Planning & Control Nodes|   |  |
  |  | | (Perception/Localization)|          | (Autoware Core Modules)       |   |  |
  |  | +--------------------------+          +-------------------------------+   |  |
  |  +---------------------------------------------------------------------------+  |
  +---------------------------------------------------------------------------------+


### Setup

1. validate & install essentials

```code
# 1. Verify your NVIDIA drivers are installed natively on the host
nvidia-smi

# 2. Install the NVIDIA Container Toolkit (allows Docker to access GPU hooks)
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# 3. Restart the Docker daemon to apply configuration changes
sudo systemctl restart docker
```

2. Prepare DEV container

Autoware relies heavily on external artifacts (such as neural network .onnx architectures and .pcd pointcloud routing maps), create structured folders on your host to pass into the container runtime.

```code
mkdir -p ~/autoware_ws/src
mkdir -p ~/autoware_data/maps
mkdir -p ~/autoware_data/ml_models
```

3. Docker compose setup

We can use pre-built autoware image to work as DEV env

```code
version: '3.8'

services:
  autoware-dev:
    # Using the prebuilt Autoware Universe developer build containing CUDA stacks
    image: ghcr.io/autowarefoundation/autoware-universe:latest-cuda
    container_name: autoware_universe_container
    
    # Crucial configurations for zero-latency communication with host tools (Gazebo)
    network_mode: host
    ipc: host
    pid: host
    
    privileged: true
    tty: true
    stdin_open: true

    environment:
      - ROS_DOMAIN_ID=0
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics

    volumes:
      # Persistent development paths
      - ~/autoware_ws/src:/autoware/src
      - ~/autoware_data/maps:/autoware/map
      - ~/autoware_data/ml_models:/autoware/autoware_data/models
      # Pass hardware graphics drivers for internal acceleration
      - /tmp/.X11-unix:/tmp/.X11-unix:rw

    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

Or we can build from source using our own ros2 desktop container (See below section)

4. Launch & Test Dev Work Pipeline

** 1. Launch the Simulation on the Host Terminal
Execute Gazebo directly inside your Ubuntu host environment shell:

```code
# Runs on Host Machine
source /opt/ros/humble/setup.bash
gz sim -r --headless-rendering your_autoware_world.sdf
```

**note**: (By adding --headless-rendering, Gazebo safely generates camera sensors and physics logic directly on the GPU without trying to paint an interactive UI display frame).

** 2. Enter and Execute Autoware Nodes Inside the Container
Spin up your developer workspace container shell via another terminal link:

```code
# Start and attach into the container 
docker compose up -d
docker exec -it autoware_universe_container bash

# Inside the Container: Verify CUDA pipeline accessibility
nvcc --version
nvidia-smi
```

** 3. Cuda Prepration
Base ros2dev image has no cuda support, we need to install it manually with following scripts

```code
# 1. Setup NVIDIA apt repos
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
dpkg -i cuda-keyring_1.1-1_all.deb
apt-get update

# 2. Install CUDA & TensorRT
apt-get install -y cuda-toolkit-12-3 libnvinfer-dev libnvinfer-plugin-dev

# 3. Export environment paths
export CUDA_HOME=/usr/local/cuda
export PATH=/usr/local/cuda/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH

# 4. Verify nvcc is accessible
nvcc --version
```

** 4. Test & Start DEV
You are now ready to run your localization or perception stacks safely inside the container environment. For example:

```code
# Inside Container
source /opt/autoware/setup.bash
ros2 launch autoware_launch autoware.launch.xml vehicle_model:=sample_vehicle sensor_model:=sample_sensor_kit
```

Because your network hooks, PID lines, and IPC memory namespaces match completely (host), the containerized deep-learning modules will consume data packets directly from the host simulation environment, run the math calculations using your GPU hardware acceleration, and output immediate navigation values instantly.

## Custom Autoware Dev Env

We would try to set up and use our custom autoware dev env, we shall standardize the process to avoid problems

As a rule
1. autoware source is managed in host ubuntu with git
2. source is mapped to docker container as a volue (e.g. /work/autoware)
3. docker conatiner just use the source to build etc. for DEV purpose

This would save source management functions from container, thus make it simpler and focused on DEV & testing tasks

### Step 0: Clone Acados
Acadas v0.5.3 is required to build autowire, so we shall clone and map it to docker before we can make it work

```code
    git clone https://github.com/acados/acados.git ./acados
    cd ./acados
    git fetch --tags --all
    git checkout v0.5.3
    git submodule update --recursive --init
```

And mount in docker compose file

```code
volumes:
      ...
      - /work/acados:/opt/acados
```

Note, we need v0.5.3, in case anything goes wrong, so the best way to do this is to follow this struction

```code
# 1. force reset on source
git reset --hard HEAD

# 2. swtich to tag v0.5.3
git checkout v0.5.3

# 3. Must do: force to sync and reset sub modules to matching tags
git submodule foreach --recursive 'git reset --hard HEAD && git clean -fdx'
git submodule update --recursive --init

```

### Step 1: Clone Autoware and Prep Your Workspaces
First, create separate directory paths on your Ubuntu Host server so that your code workspace persists even if the container is stopped or rebuilt.

```code
# On your Host System: Create persistent workspace structures
mkdir -p ~/autoware_ws

# Clone the main Autoware deployment repository
cd ~/work
git clone https://github.com/autowarefoundation/autoware.git ./autoware
```


The Best Practic is to try isolating Build Artifacts from source, for this purpose, mount your source directories, but use anonymous volumes to force the container to write all compilation artifacts (build, install, log) directly to its fast internal layer.

Update your docker-compose.yml volume definitions to look like this:

```code
volumes:
      # 1. Mount your host's ready Git source tree into the container
      - /work/autoware:/opt/autoware
      
      # 2. Force build outputs to stay inside the container's fast filesystem
      - /opt/autoware/build
      - /opt/autoware/install
      - /opt/autoware/log
```

### Step 2: Automate Dependency Injection via Ansible
Since source codes are managed onhost, your container only needs to ensure that the exact system binary dependencies required by your current branch are present. Run this once inside the container workspace (/workspace/autoware):

```code
source /opt/ros/humble/setup.bash
rosdep update
rosdep install -y --from-paths src --ignore-src --rosdistro humble
```

### Step 3: Turbocharging Compilation with ccache
Compiling Autoware Universe from source can take up to an hour depending on your server's CPU. By leveraging ccache (Compiler Cache), consecutive builds (like when switching branches or modifying single files) drop from 45 minutes to less than 2 minutes.

1. Install ccache in your container or custom image:
```code
sudo apt-get update && sudo apt-get install -y ccache
```

(note: we use ros2dev, which already get ccache built into image)

2. Inject ccache directly into your colcon build pass:
```code
colcon build \
  --symlink-install \
  --cmake-args \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
    -DCMAKE_C_COMPILER_LAUNCHER=ccache \
  --parallel-workers $(nproc)
```

3. Automate Dependency Injection via Ansible
Autoware comes packaged with setup automation via Ansible. Since your image is a clean ROS 2 layout, it lacks the required CUDA wrappers, pacmod libraries, and planning dependencies.  Run Autoware's setup playbook directly inside your active container shell:

(Note: Because the container already runs as root or a privileged user, this script will securely overlay all third-party libraries without conflicting with your host OS server libraries).

```code
# Still inside /workspace/src/autoware
# 1. Install ansible binaries inside your container
bash ansible/scripts/install-ansible.sh

# 2. Execute the setup playbook. 
# This handles everything: CUDA setup, TensorRT setup, and core system libraries.
ansible-galaxy collection install -f -r ansible-galaxy-requirements.yaml
ansible-playbook autoware.dev_env.install_dev_env
```

4. Initialize Rosdep for ROS Packages

Now that the external system frameworks (like CUDA/TensorRT) are present, use rosdep to parse the underlying source folders and fetch any missing community ROS 2 package components:  

```code
cd /workspace/src/autoware

# Source your baseline environment
source /opt/ros/humble/setup.bash

# Sync and pull systemic definitions
sudo rosdep init # Run only if rosdep was never initialized in your custom image
rosdep update

# Automatically install all missing ROS 2 Humble binary dependencies
rosdep install -y --from-paths src --ignore-src --rosdistro $ROS_DISTRO
```

5. Execute the Colcon Build Pipeline
With all background requirements resolved, you are ready to kick off the compilation process.

Because Autoware is massive and highly parallelized, compiling every single package can easily max out system resources. It is highly recommended to pass optimization constraints so your server doesn't crash from memory depletion during complex template parsing:

```code
cd /workspace/src/autoware

# Clean, production-optimized compilation pass
colcon build \
  --symlink-install \
  --cmake-args -DCMAKE_BUILD_TYPE=Release \
  --parallel-workers $(nproc)
```

**--symlink-install**: Saves massive disk space and prevents needing to rebuild packages when you only modify non-compiled configuration files (like Python nodes or launch scripts).
**-DCMAKE_BUILD_TYPE=Release**: Essential for actual performance. It enables full compiler optimizations ($O3$) for heavy operations like NDT matching and perception processing.


### Daily Developer Workflow Loop
Now that the source code sync is completely offloaded to the host, your day-to-day workflow becomes extremely simple and clean:

1. On the Host Machine
Use your standard git workflows, switch branches, or open your workspace in VS Code/Cursor directly:
```code
cd /work/autoware
git checkout feature/your-planning-algorithm
```

2. Inside the Docker Container:
Open a terminal inside the container to compile and run the nodes. Because of --symlink-install, any changes you make to launch scripts or Python nodes on the host take effect instantly without needing a recompile.

```
# Attach to your running container
docker exec -it autoware_build_env bash
cd /workspace/autoware

# Compile only when modifying C++ source files
colcon build --symlink-install --packages-select autoware_universe_your_package

# Source and launch
source install/setup.bash
ros2 launch autoware_launch autoware.launch.xml
```
