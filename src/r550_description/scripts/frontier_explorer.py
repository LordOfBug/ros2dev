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
from geometry_msgs.msg import PoseStamped, Twist
from visualization_msgs.msg import Marker, MarkerArray
import numpy as np
from scipy.ndimage import label, binary_dilation
import math
import tf2_ros


class FrontierExplorer(Node):
    def __init__(self):
        super().__init__('frontier_explorer')

        # ===================== 可配置参数 =====================
        self.declare_parameter('min_frontier_size', 15)
        self.declare_parameter('robot_frame', 'base_footprint')
        self.declare_parameter('blacklist_radius', 0.5)        # 失败屏蔽半径（缩小以避免过度封锁）
        self.declare_parameter('update_interval', 2.0)
        self.declare_parameter('min_goal_distance', 0.5)      # 忽略太近的 frontier
        self.declare_parameter('goal_offset', 0.3)             # 目标点偏移量（从 frontier 向 robot 方向）
        self.declare_parameter('no_progress_timeout', 25.0)    # 无进展超时

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
        self.original_goal_xy = None
        self.current_goal_handle = None
        self.nav_start_time = None
        self.last_progress_time = None
        self.last_feedback_distance = None
        self.last_success_xy = None          # 上次成功到达的位置（用于就近探索）
        self.current_frontier_xy = None      # 当前导航对应的 frontier 中心
        self.retry_count = 0                 # 当前 frontier 重试次数
        self.current_goal_dir_yaw = None     # 当前导航目标的初始航向角（用于运动中重规划的方向约束）
        self.last_robot_xy = None            # 上次记录的机器人坐标 (用于卡死检测)
        self.last_robot_yaw = None           # 上次记录的机器人朝向 (用于旋转卡阻检测)
        self.stuck_ticks = 0                 # 连续未移动的 tick 次数
        self.last_preempt_time = None        # 上次动态抢占切换目标的时间（用于冷却限制）
        self.is_backing_up = False           # 是否正在进行后退脱困动作
        self.backup_ticks_remaining = 0      # 剩余后退 tick 数 (10Hz)
        self.just_recovered = False          # 刚从卡阻后退恢复（下次选目标时优先选朝向一致的）
        self.startup_clearance_done = False   # 启动时是否已完成前方间隙检查

        # ===================== ROS 通信 =====================
        self.map_sub = self.create_subscription(
            OccupancyGrid, '/map', self.map_callback, 10)
        self.nav_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self.marker_pub = self.create_publisher(
            MarkerArray, '/frontier_markers', 10)
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)

        # 定时器
        self.timer = self.create_timer(self.update_interval, self.exploration_tick)
        self.backup_timer = self.create_timer(0.1, self.backup_tick)

        self.get_logger().info('🧭 Frontier Explorer 已启动')
        self.get_logger().info(f'   min_frontier_size={self.min_frontier_size}, '
                               f'goal_offset={self.goal_offset}m, '
                               f'no_progress_timeout={self.no_progress_timeout}s')

    # ===================== 回调 =====================

    def map_callback(self, msg):
        self.current_map = msg

    def exploration_tick(self):
        if self.exploration_complete or self.current_map is None:
            return

        if self.is_backing_up:
            return

        robot_x, robot_y, robot_yaw = self.get_robot_position()
        if robot_x is None:
            return

        # ===================== 启动前间隙检查 =====================
        # 仅在首次发送目标前执行一次：如果车头正前方有墙/障碍物 (< 0.25m)，
        # 先主动后退创建转向空间，确保左手法则扫描到侧向目标后机器人能安全旋转。
        if not self.startup_clearance_done and self.goals_sent == 0:
            self.startup_clearance_done = True
            if self.current_map is not None and robot_yaw is not None:
                info = self.current_map.info
                grid = np.array(self.current_map.data, dtype=np.int8).reshape(info.height, info.width)
                front_blocked = False
                for check_dist in [0.15, 0.20, 0.25]:
                    check_x = robot_x + check_dist * math.cos(robot_yaw)
                    check_y = robot_y + check_dist * math.sin(robot_yaw)
                    col = int((check_x - info.origin.position.x) / info.resolution)
                    row = int((check_y - info.origin.position.y) / info.resolution)
                    if 0 <= col < info.width and 0 <= row < info.height:
                        if self.has_obstacles_nearby(row, col, grid, info.width, info.height, radius=2):
                            front_blocked = True
                            self.get_logger().warn(
                                f'🔙 启动间隙检查: 车头前方 {check_dist:.2f}m 处检测到障碍物，先后退创建转向空间')
                            break
                if front_blocked:
                    self.is_backing_up = True
                    self.backup_ticks_remaining = 15  # 1.5 秒后退
                    self.just_recovered = True  # 后退完成后优先选车头方向的目标
                    return
                else:
                    self.get_logger().info('✅ 启动间隙检查: 车头前方空间充足，无需后退')

        # 如果正在导航，检查进度并支持运动中重新规划
        if self.is_navigating:
            self.check_nav_progress()
            
            # 【核心：运动中动态重新规划目标】
            # 在距离旧目标较近 (例如 < 1.2m 且 > 0.3m)，且非重试状态下，执行动态替换目标，实现平滑转向
            if self.retry_count == 0 and self.last_feedback_distance is not None:
                # 检查平滑抢占冷却时间（至少间隔 8.0s），防止频繁在拐角处连续切换目标导致打滑/撞墙
                can_preempt = True
                elapsed_since_preempt = 999.0
                if self.last_preempt_time is not None:
                    elapsed_since_preempt = (self.get_clock().now() - self.last_preempt_time).nanoseconds / 1e9
                    if elapsed_since_preempt < 8.0:
                        can_preempt = False

                if 0.3 < self.last_feedback_distance < 1.2:
                    if not can_preempt:
                        self.get_logger().info(
                            f'⏳ 动态切换冷却中（上次切换后已过 {elapsed_since_preempt:.1f}s，冷却限制 8.0s），跳过本轮抢占。')
                    else:
                        self.get_logger().info(
                            f'🔄 满足触发重新规划距离条件（剩余距离: {self.last_feedback_distance:.2f}m），开始运动中重新规划...')
                        frontiers = self.detect_frontiers(self.current_map)
                        if frontiers:
                            best = self.select_best_frontier(frontiers, robot_x, robot_y, robot_yaw)
                            if best is not None:
                                new_goal_x, new_goal_y, _ = best
                                # 只有当新计算出的目标点与当前执行的目标点距离有明显差距 (如 > 0.6m) 时才抢占，防止微小跳动
                                dx = new_goal_x - self.current_goal_xy[0]
                                dy = new_goal_y - self.current_goal_xy[1]
                                dist_diff = math.hypot(dx, dy)
                                if dist_diff > 0.6:
                                    self.get_logger().info(
                                        f'🔄 运动中动态平滑切换目标！新旧目标距离差距 {dist_diff:.2f}m > 0.6m，发送新目标：({new_goal_x:.2f}, {new_goal_y:.2f})')
                                    self.publish_markers(frontiers, best)
                                    self.send_nav_goal(new_goal_x, new_goal_y)
                                else:
                                    self.get_logger().info(
                                        f'⏭️ 新旧目标距离差距 {dist_diff:.2f}m <= 0.6m，为防抖动不进行切换。')
            return

        # 如果有待重试的 frontier（重试次数为 1）
        if self.retry_count == 1 and self.current_frontier_xy is not None:
            fx, fy = self.current_frontier_xy
            dx = fx - robot_x
            dy = fy - robot_y
            norm = math.hypot(dx, dy)
            if norm > 0.1:
                perp_x = -dy / norm
                perp_y = dx / norm
                offset_x = fx + perp_x * 1.0
                offset_y = fy + perp_y * 1.0
                self.retry_count = 2  # 标记已进行过重试
                self.get_logger().info(f'🔄 触发重试：垂直偏移至 ({offset_x:.2f}, {offset_y:.2f})')
                self.send_nav_goal(offset_x, offset_y)
                return
            else:
                self.retry_count = 0  # 无法计算偏移，直接寻找新 frontier

        frontiers = self.detect_frontiers(self.current_map)

        if not frontiers:
            self.get_logger().info('🎉 没有更多 frontier — 探索完成！')
            self.exploration_complete = True
            self.publish_markers([], None)
            self.print_summary()
            return

        best = self.select_best_frontier(frontiers, robot_x, robot_y, robot_yaw)

        if best is None:
            self.get_logger().info('🎉 所有 frontier 已屏蔽 — 探索完成！')
            self.exploration_complete = True
            self.publish_markers(frontiers, None)
            self.print_summary()
            return

        self.publish_markers(frontiers, best)
        self.retry_count = 0  # 正常选择新目标，重置重试计数
        self.send_nav_goal(best[0], best[1])

    def backup_tick(self):
        if self.is_backing_up and self.backup_ticks_remaining > 0:
            msg = Twist()
            msg.linear.x = -0.1  # 后退速度
            msg.angular.z = 0.2  # 增加微小的旋转，使后退轨迹呈弧线，利于在贴墙/滑移时摆脱摩擦锁死
            self.cmd_vel_pub.publish(msg)
            self.backup_ticks_remaining -= 1
            if self.backup_ticks_remaining == 0:
                # 停止小车
                stop_msg = Twist()
                self.cmd_vel_pub.publish(stop_msg)
                self.is_backing_up = False
                self.just_recovered = True  # 标记刚恢复，下次选目标时优先选朝向一致的
                self.get_logger().info('✅ 后退脱困完成，机器人已安全拉开距离，恢复探索流程。')

    # ===================== 导航进度监控 =====================

    def check_nav_progress(self):
        if not self.is_navigating or self.nav_start_time is None:
            return

        robot_x, robot_y, robot_yaw = self.get_robot_position()
        if robot_x is None:
            return

        now = self.get_clock().now()
        elapsed = (now - self.nav_start_time).nanoseconds / 1e9

        # 前 5 秒不检查进度/受阻（给小车旋转和启动时间）
        if elapsed < 5.0:
            self.last_robot_xy = (robot_x, robot_y)
            self.last_robot_yaw = robot_yaw
            self.stuck_ticks = 0
            return

        # 检查是否物理卡住
        if self.last_robot_xy is not None and self.last_robot_yaw is not None:
            dist_moved = math.hypot(robot_x - self.last_robot_xy[0], robot_y - self.last_robot_xy[1])
            
            # 计算角度变化量并处理回绕
            yaw_diff = abs(robot_yaw - self.last_robot_yaw)
            if yaw_diff > math.pi:
                yaw_diff = 2 * math.pi - yaw_diff
                
            # 只有当位移 and 旋转都很小时，才认为卡阻并增加 stuck_ticks
            if dist_moved < 0.01 and yaw_diff < 0.08:
                self.stuck_ticks += 1
                self.get_logger().warn(
                    f'⚠️ 物理卡阻检测: 机器人几乎无位移和旋转 (移动 {dist_moved:.3f}m < 0.01m, 旋转 {yaw_diff:.3f}rad < 0.08rad)，stuck_ticks 增加至 {self.stuck_ticks}')
            else:
                if self.stuck_ticks > 0:
                    self.get_logger().info(
                        f'✅ 物理卡阻检测: 检测到明显运动 (移动 {dist_moved:.3f}m, 旋转 {yaw_diff:.3f}rad)，stuck_ticks 重置为 0')
                self.stuck_ticks = 0
                self.last_progress_time = now
        else:
            self.stuck_ticks = 0

        self.last_robot_xy = (robot_x, robot_y)
        self.last_robot_yaw = robot_yaw

        # 连续 3 次 tick (约 6 秒) 没有发生位移，且车头前方有障碍物，判定为受阻/撞墙
        if self.stuck_ticks >= 3:
            if self.current_map is not None:
                info = self.current_map.info
                grid = np.array(self.current_map.data, dtype=np.int8).reshape(info.height, info.width)
                
                # 检查车头前方 0.15m 至 0.35m 的区间是否有障碍物 (100)
                is_blocked = False
                blocked_dist = None
                for dist in [0.15, 0.25, 0.35]:
                    front_x = robot_x + dist * math.cos(robot_yaw)
                    front_y = robot_y + dist * math.sin(robot_yaw)
                    
                    col = int((front_x - info.origin.position.x) / info.resolution)
                    row = int((front_y - info.origin.position.y) / info.resolution)
                    
                    if 1 <= col < info.width - 1 and 1 <= row < info.height - 1:
                        sub = grid[row-1:row+2, col-1:col+2]
                        if np.any(sub == 100):
                            is_blocked = True
                            blocked_dist = dist
                            break
                
                if is_blocked:
                    self.get_logger().warn(f'🚨 判定受阻！连续未移动 tick={self.stuck_ticks} 且车头前方 {blocked_dist}m 处检测到墙体/障碍物。执行后退避障并加入黑名单。')
                    if self.current_goal_xy is not None:
                        self.blacklisted_goals.append(self.current_goal_xy)
                        if self.original_goal_xy is not None:
                            self.blacklisted_goals.append(self.original_goal_xy)
                    # 将机器人当前位置也加入黑名单，防止在原地继续规划附近的点
                    self.blacklisted_goals.append((robot_x, robot_y))
                    self.stuck_ticks = 0
                    self.retry_count = 2  # 设为 2 以跳过 retry_count == 0 时的垂直偏移重试阶段
                    self.cancel_current_goal()
                    
                    # 触发 1.5 秒 (15 ticks @ 10Hz) 的主动后退动作
                    self.is_backing_up = True
                    self.backup_ticks_remaining = 15
                    return
                elif self.stuck_ticks >= 5:
                    self.get_logger().warn(f'🚨 判定卡阻（超时）！连续未移动 tick={self.stuck_ticks}，车头虽无明显障碍物，但可能侧面/后面卡住或打滑。执行后退避障并加入黑名单。')
                    if self.current_goal_xy is not None:
                        self.blacklisted_goals.append(self.current_goal_xy)
                        if self.original_goal_xy is not None:
                            self.blacklisted_goals.append(self.original_goal_xy)
                    # 将机器人当前位置也加入黑名单，防止在原地继续规划附近的点
                    self.blacklisted_goals.append((robot_x, robot_y))
                    self.stuck_ticks = 0
                    self.retry_count = 2
                    self.cancel_current_goal()
                    
                    # 触发 1.5 秒 (15 ticks @ 10Hz) 的主动后退动作
                    self.is_backing_up = True
                    self.backup_ticks_remaining = 15
                    return
                else:
                    self.get_logger().info(f'ℹ️ 物理位移不足 (tick={self.stuck_ticks})，但车头前方无障碍物，继续等待。')

        # 正常进度超时检测（如果小车虽然在移动，但 25 秒内没有接近目标，说明陷入死胡同/打滑）
        if self.last_progress_time is not None:
            since_progress = (now - self.last_progress_time).nanoseconds / 1e9
            if since_progress > self.no_progress_timeout:
                self.get_logger().warn(
                    f'⏱️ 已 {since_progress:.0f}s 无进展，取消当前目标')
                self.cancel_current_goal()

    def cancel_current_goal(self):
        self.is_navigating = False
        if self.current_goal_handle is not None:
            self.current_goal_handle.cancel_goal_async()
        else:
            if self.current_goal_xy:
                self.blacklisted_goals.append(self.current_goal_xy)
                if self.original_goal_xy is not None:
                    self.blacklisted_goals.append(self.original_goal_xy)
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

    def select_best_frontier(self, frontiers, robot_x, robot_y, robot_yaw):
        """
        选择最佳 frontier。
        评分 = log2(size) * 2 - distance + heading_bonus + nearby_boost
        大 frontier + 近距离 → 高分。
        如果刚到达过一个目标，优先探索 3m 内 the frontier（就近完成当前区域）。
        """
        if self.current_map is None:
            self.get_logger().warn('⚠️ select_best_frontier: 地图数据为空！')
            return None

        info = self.current_map.info
        w, h = info.width, info.height
        res = info.resolution
        ox = info.origin.position.x
        oy = info.origin.position.y
        grid = np.array(self.current_map.data, dtype=np.int8).reshape(h, w)

        # 如果我们正在导航（且非重试阶段），我们处于运动中重规划状态
        # 此时需要限制候选 frontier 的方向，防止折返/转弯导致 ping-pong 震荡
        is_preempting = self.is_navigating and self.retry_count == 0

        self.get_logger().info(f'🔎 规划开始: 共有 {len(frontiers)} 个待筛选的 frontiers (机器人位置: {robot_x:.2f}, {robot_y:.2f})')

        candidates = []
        for idx, (fx, fy, size) in enumerate(frontiers):
            f_prefix = f'  [Frontier #{idx} ({fx:.2f}, {fy:.2f}, 规模:{size})]'
            
            # 1. 运动中重规划方向约束：新目标方向必须与当前导航方向基本一致 (夹角在 45 度内)
            if is_preempting and self.current_goal_dir_yaw is not None:
                frontier_yaw = math.atan2(fy - robot_y, fx - robot_x)
                diff_yaw = abs(math.atan2(math.sin(frontier_yaw - self.current_goal_dir_yaw),
                                          math.cos(frontier_yaw - self.current_goal_dir_yaw)))
                if diff_yaw > (math.pi / 4.0):  # 45度角限制
                    self.get_logger().info(f'{f_prefix} 过滤: 偏角 {math.degrees(diff_yaw):.1f}° 超过 45° 运动中重规划约束')
                    continue

            # 2. 投影出安全的 free_space 目标点
            safe_goal = self.get_safe_projected_goal(fx, fy, robot_x, robot_y, robot_yaw, grid, info)
            if safe_goal is None:
                self.get_logger().info(f'{f_prefix} 过滤: 无法在该 frontier 附近投影出安全的自由空间目标点')
                continue
            goal_x, goal_y = safe_goal

            # 3. 基于最终投影后的目标点检查黑名单（防止重复失败的目标再次被选中）
            if self.is_blacklisted(goal_x, goal_y):
                self.get_logger().info(f'{f_prefix} 过滤: 投影目标点 ({goal_x:.2f}, {goal_y:.2f}) 在黑名单中')
                continue

            # 4. 检查目标到 robot 的距离（防止即到即成功死循环 / 小幅抖动）
            goal_dist = math.hypot(goal_x - robot_x, goal_y - robot_y)
            if goal_dist < self.min_goal_distance or goal_dist < 0.35:
                self.get_logger().info(f'{f_prefix} 过滤: 投影目标点距离过近 ({goal_dist:.2f}m，最小限制: {max(self.min_goal_distance, 0.35):.2f}m)')
                continue

            # 基础分 (大小与距离)
            base_score = math.log2(max(size, 2)) * 2.0 - goal_dist
            score = base_score
            heading_bonus = 0.0
            nearby_boost = False

            # 朝向加分（如果目标在当前前进方向上，给予额外加分以减少原地转向）
            if robot_yaw is not None:
                frontier_yaw = math.atan2(fy - robot_y, fx - robot_x)
                diff_yaw = abs(math.atan2(math.sin(frontier_yaw - robot_yaw), math.cos(frontier_yaw - robot_yaw)))
                heading_factor = math.cos(diff_yaw)
                if heading_factor > 0.0:
                    # 刚从卡阻恢复时，大幅提升朝向权重（20分），避免选需要大转弯的目标导致贴墙再次卡死
                    bonus_weight = 20.0 if self.just_recovered else 4.0
                    heading_bonus = bonus_weight * heading_factor
                    score += heading_bonus
                elif self.just_recovered:
                    # 刚恢复且目标在身后 → 重罚，防止选需要 180° 转弯的目标
                    score -= 15.0

            # 就近探索加分：如果上次成功到达某处，3m 内的 frontier 得 50% 加分
            if self.last_success_xy is not None:
                dist_to_last = math.hypot(
                    fx - self.last_success_xy[0],
                    fy - self.last_success_xy[1])
                if dist_to_last < 3.0:
                    score *= 1.5
                    nearby_boost = True

            self.get_logger().info(
                f'{f_prefix} 候选: 投影至 ({goal_x:.2f}, {goal_y:.2f}), 距车 {goal_dist:.2f}m, '
                f'得分 {score:.2f} (基础 {base_score:.2f} + 朝向 {heading_bonus:.2f}'
                f'{ " + 就近 1.5x" if nearby_boost else "" })'
            )
            candidates.append((goal_x, goal_y, fx, fy, size, goal_dist, score))

        if not candidates:
            self.get_logger().warn('⚠️ 规划结束: 无可用 candidate frontiers！')
            self.just_recovered = False
            return None

        candidates.sort(key=lambda c: c[6], reverse=True)
        goal_x, goal_y, fx, fy, size, goal_dist, score = candidates[0]

        self.get_logger().info(
            f'🎯 规划胜出: frontier ({fx:.2f}, {fy:.2f}) 规模={size}, 距离={goal_dist:.2f}m, '
            f'最高分={score:.2f} → 最终目标点 ({goal_x:.2f}, {goal_y:.2f})'
            f'{" [恢复模式: 优先朝向]" if self.just_recovered else ""}')
        self.current_frontier_xy = (fx, fy)  # 记住 frontier 中心用于重试
        self.just_recovered = False  # 重置恢复标记
        return (goal_x, goal_y, size)

    def get_safe_projected_goal(self, fx, fy, robot_x, robot_y, robot_yaw, grid, info):
        w, h = info.width, info.height
        res = info.resolution
        ox = info.origin.position.x
        oy = info.origin.position.y

        # 计算机器人到 frontier centroid 的距离
        dx = robot_x - fx
        dy = robot_y - fy
        dist = math.hypot(dx, dy)

        allow_unknown = True

        # 如果距离过近 (说明 frontier 环绕着机器人，例如初始状态)
        # 此时我们无法沿质心射线朝机器人方向投影（距离极短），
        # 采用"左手法则"(Left-Hand Rule)：从车头正前方开始，以固定逆时针方向（左转）
        # 每次偏转 30° 扫描，优先选择车头前方，然后依次向左旋转寻找安全目标。
        # 这保证了在对称/环形空间中始终以固定旋转方向打破僵局，类似迷宫探索中的左手法则。
        if dist < 0.35:
            yaw = robot_yaw if robot_yaw is not None else 0.0
            sweep_step = math.radians(30)  # 每步 30°
            sweep_count = 12               # 360° / 30° = 12 步，覆盖完整一圈
            self.get_logger().info(f'🔄 左手法则启动: frontier ({fx:.2f}, {fy:.2f}) 距车仅 {dist:.2f}m，从车头朝向 {math.degrees(yaw):.0f}° 开始逆时针扫描')
            for i in range(sweep_count):
                target_angle = yaw + i * sweep_step  # 逆时针扫描 (0°, +30°, +60°, ... +330°)
                tx = robot_x + 1.0 * math.cos(target_angle)
                ty = robot_y + 1.0 * math.sin(target_angle)

                col = int((tx - ox) / res)
                row = int((ty - oy) / res)

                if 0 <= col < w and 0 <= row < h:
                    cell_val = grid[row, col]
                    if cell_val == 0:
                        if self.is_cell_safe(row, col, grid, w, h, radius=5, allow_unknown=allow_unknown):
                            self.get_logger().info(f'  ✅ 左手法则: 偏转 {i*30}° → ({tx:.2f}, {ty:.2f}) 安全可达')
                            return tx, ty
                        else:
                            self.get_logger().info(f'  ❌ 左手法则: 偏转 {i*30}° → ({tx:.2f}, {ty:.2f}) free但周围不安全')
                    else:
                        self.get_logger().info(f'  ❌ 左手法则: 偏转 {i*30}° → ({tx:.2f}, {ty:.2f}) 非free区 (值={cell_val})')
                else:
                    self.get_logger().info(f'  ❌ 左手法则: 偏转 {i*30}° → ({tx:.2f}, {ty:.2f}) 超出地图边界')
            self.get_logger().warn(f'  ⚠️ 左手法则: 360° 扫描完毕，未找到安全目标')
            return None

        # 从 frontier 向 robot 方向画射线

        # 将 frontier 世界坐标转为网格坐标
        f_col = int((fx - ox) / res)
        f_row = int((fy - oy) / res)

        # 检查 frontier 周围 0.8m (16像素) 内是否有障碍物 (100)
        has_walls = False
        if 0 <= f_col < w and 0 <= f_row < h:
            has_walls = self.has_obstacles_nearby(f_row, f_col, grid, w, h, radius=16)

        # 开阔未知区域：目标点可直接设在 frontier 边缘 (0.0m) 且安全区可包含未知元素 (-1)
        # 靠近障碍物区域：目标点保守回退 (0.3m)，安全区必须全是已知 free (0)，但我们现在总是 allow_unknown=True
        # 以防启动时因为四周是未知区域导致无法定位目标点
        if not has_walls:
            min_offset = 0.0
        else:
            min_offset = self.goal_offset
        allow_unknown = True

        # 在 range(min_offset, 1.5m) 之间以 0.05m 步长寻找满足安全条件的点
        step_size = 0.05
        max_offset = 1.5
        steps = int((max_offset - min_offset) / step_size) + 1

        for step in range(steps):
            offset = min_offset + step * step_size
            if offset > dist - 0.35:
                break
            tx = fx + (dx / dist) * offset
            ty = fy + (dy / dist) * offset

            col = int((tx - ox) / res)
            row = int((ty - oy) / res)

            if 0 <= col < w and 0 <= row < h:
                # 目标点本身必须是已探索 of the free area (0)
                if grid[row, col] == 0:
                    if self.is_cell_safe(row, col, grid, w, h, radius=5, allow_unknown=allow_unknown):
                        return tx, ty
        return None

    def has_obstacles_nearby(self, center_row, center_col, grid, w, h, radius):
        r_start = max(0, center_row - radius)
        r_end = min(h, center_row + radius + 1)
        c_start = max(0, center_col - radius)
        c_end = min(w, center_col + radius + 1)
        subgrid = grid[r_start:r_end, c_start:c_end]
        return np.any(subgrid == 100)

    def is_cell_safe(self, center_row, center_col, grid, w, h, radius, allow_unknown=False):
        r_start = max(0, center_row - radius)
        r_end = min(h, center_row + radius + 1)
        c_start = max(0, center_col - radius)
        c_end = min(w, center_col + radius + 1)

        subgrid = grid[r_start:r_end, c_start:c_end]
        if np.any(subgrid == 100):
            return False
        if not allow_unknown and np.any(subgrid == -1):
            return False
        return True

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
        if self.retry_count == 0:
            self.original_goal_xy = (x, y)
        self.nav_start_time = self.get_clock().now()
        self.last_progress_time = self.get_clock().now()
        self.last_feedback_distance = None
        self.last_robot_xy = None
        self.last_robot_yaw = None
        self.stuck_ticks = 0
        self.last_preempt_time = self.get_clock().now()

        # 计算并保存当前导航目标的初始航向角（用于运动中重规划方向约束）
        robot_x, robot_y, _ = self.get_robot_position()
        if robot_x is not None:
            self.current_goal_dir_yaw = math.atan2(y - robot_y, x - robot_x)
            src_str = f"自 ({robot_x:.2f}, {robot_y:.2f})"
        else:
            self.current_goal_dir_yaw = None
            src_str = "自未知位置"

        self.get_logger().info(
            f'🚀 导航 → ({x:.2f}, {y:.2f}) [#{self.goals_sent}] {src_str}')

        send_future = self.nav_client.send_goal_async(
            goal_msg, feedback_callback=self.nav_feedback_callback)
        send_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn('⚠️ 目标被拒绝')
            self.blacklisted_goals.append(self.current_goal_xy)
            if self.original_goal_xy is not None:
                self.blacklisted_goals.append(self.original_goal_xy)
            self.is_navigating = False
            self.retry_count = 0
            return
        self.current_goal_handle = goal_handle
        self.get_logger().info('✅ 目标已接受')
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(
            lambda fut: self.nav_result_callback(fut, goal_handle))

    def nav_feedback_callback(self, feedback_msg):
        try:
            self.last_feedback_distance = feedback_msg.feedback.distance_remaining
        except Exception:
            pass

    def nav_result_callback(self, future, goal_handle):
        if goal_handle != self.current_goal_handle:
            self.get_logger().info('Ignoring result from stale goal handle')
            return

        status = future.result().status
        if status == 4:  # SUCCEEDED
            self.goals_succeeded += 1
            self.last_success_xy = self.current_goal_xy
            self.retry_count = 0
            self.get_logger().info(
                f'✅ 到达！({self.goals_succeeded}/{self.goals_sent})')
        elif status == 6:  # ABORTED
            self.get_logger().warn('⚠️ ABORTED，加入黑名单')
            self.blacklisted_goals.append(self.current_goal_xy)
            if self.original_goal_xy is not None:
                self.blacklisted_goals.append(self.original_goal_xy)
            self.retry_count = 0
        elif status == 5:  # CANCELED
            self.get_logger().info('ℹ️ 已取消')
            if self.retry_count == 0:
                self.retry_count = 1
                self.get_logger().info('ℹ️ 标记为待重试一次')
            else:
                self.get_logger().warn('⚠️ 重试依然无进展，加入黑名单')
                self.blacklisted_goals.append(self.current_goal_xy)
                if self.original_goal_xy is not None:
                    self.blacklisted_goals.append(self.original_goal_xy)
                self.retry_count = 0
        else:
            self.get_logger().warn(f'⚠️ 状态码: {status}，加入黑名单')
            self.blacklisted_goals.append(self.current_goal_xy)
            if self.original_goal_xy is not None:
                self.blacklisted_goals.append(self.original_goal_xy)
            self.retry_count = 0
        self.is_navigating = False
        self.current_goal_handle = None

    # ===================== 工具 =====================

    def get_robot_position(self):
        try:
            t = self.tf_buffer.lookup_transform(
                'map', self.robot_frame, rclpy.time.Time(),
                timeout=Duration(seconds=1.0))
            x = t.transform.translation.x
            y = t.transform.translation.y
            q = t.transform.rotation
            siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
            cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
            yaw = math.atan2(siny_cosp, cosy_cosp)
            return x, y, yaw
        except Exception as e:
            self.get_logger().warn(f'TF 失败: {e}')
            return None, None, None

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
