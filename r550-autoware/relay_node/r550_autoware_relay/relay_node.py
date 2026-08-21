#!/usr/bin/env python3
"""
r550_autoware_relay — lightweight relay between robot sensors/control and remote Autoware.

Subscribes to sensor topics bridged from the robot's ROS1 stack (via ros1_bridge)
and republishes them for the host Autoware instance. Subscribes to Autoware velocity
commands and forwards them to the robot's /cmd_vel.

All topic mappings are configurable via ROS parameters (loaded from YAML).
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy

from geometry_msgs.msg import Twist
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import Odometry
from std_msgs.msg import Header


# Default QoS matching typical ROS1 bridge behavior
_BRIDGE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)


class RelayNode(Node):
    def __init__(self):
        super().__init__('r550_autoware_relay')

        # ── Parameters (topic name mappings) ──────────────────────────────
        self.declare_parameter('robot_to_host', [
            # [robot-side topic (after bridge), host-side republished topic, msg_type]
            # LaserScan
            ['/scan', '/robot/scan', 'sensor_msgs/LaserScan'],
            # Odometry
            ['/odom', '/robot/odom', 'nav_msgs/Odometry'],
        ])

        self.declare_parameter('host_to_robot', [
            # [host-side topic (from Autoware), robot-side topic, msg_type]
            ['/autoware/velocity_control/cmd_vel', '/cmd_vel', 'geometry_msgs/Twist'],
        ])

        self.declare_parameter('robot_cmd_vel', '/cmd_vel')
        self.declare_parameter('autoware_cmd_vel', '/autoware/velocity_control/cmd_vel')

        # ── Dynamic subscriber/publisher storage ──────────────────────────
        self._subscribers = []
        self._publishers = {}

        # ── Direct cmd_vel bridge (always active) ────────────────────────
        robot_cmd = self.get_parameter('robot_cmd_vel').value
        autoware_cmd = self.get_parameter('autoware_cmd_vel').value

        self._cmd_vel_pub = self.create_publisher(
            Twist, robot_cmd, 10
        )

        self._cmd_vel_sub = self.create_subscription(
            Twist, autoware_cmd, self._cmd_vel_callback, 10
        )

        self.get_logger().info(
            f'Relaying cmd_vel: {autoware_cmd} -> {robot_cmd}'
        )

        # ── Set up relay pairs from parameters ───────────────────────────
        robot_to_host = self.get_parameter('robot_to_host').value
        host_to_robot = self.get_parameter('host_to_robot').value

        for src_topic, dst_topic, msg_type in robot_to_host:
            self._setup_relay(src_topic, dst_topic, msg_type, direction='robot->host')

        for src_topic, dst_topic, msg_type in host_to_robot:
            # Skip if it's the same as the cmd_vel pair (already handled above)
            if src_topic == autoware_cmd and dst_topic == robot_cmd:
                continue
            self._setup_relay(src_topic, dst_topic, msg_type, direction='host->robot')

        self.get_logger().info(
            f'r550_autoware_relay started — '
            f'{len(self._subscribers)} subscribers, '
            f'{len(self._publishers)} publishers'
        )

    def _cmd_vel_callback(self, msg: Twist):
        self._cmd_vel_pub.publish(msg)

    def _setup_relay(self, src_topic, dst_topic, msg_type, direction='?'):
        """Create a subscriber on src_topic that republishes to dst_topic."""
        msg_class = self._resolve_msg_type(msg_type)
        if msg_class is None:
            self.get_logger().warn(
                f'Unknown msg type "{msg_type}" for relay {src_topic} -> {dst_topic}, skipping'
            )
            return

        pub = self.create_publisher(msg_class, dst_topic, _BRIDGE_QOS)

        def relay_callback(msg, _pub=pub):
            _pub.publish(msg)

        sub = self.create_subscription(msg_class, src_topic, relay_callback, _BRIDGE_QOS)
        self._subscribers.append(sub)
        self._publishers[dst_topic] = pub

        self.get_logger().info(
            f'[{direction}] {src_topic} ({msg_type}) -> {dst_topic}'
        )

    @staticmethod
    def _resolve_msg_type(msg_type_str):
        """Resolve a message type string like 'sensor_msgs/LaserScan' to its class."""
        _TYPE_MAP = {
            'sensor_msgs/LaserScan': LaserScan,
            'sensor_msgs/Image': None,  # lazy import if needed
            'sensor_msgs/PointCloud2': None,
            'nav_msgs/Odometry': Odometry,
            'geometry_msgs/Twist': Twist,
            'geometry_msgs/PoseStamped': None,
            'geometry_msgs/PoseWithCovarianceStamped': None,
            'std_msgs/Header': Header,
        }
        return _TYPE_MAP.get(msg_type_str)


def main(args=None):
    rclpy.init(args=args)
    node = RelayNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
