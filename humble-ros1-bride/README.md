## Build Command

To compile and pack the image for the target robot architecture (`linux/arm64`), use the following command:
```bash
docker buildx build --platform linux/arm64 -t r550-ros1-bridge:latest .
```

## Running the Bridge

Since `ros1_bridge` requires both ROS1 and ROS2 node discovery over the local network, you should start the container with host networking:

```bash
docker run -it --rm \
  --network host \
  -e ROS_MASTER_URI=http://127.0.0.1:11311 \
  r550-ros1-bridge:latest
```

*Note: Replace `127.0.0.1` with the IP address of the device running the ROS1 `roscore` if it is not running on the same local host.*

## Testing Sourcing & Custom Commands

If you need to log in to the running bridge container to inspect nodes, you can execute a bash shell:
```bash
docker exec -it <container_id_or_name> bash
```

Inside the container:
- Sourcing is handled automatically by the entrypoint.
- If you need to source specific environments manually:
  ```bash
  # Source ROS2:
  source /opt/ros/humble/setup.bash
  
  # Source ROS1 (installed via system package paths):
  # (Sourcing is not required for system paths, but any custom compiled overlays can be sourced via their workspace setup)
  source /ros_tutorials/install/setup.bash
  source /common_tutorials/install/setup.bash
  source /control_msgs_ros1/install/setup.bash
  
  # Source the Bridge:
  source /ros-humble-ros1-bridge/install/setup.bash
  ```
