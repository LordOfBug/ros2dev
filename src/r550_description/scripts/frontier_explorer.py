#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R550 自主探索节点 — Frontier Exploration

标准 frontier 探索策略：
  1. 检测 SLAM 地图上的 frontier（已知自由空间与未知区域的边界）
  2. 选择最佳 frontier（优先大面积 + 近距离）
  3. 导航到 frontier 附近，Lidar（12m 射程）自动扫描并扩展地图
  4. 主动监控导航进度，卡住则取消重试
  5. 重复直到没有 frontier

用法:
  ros2 run r550_description frontier_explorer.py
"""

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.action import ActionClient
from rclpy.duration import Duration
from nav_msgs.msg import OccupancyGrid
from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import PoseStamped
from visualization_msgs.msg import Marker, MarkerArray
import numpy as np
from scipy.ndimage import label, binary_dilation
import math
import tf2_ros


class FrontierExplorer(Node):
    def __init__(self):
        super().__init__('frontier_explorer')

        # ===================== 可配置参数 =====================
        self.declare_parameter('min_frontier_size', 5)
        self.declare_parameter('robot_frame', 'base_footprint')
        self.declare_parameter('blacklist_radius', 1.0)
        self.declare_parameter('update_interval', 2.0)
        self.declare_parameter('min_goal_distance', 0.5)      # 忽略太近的 frontier
        self.declare_parameter('goal_offset', 0.3)             # 目标点偏移量（从 frontier 向 robot 方向）
        self.declare_parameter('no_progress_timeout', 15.0)    # 无进展超时

        self.min_frontier_size = self.get_parameter('min_frontier_size').value
        self.robot_frame = self.get_parameter('robot_frame').value
        self.blacklist_radius = self.get_parameter('blacklist_radius').value
        self.update_interval = self.get_parameter('update_interval').value
        self.min_goal_distance = self.get_parameter('min_goal_distance').value
        self.goal_offset = self.get_parameter('goal_offset').value
        self.no_progress_timeout = self.get_parameter('no_progress_timeout').value

        # ===================== 状态变量 =====================
        self.current_map = None
        self.is_navigating = False
        self.blacklisted_goals = []
        self.goals_sent = 0
        self.goals_succeeded = 0
        self.exploration_complete = False
        self.current_goal_xy = None
        self.current_goal_handle = None
        self.nav_start_time = None
        self.last_progress_time = None
        self.last_feedback_distance = None

        # ===================== ROS 通信 =====================
        self.map_sub = self.create_subscription(
            OccupancyGrid, '/map', self.map_callback, 10)
        self.nav_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self.marker_pub = self.create_publisher(
            MarkerArray, '/frontier_markers', 10)
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        # 定时器
        self.timer = self.create_timer(self.update_interval, self.exploration_tick)
        self.progress_timer = self.create_timer(2.0, self.check_nav_progress)

        self.get_logger().info('🧭 Frontier Explorer 已启动')
        self.get_logger().info(f'   min_frontier_size={self.min_frontier_size}, '
                               f'goal_offset={self.goal_offset}m, '
                               f'no_progress_timeout={self.no_progress_timeout}s')

    # ===================== 回调 =====================

    def map_callback(self, msg):
        self.current_map = msg

    # ===================== 核心探索循环 =====================

    def exploration_tick(self):
        if self.exploration_complete or self.is_navigating or self.current_map is None:
            return

        frontiers = self.detect_frontiers(self.current_map)

        if not frontiers:
            self.get_logger().info('🎉 没有更多 frontier — 探索完成！')
            self.exploration_complete = True
            self.publish_markers([], None)
            self.print_summary()
            return

        robot_x, robot_y = self.get_robot_position()
        if robot_x is None:
            return

        best = self.select_best_frontier(frontiers, robot_x, robot_y)

        if best is None:
            self.get_logger().info('🎉 所有 frontier 已屏蔽 — 探索完成！')
            self.exploration_complete = True
            self.publish_markers(frontiers, None)
            self.print_summary()
            return

        self.publish_markers(frontiers, best)
        self.send_nav_goal(best[0], best[1])

    # ===================== 导航进度监控 =====================

    def check_nav_progress(self):
        if not self.is_navigating or self.nav_start_time is None:
            return

        now = self.get_clock().now()
        elapsed = (now - self.nav_start_time).nanoseconds / 1e9

        # 前 5 秒不检查（给启动/转弯留时间）
        if elapsed < 5.0:
            return

        if self.last_progress_time is not None:
            since_progress = (now - self.last_progress_time).nanoseconds / 1e9
            if since_progress > self.no_progress_timeout:
                self.get_logger().warn(
                    f'⏱️ 已 {since_progress:.0f}s 无进展，取消当前目标')
                self.cancel_current_goal()

    def cancel_current_goal(self):
        if self.current_goal_handle is not None:
            cancel_future = self.current_goal_handle.cancel_goal_async()
            cancel_future.add_done_callback(self.cancel_done_callback)
        else:
            if self.current_goal_xy:
                self.blacklisted_goals.append(self.current_goal_xy)
            self.is_navigating = False

    def cancel_done_callback(self, future):
        self.get_logger().info('🛑 目标已取消')
        if self.current_goal_xy:
            self.blacklisted_goals.append(self.current_goal_xy)
        self.is_navigating = False
        self.current_goal_handle = None

    # ===================== Frontier 检测 =====================

    def detect_frontiers(self, map_msg):
        info = map_msg.info
        w, h = info.width, info.height
        res = info.resolution
        ox = info.origin.position.x
        oy = info.origin.position.y

        grid = np.array(map_msg.data, dtype=np.int8).reshape(h, w)
        free = (grid == 0)
        unknown = (grid == -1)

        unknown_dilated = binary_dilation(unknown, structure=np.ones((3, 3)))
        frontier_mask = free & unknown_dilated

        labeled, num_clusters = label(frontier_mask)

        frontiers = []
        for i in range(1, num_clusters + 1):
            rows, cols = np.where(labeled == i)
            size = len(rows)
            if size < self.min_frontier_size:
                continue
            cx = ox + np.mean(cols) * res
            cy = oy + np.mean(rows) * res
            frontiers.append((cx, cy, size))

        self.get_logger().info(
            f'🔍 {len(frontiers)} 个 frontier (过滤前 {num_clusters} 个)')
        return frontiers

    # ===================== Frontier 选择 =====================

    def select_best_frontier(self, frontiers, robot_x, robot_y):
        """
        选择最佳 frontier。
        评分 = log2(size) * 2 - distance
        大 frontier（门洞/通道）+ 近距离 → 高分。
        目标点 = frontier 中心向 robot 方向偏移 goal_offset。
        """
        candidates = []
        for fx, fy, size in frontiers:
            if self.is_blacklisted(fx, fy):
                continue
            dist = math.hypot(fx - robot_x, fy - robot_y)
            if dist < self.min_goal_distance:
                continue

            # 目标：从 frontier 向 robot 方向偏移 goal_offset
            dx = robot_x - fx
            dy = robot_y - fy
            norm = math.hypot(dx, dy)
            if norm > 0.01:
                goal_x = fx + (dx / norm) * self.goal_offset
                goal_y = fy + (dy / norm) * self.goal_offset
            else:
                goal_x, goal_y = fx, fy

            # 检查目标到 robot 的距离（防止即到即成功死循环）
            goal_dist = math.hypot(goal_x - robot_x, goal_y - robot_y)
            if goal_dist < 0.35:
                # 目标太近，直接用 frontier 坐标
                goal_x, goal_y = fx, fy
                goal_dist = dist

            score = math.log2(max(size, 2)) * 2.0 - goal_dist
            candidates.append((goal_x, goal_y, fx, fy, size, goal_dist, score))

        if not candidates:
            return None

        candidates.sort(key=lambda c: c[6], reverse=True)
        goal_x, goal_y, fx, fy, size, goal_dist, score = candidates[0]

        self.get_logger().info(
            f'🎯 frontier ({fx:.2f}, {fy:.2f}), '
            f'size={size}, dist={goal_dist:.2f}m, '
            f'score={score:.1f} → goal ({goal_x:.2f}, {goal_y:.2f})')
        return (goal_x, goal_y, size)

    def is_blacklisted(self, x, y):
        for bx, by in self.blacklisted_goals:
            if math.hypot(x - bx, y - by) < self.blacklist_radius:
                return True
        return False

    # ===================== 导航 =====================

    def send_nav_goal(self, x, y):
        if not self.nav_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error('❌ Nav2 未就绪')
            return

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose = PoseStamped()
        goal_msg.pose.header.frame_id = 'map'
        goal_msg.pose.header.stamp = self.get_clock().now().to_msg()
        goal_msg.pose.pose.position.x = x
        goal_msg.pose.pose.position.y = y
        goal_msg.pose.pose.orientation.w = 1.0

        self.is_navigating = True
        self.goals_sent += 1
        self.current_goal_xy = (x, y)
        self.nav_start_time = self.get_clock().now()
        self.last_progress_time = self.get_clock().now()
        self.last_feedback_distance = None

        self.get_logger().info(
            f'🚀 导航 → ({x:.2f}, {y:.2f}) [#{self.goals_sent}]')

        send_future = self.nav_client.send_goal_async(
            goal_msg, feedback_callback=self.nav_feedback_callback)
        send_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn('⚠️ 目标被拒绝')
            self.blacklisted_goals.append(self.current_goal_xy)
            self.is_navigating = False
            return
        self.current_goal_handle = goal_handle
        self.get_logger().info('✅ 目标已接受')
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.nav_result_callback)

    def nav_feedback_callback(self, feedback_msg):
        try:
            remaining = feedback_msg.feedback.distance_remaining
            if self.last_feedback_distance is not None:
                if remaining < self.last_feedback_distance - 0.1:
                    self.last_progress_time = self.get_clock().now()
            self.last_feedback_distance = remaining
        except Exception:
            pass

    def nav_result_callback(self, future):
        status = future.result().status
        if status == 4:  # SUCCEEDED
            self.goals_succeeded += 1
            self.get_logger().info(
                f'✅ 到达！({self.goals_succeeded}/{self.goals_sent})')
        elif status == 6:  # ABORTED
            self.get_logger().warn('⚠️ ABORTED，加入黑名单')
            self.blacklisted_goals.append(self.current_goal_xy)
        elif status == 5:  # CANCELED
            self.get_logger().info('ℹ️ 已取消')
        else:
            self.get_logger().warn(f'⚠️ 状态码: {status}')
            self.blacklisted_goals.append(self.current_goal_xy)
        self.is_navigating = False
        self.current_goal_handle = None

    # ===================== 工具 =====================

    def get_robot_position(self):
        try:
            t = self.tf_buffer.lookup_transform(
                'map', self.robot_frame, rclpy.time.Time(),
                timeout=Duration(seconds=1.0))
            return t.transform.translation.x, t.transform.translation.y
        except Exception as e:
            self.get_logger().warn(f'TF 失败: {e}')
            return None, None

    def print_summary(self):
        self.get_logger().info('=' * 40)
        self.get_logger().info(f'📊 探索完成！发送 {self.goals_sent} 个目标，'
                               f'成功 {self.goals_succeeded}，'
                               f'黑名单 {len(self.blacklisted_goals)}')
        self.get_logger().info('=' * 40)

    # ===================== 可视化 =====================

    def publish_markers(self, frontiers, selected):
        marker_array = MarkerArray()

        clear = Marker()
        clear.header.frame_id = 'map'
        clear.header.stamp = self.get_clock().now().to_msg()
        clear.ns = 'frontiers'
        clear.action = Marker.DELETEALL
        marker_array.markers.append(clear)

        for idx, (fx, fy, size) in enumerate(frontiers):
            m = Marker()
            m.header.frame_id = 'map'
            m.header.stamp = self.get_clock().now().to_msg()
            m.ns = 'frontiers'
            m.id = idx + 1
            m.type = Marker.SPHERE
            m.action = Marker.ADD
            m.pose.position.x = fx
            m.pose.position.y = fy
            m.pose.position.z = 0.3
            m.pose.orientation.w = 1.0
            scale = min(0.2 + size * 0.02, 1.0)
            m.scale.x = scale
            m.scale.y = scale
            m.scale.z = scale
            m.color.r = 0.2
            m.color.g = 1.0
            m.color.b = 0.2
            m.color.a = 0.7
            m.lifetime.sec = 5
            marker_array.markers.append(m)

        if selected:
            m = Marker()
            m.header.frame_id = 'map'
            m.header.stamp = self.get_clock().now().to_msg()
            m.ns = 'frontiers'
            m.id = 9999
            m.type = Marker.SPHERE
            m.action = Marker.ADD
            m.pose.position.x = selected[0]
            m.pose.position.y = selected[1]
            m.pose.position.z = 0.5
            m.pose.orientation.w = 1.0
            m.scale.x = 0.6
            m.scale.y = 0.6
            m.scale.z = 0.6
            m.color.r = 1.0
            m.color.g = 1.0
            m.color.b = 0.0
            m.color.a = 0.9
            m.lifetime.sec = 0
            marker_array.markers.append(m)

        self.marker_pub.publish(marker_array)


def main(args=None):
    rclpy.init(args=args)
    node = FrontierExplorer()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
