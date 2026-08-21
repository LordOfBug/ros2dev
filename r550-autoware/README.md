# r550-autoware

Extends `r550-ros1-bridge` with a relay node that bridges sensor/control topics between the robot and a remote Autoware host over DDS.

## Architecture

```
┌──────────────────────────────────┐
│ Host x86: ros2dev (Autoware)    │
│ /opt/autoware + /opt/acados     │
│ Perception, planning, map       │
│ ROS_DOMAIN_ID=55                │
└──────────┬───────────────────────┘
           │ ROS2 DDS / LAN (peer discovery)
           ▼
┌──────────────────────────────────┐
│ Robot ARM64: r550-autoware       │
│ ┌────────────────────────────┐   │
│ │ r550-ros1-bridge (base)    │   │  ros1_bridge + bridge_mapping
│ └────────────┬───────────────┘   │
│              │                   │
│ ┌────────────▼───────────────┐   │
│ │ relay_node (new)           │   │  sensor/control topic relay
│ └────────────────────────────┘   │
│ ROS_DOMAIN_ID=55                │
└──────────┬───────────────────────┘
           │ ROS1 localhost:11311
           ▼
┌──────────────────────────────────┐
│ Robot: r550-humble-bot           │
│ Chassis, LiDAR, Camera          │
│ (existing, unchanged)            │
└──────────────────────────────────┘
```

## What's Inside

This image inherits everything from `r550-ros1-bridge` (ros1_bridge, bridge_mapping, control_msgs, overlays) and adds:

| Component | Purpose |
|-----------|---------|
| `relay_node` | Python node that relays `/scan`, `/odom`, `/tf` to host Autoware and forwards Autoware velocity commands to `/cmd_vel` |

---

## Build

### Prerequisites

Build the base bridge image first:
```bash
cd ../humble-ros1-bride
./download_assets.sh
docker buildx build --platform linux/arm64 -t r550-ros1-bridge:latest .
```

### Build this image

```bash
cd ../r550-autoware
./release.sh
```

Or manually:
```bash
docker buildx build --platform linux/arm64 -t r550-autoware:latest --load .
```

---

## Deploy

1. Copy `docker-compose.yaml` to the robot
2. Start:

```bash
docker compose up -d
```

Replace the `r550_ros1_bridge` service in your existing robot compose file with `r550_autoware`.

---

## Relay Node Configuration

Default topic mappings (`relay_node/config/relay_topics.yaml`):

| Direction | Robot Topic | Host Topic | Msg Type |
|-----------|------------|------------|----------|
| Robot → Host | `/scan` | `/robot/scan` | `LaserScan` |
| Robot → Host | `/odom` | `/robot/odom` | `Odometry` |
| Robot → Host | `/tf` | `/robot/tf` | `TFMessage` |
| Host → Robot | `/autoware/velocity_control/cmd_vel` | `/cmd_vel` | `Twist` |

Edit `relay_node/config/relay_topics.yaml` before building to customize.

---

## DDS Discovery

Both robot and host must use `ROS_DOMAIN_ID=55`. DDS peer discovery works automatically over LAN.

Verify on host:
```bash
source /opt/ros/humble/setup.bash
ros2 topic list | grep robot
# Should show /robot/scan, /robot/odom, etc.
```

---

## Troubleshooting

**Relay node doesn't start:** `docker logs r550_autoware`

**Host can't see robot topics:** Check `ROS_DOMAIN_ID=55` on both sides, verify UDP multicast is not blocked by firewall.

**cmd_vel not reaching robot:** `ros2 topic echo /cmd_vel` inside the container to verify relay is forwarding.
