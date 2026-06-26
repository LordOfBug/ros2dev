#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R550 自主探索节点 — Frontier Exploration
自动检测 SLAM 地图上的未知边界（frontier），驱动机器人逐步探索，直到完整建图。

用法:
  ros2 launch r550_description r550_explore.launch.py
  或
  ros2 run r550_description frontier_explorer.py
"""

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.duration import Duration
from nav_msgs.msg import OccupancyGrid
from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import PoseStamped
from visualization_msgs.msg import Marker, MarkerArray
import numpy as np
from scipy.ndimage import label
import math
import tf2_ros


class FrontierExplorer(Node):
    def __init__(self):
        super().__init__('frontier_explorer')

        # ===================== 可配置参数 =====================
        self.declare_parameter('min_frontier_size', 5)        # 最小 frontier 像素数（过滤噪声）
        self.declare_parameter('exploration_timeout', 120.0)  # 单次导航超时（秒）
        self.declare_parameter('robot_frame', 'base_footprint')
        self.declare_parameter('blacklist_radius', 0.5)       # 失败目标的屏蔽半径（米）
        self.declare_parameter('update_interval', 2.0)        # 地图分析间隔（秒）
        self.declare_parameter('min_goal_distance', 1.0)      # 忽略距离机器人太近的 frontier（米）
        self.declare_parameter('goal_offset', 0.5)            # 目标点从 frontier 向机器人方向偏移的距离（米）

        self.min_frontier_size = self.get_parameter('min_frontier_size').value
        self.timeout = self.get_parameter('exploration_timeout').value
        self.robot_frame = self.get_parameter('robot_frame').value
        self.blacklist_radius = self.get_parameter('blacklist_radius').value
        self.update_interval = self.get_parameter('update_interval').value
        self.min_goal_distance = self.get_parameter('min_goal_distance').value
        self.goal_offset = self.get_parameter('goal_offset').value

        # ===================== 状态变量 =====================
        self.current_map = None           # 最新地图数据
        self.is_navigating = False        # 是否正在导航中
        self.blacklisted_goals = []       # 失败过的目标位置列表
        self.goals_sent = 0               # 已发送目标数
        self.goals_succeeded = 0          # 成功到达数
        self.exploration_complete = False  # 探索是否完成

        # ===================== ROS 通信 =====================
        # 订阅 SLAM 地图
        self.map_sub = self.create_subscription(
            OccupancyGrid, '/map', self.map_callback, 10)

        # Nav2 导航动作客户端
        self.nav_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')

        # Foxglove 可视化标记
        self.marker_pub = self.create_publisher(
            MarkerArray, '/frontier_markers', 10)

        # TF 用于获取机器人当前位置
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        # 定时器：周期性检查是否需要探索新 frontier
        self.timer = self.create_timer(self.update_interval, self.exploration_tick)

        self.get_logger().info('🧭 Frontier Explorer 自主探索节点已启动！')
        self.get_logger().info(f'   最小 frontier 大小: {self.min_frontier_size} cells')
        self.get_logger().info(f'   单次导航超时: {self.timeout}s')
        self.get_logger().info(f'   失败屏蔽半径: {self.blacklist_radius}m')

    # ===================== 地图回调 =====================

    def map_callback(self, msg):
        """缓存最新 SLAM 地图"""
        self.current_map = msg

    # ===================== 核心探索循环 =====================

    def exploration_tick(self):
        """定时器触发：如果当前空闲，分析地图并发起新探索"""
        if self.exploration_complete or self.is_navigating or self.current_map is None:
            return

        # 1. 从地图中提取 frontier
        frontiers = self.detect_frontiers(self.current_map)

        if not frontiers:
            self.get_logger().info('🎉 没有更多 frontier 了 — 探索完成！')
            self.exploration_complete = True
            self.publish_markers([], None)  # 清除可视化
            self.print_summary()
            return

        # 2. 获取机器人当前位置
        robot_x, robot_y = self.get_robot_position()
        if robot_x is None:
            self.get_logger().warn('⚠️ 无法获取机器人位置，跳过本轮')
            return

        # 3. 选择最佳 frontier（最近的、且不在黑名单中的）
        best = self.select_best_frontier(frontiers, robot_x, robot_y)

        if best is None:
            self.get_logger().info('🎉 所有可达 frontier 已探索或被屏蔽 — 探索完成！')
            self.exploration_complete = True
            self.publish_markers(frontiers, None)
            self.print_summary()
            return

        # 4. 可视化：标记所有 frontier 和选中目标
        self.publish_markers(frontiers, best)

        # 5. 发送导航目标
        self.send_nav_goal(best[0], best[1])

    # ===================== Frontier 检测 =====================

    def detect_frontiers(self, map_msg):
        """
        从 OccupancyGrid 中检测 frontier cells。
        Frontier = free cell (0) 且至少有一个 unknown neighbor (-1)
        """
        info = map_msg.info
        w, h = info.width, info.height
        res = info.resolution
        ox = info.origin.position.x
        oy = info.origin.position.y

        # 将地图数据转为 2D 数组
        grid = np.array(map_msg.data, dtype=np.int8).reshape(h, w)

        # free cells = 0, unknown = -1
        free = (grid == 0)
        unknown = (grid == -1)

        # 找到与 unknown 相邻的 free cell = frontier
        # 使用 4-邻域扩展 unknown 区域，然后与 free 取交集
        from scipy.ndimage import binary_dilation
        unknown_dilated = binary_dilation(unknown, structure=np.ones((3, 3)))
        frontier_mask = free & unknown_dilated

        # 聚类：将相邻的 frontier cell 分组
        labeled, num_clusters = label(frontier_mask)

        frontiers = []
        for i in range(1, num_clusters + 1):
            rows, cols = np.where(labeled == i)
            size = len(rows)

            # 过滤太小的 cluster（噪声）
            if size < self.min_frontier_size:
                continue

            # 计算 cluster 中心的世界坐标
            cx = ox + np.mean(cols) * res
            cy = oy + np.mean(rows) * res
            frontiers.append((cx, cy, size))

        self.get_logger().info(
            f'🔍 检测到 {len(frontiers)} 个有效 frontier '
            f'(过滤前 {num_clusters} 个 cluster)')

        return frontiers

    # ===================== Frontier 选择 =====================

    def select_best_frontier(self, frontiers, robot_x, robot_y):
        """选择最佳 frontier：过滤太近/黑名单的，然后按距离优先（大小加分）"""
        candidates = []
        for fx, fy, size in frontiers:
            # 检查是否在黑名单中
            if self.is_blacklisted(fx, fy):
                continue
            dist = math.hypot(fx - robot_x, fy - robot_y)
            # 跳过距离太近的 frontier（DWB 在极短距离内容易失败）
            if dist < self.min_goal_distance:
                continue
            candidates.append((fx, fy, size, dist))

        if not candidates:
            return None

        # 按距离排序（最近优先）
        candidates.sort(key=lambda c: c[3])

        best_fx, best_fy, best_size, best_dist = candidates[0]

        # 将目标点从 frontier 边界向机器人方向偏移 goal_offset 米
        # 这样目标落在已知自由空间内，避免落在 unknown/obstacle 边界上
        dx = robot_x - best_fx
        dy = robot_y - best_fy
        norm = math.hypot(dx, dy)
        if norm > 0.01:  # 防除零
            goal_x = best_fx + (dx / norm) * self.goal_offset
            goal_y = best_fy + (dy / norm) * self.goal_offset
        else:
            goal_x, goal_y = best_fx, best_fy

        self.get_logger().info(
            f'🎯 选择 frontier: ({best_fx:.2f}, {best_fy:.2f}), '
            f'大小={best_size} cells, 距离={best_dist:.2f}m → '
            f'偏移后目标: ({goal_x:.2f}, {goal_y:.2f})')
        return (goal_x, goal_y, best_size)

    def is_blacklisted(self, x, y):
        """检查坐标是否在失败黑名单内"""
        for bx, by in self.blacklisted_goals:
            if math.hypot(x - bx, y - by) < self.blacklist_radius:
                return True
        return False

    # ===================== 导航控制 =====================

    def send_nav_goal(self, x, y):
        """发送 Nav2 NavigateToPose 目标"""
        if not self.nav_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error('❌ Nav2 导航服务未就绪！')
            return

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose = PoseStamped()
        goal_msg.pose.header.frame_id = 'map'
        goal_msg.pose.header.stamp = self.get_clock().now().to_msg()
        goal_msg.pose.pose.position.x = x
        goal_msg.pose.pose.position.y = y
        goal_msg.pose.pose.orientation.w = 1.0  # 朝向无所谓

        self.is_navigating = True
        self.goals_sent += 1
        self.current_goal_xy = (x, y)

        self.get_logger().info(f'🚀 导航出发 → ({x:.2f}, {y:.2f}) [第 {self.goals_sent} 个目标]')

        send_future = self.nav_client.send_goal_async(
            goal_msg, feedback_callback=self.nav_feedback_callback)
        send_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        """Nav2 是否接受了目标"""
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn('⚠️ Nav2 拒绝了目标，加入黑名单')
            self.blacklisted_goals.append(self.current_goal_xy)
            self.is_navigating = False
            return

        self.get_logger().info('✅ Nav2 已接受目标，正在导航...')
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.nav_result_callback)

    def nav_feedback_callback(self, feedback_msg):
        """导航过程中的实时反馈（可选：打印剩余距离）"""
        pass  # 保持安静，避免刷屏

    def nav_result_callback(self, future):
        """导航完成后的回调"""
        result = future.result()
        status = result.status

        if status == 4:  # SUCCEEDED
            self.goals_succeeded += 1
            self.get_logger().info(
                f'✅ 到达目标！({self.goals_succeeded}/{self.goals_sent} 成功)')
        elif status == 6:  # ABORTED
            self.get_logger().warn('⚠️ 导航失败（ABORTED），将目标加入黑名单')
            self.blacklisted_goals.append(self.current_goal_xy)
        elif status == 5:  # CANCELED
            self.get_logger().info('ℹ️ 导航被取消')
        else:
            self.get_logger().warn(f'⚠️ 导航结束，状态码: {status}')
            self.blacklisted_goals.append(self.current_goal_xy)

        self.is_navigating = False

    # ===================== 工具方法 =====================

    def get_robot_position(self):
        """通过 TF 获取机器人在 map 坐标系中的位置"""
        try:
            transform = self.tf_buffer.lookup_transform(
                'map', self.robot_frame, rclpy.time.Time(),
                timeout=Duration(seconds=1.0))
            x = transform.transform.translation.x
            y = transform.transform.translation.y
            return x, y
        except Exception as e:
            self.get_logger().warn(f'TF 查询失败: {e}')
            return None, None

    def print_summary(self):
        """打印探索总结"""
        self.get_logger().info('=' * 50)
        self.get_logger().info('📊 自主探索完成！')
        self.get_logger().info(f'   发送目标数: {self.goals_sent}')
        self.get_logger().info(f'   成功到达数: {self.goals_succeeded}')
        self.get_logger().info(f'   黑名单数量: {len(self.blacklisted_goals)}')
        self.get_logger().info('   💾 请手动保存地图:')
        self.get_logger().info('   ros2 run nav2_map_server map_saver_cli -f maps/explored_map')
        self.get_logger().info('=' * 50)

    # ===================== Foxglove 可视化 =====================

    def publish_markers(self, frontiers, selected):
        """
        发布 frontier 可视化标记到 Foxglove：
        - 绿色球体 = 可选 frontier
        - 黄色大球 = 当前选中的目标
        """
        marker_array = MarkerArray()

        # 先清除旧标记
        clear_marker = Marker()
        clear_marker.header.frame_id = 'map'
        clear_marker.header.stamp = self.get_clock().now().to_msg()
        clear_marker.ns = 'frontiers'
        clear_marker.action = Marker.DELETEALL
        marker_array.markers.append(clear_marker)

        # 绿色球体标记所有 frontier
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
            # 大小根据 frontier 规模缩放
            scale = min(0.2 + size * 0.02, 1.0)
            m.scale.x = scale
            m.scale.y = scale
            m.scale.z = scale
            m.color.r = 0.2
            m.color.g = 1.0
            m.color.b = 0.2
            m.color.a = 0.7
            m.lifetime.sec = 5  # 5 秒后自动消失
            marker_array.markers.append(m)

        # 黄色大球标记选中的目标
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
            m.lifetime.sec = 0  # 永久直到下次更新
            marker_array.markers.append(m)

        self.marker_pub.publish(marker_array)


def main(args=None):
    rclpy.init(args=args)
    node = FrontierExplorer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
