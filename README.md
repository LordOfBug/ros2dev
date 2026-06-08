# ROS 2 Humble Development Environment (`ros2dev`)

Welcome to your containerized ROS 2 Humble development workspace! This repository provides a fully isolated, graphical desktop environment optimized for robotics development.

It features **Ubuntu 22.04 LTS (Jammy)**, **ROS 2 Humble Hawksbill (Desktop Install)**, and an **XFCE4 Desktop Environment** accessible via Remote Desktop (RDP). This allows you to run graphical ROS 2 tools (such as Turtlesim, RViz2, and Gazebo) directly from inside a Docker container without complex host X11 forwarding configurations.

---

## Architecture & Quick Start

The environment is packaged as a Docker container. 

### 1. Build the Docker Image
To build the image locally, navigate to the `docker/` directory and run the build script:
```bash
cd docker
./build.sh
```

### 2. Run the Container
Start the container and expose the RDP port (`3389`):
```bash
docker run -d \
  --name ros2dev_container \
  -p 3389:3389 \
  --privileged \
  ros2dev:latest
```
> [!NOTE]
> The `--privileged` flag is recommended to allow full hardware access (e.g., for GPU acceleration in simulators like Gazebo) and container system loopbacks.

### 3. Connect via RDP
Open any Remote Desktop Client (e.g., Remmina on Linux, Remote Desktop Connection on Windows, or Microsoft Remote Desktop on macOS) and connect to:
- **Host:** `localhost:3389`
- **Username:** `root`
- **Password:** `ros2dev`

---

## Sample Use: Turtlesim Demo

When you first open a terminal in your desktop container, running `ros2 node list` will only show `/parameter_events` and `/rosout` in the topic list. This is **completely normal**! 

`ros2 node list` is a live diagnostic tool—it only shows nodes that are **currently running**. Since the workspace starts fresh, no applications or robots are active yet.

Let's launch the classic ROS 2 graphical demo: **Turtlesim**. This will let you control a virtual robot and see the computational graph populate in real-time.

### Step 1: Launch the Turtle GUI
Inside your RDP desktop window, open a terminal (**Applications -> Terminal Emulator**) and run:
```bash
ros2 run turtlesim turtlesim_node
```
*A blue window will pop up with a small turtle standing in the center.*

### Step 2: Launch the Keyboard Controller
Leave the first terminal running. Open a **second terminal window** inside your RDP desktop and run:
```bash
ros2 run turtlesim turtle_teleop_key
```
*Keep this second terminal active. Use the **arrow keys** on your keyboard, and you will see the turtle on your screen start driving around, leaving a line behind it.*

### Step 3: Inspect the Live Graph
Open a **third terminal window** inside your RDP desktop. Let's run the diagnostic commands again while the turtle is active:

1. **Check the active nodes:**
   ```bash
   ros2 node list
   ```
   You will now see:
   ```text
   /turtlesim
   /teleop_turtle
   ```

2. **Check the active topics:**
   ```bash
   ros2 topic list
   ```
   You will see the new topics carrying velocity and sensor data:
   ```text
   /parameter_events
   /rosout
   /turtle1/cmd_vel
   /turtle1/color_sensor
   /turtle1/pose
   ```

3. **Echo the keyboard commands in real-time:**
   Run the following command, then click back onto your keyboard controller terminal (from Step 2) and tap the arrow keys:
   ```bash
   ros2 topic echo /turtle1/cmd_vel
   ```
   You will see the raw $x$ linear and $z$ angular velocity vectors flying across the screen in real-time!

---

## Learning & Reference Resources

Getting a fully isolated, graphical environment running inside Docker is often the highest initial hurdle for new robotics developers. You are now ready to start writing packages and nodes.

Since you are already comfortable with system architecture and writing software, you can skip the basic "Intro to Linux/Python" tutorials and dive straight into how ROS 2 handles distributed messaging and node lifecycles.

Here are the three most valuable resources to get you building quickly:

### 1. The Source of Truth: [Official ROS 2 Humble Tutorials](https://docs.ros.org/en/humble/Tutorials.html)
* **What it is:** The official step-by-step ROS 2 documentation.
* **Where to start:** Skip the setup guides and jump straight into the **"Beginner: Client Libraries"** section.
* **Why it matters:** This will walk you through creating your first Python and C++ packages, writing custom Talker/Listener nodes, and understanding how to structure your `CMakeLists.txt` and `package.xml` files. It is the absolute best place to learn the ROS 2 API syntax.

### 2. Architectural Deep-Dive: [ROS 2 Design](https://design.ros2.org/)
* **What it is:** Design documents and articles detailing the architectural concepts behind ROS 2.
* **Where to start:** Read the articles on **"Changes between ROS 1 and ROS 2"** and **"DDS as the ROS middleware"**.
* **Why it matters:** For someone building large-scale systems, understanding *why* the framework behaves the way it does is critical. This site explains the engineering decisions behind ROS 2, covering how the Data Distribution Service (DDS) handles node discovery without a central master, how memory management works, and how Executor models handle threading.

### 3. Practical 3D Simulation & Applications: [Articulated Robotics](https://www.youtube.com/@ArticulatedRobotics)
* **What it is:** A high-quality tutorial channel bridging code and simulated/physical robots.
* **Where to start:** The **"Building a Mobile Robot"** or **"ROS 2 Basics"** playlists.
* **Why it matters:** Reading documentation is one thing, but seeing how to configure a robot's URDF (Unified Robot Description Format) and launch it in Gazebo is another. Josh Newans provides incredibly high-quality, step-by-step visual guides that show how to connect the code you write to a 3D physics simulator.
