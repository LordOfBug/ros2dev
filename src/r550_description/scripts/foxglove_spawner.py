#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PointStamped, PoseWithCovarianceStamped
from gazebo_msgs.srv import SpawnEntity, DeleteEntity
import uuid

class FoxgloveObstacleSpawner(Node):
    def __init__(self):
        super().__init__('foxglove_obstacle_spawner')
        
        # 记录所有通过脚本生成的障碍物名字，用于一键清除
        self.spawned_obstacles = []

        # 1. 订阅 Foxglove 的“鼠标点击点”频道 (快捷键 P) 用于召唤障碍物
        self.subscription = self.create_subscription(
            PointStamped,
            '/clicked_point',
            self.clicked_point_callback,
            10
        )

        # 2. 订阅 Foxglove 的“初始位置校准”频道 (快捷键 I) 用于一键清除障碍物
        self.clear_subscription = self.create_subscription(
            PoseWithCovarianceStamped,
            '/initialpose',
            self.clear_obstacles_callback,
            10
        )

        self.get_logger().info('🌟 神笔马良避障刷怪箱 & 魔法橡皮擦节点已启动！')
        self.get_logger().info('📦 召唤：请在 Foxglove 里按下 [P] 键并点击网格投放红色箱子')
        self.get_logger().info('🧹 清除：请在 Foxglove 里按下 [I] 键并点击网格任意位置一键抹除所有箱子！')

        # 3. 创建 Gazebo 的 entity 投放和删除服务客户端
        self.spawn_client = self.create_client(SpawnEntity, '/spawn_entity')
        self.delete_client = self.create_client(DeleteEntity, '/delete_entity')
        
        while not self.spawn_client.wait_for_service(timeout_sec=1.0):
            self.get_logger().warn('⏳ 正在等待 Gazebo 物理服务上线...')

        # 4. 预设我们召唤的 3D 红色大箱子模型（SDF 格式）
        self.obstacle_sdf = """
        <sdf version='1.6'>
          <model name='dynamic_box'>
            <static>true</static>
            <link name='link'>
              <collision name='collision'>
                <geometry>
                  <box><size>0.5 0.5 1.0</size></box>
                </geometry>
              </collision>
              <visual name='visual'>
                <geometry>
                  <box><size>0.5 0.5 1.0</size></box>
                </geometry>
                <material>
                  <ambient>1 0 0 1</ambient>
                  <diffuse>1 0 0 1</diffuse>
                </material>
              </visual>
            </link>
          </model>
        </sdf>
        """

    def clicked_point_callback(self, msg):
        # 提取鼠标点击处的 3D 物理空间坐标
        x = msg.point.x
        y = msg.point.y
        z = 0.5  # 箱子高度 1米，中心点放在 z=0.5，刚好平贴地面

        # 生成一个唯一的障碍物名字（比如 click_obstacle_a7b2...），防止名字重复冲突
        unique_id = str(uuid.uuid4())[:8]
        obstacle_name = f"click_obstacle_{unique_id}"

        self.get_logger().info(f'📦 召唤箱子：坐标 (x: {x:.2f}, y: {y:.2f}) -> 实体名: {obstacle_name}')

        # 组装服务请求，发给 Gazebo 物理引擎
        request = SpawnEntity.Request()
        request.name = obstacle_name
        request.xml = self.obstacle_sdf
        request.robot_namespace = ''
        request.initial_pose.position.x = x
        request.initial_pose.position.y = y
        request.initial_pose.position.z = z
        request.reference_frame = 'world'

        # 异步调用服务投放，并将名字记入小本本
        self.spawn_client.call_async(request)
        self.spawned_obstacles.append(obstacle_name)

    def clear_obstacles_callback(self, msg):
        # 检查小本本上是否有障碍物
        if not self.spawned_obstacles:
            self.get_logger().info('🧹 操场干干净净，没有需要清除的障碍物。')
            return

        self.get_logger().info(f'🧹 收到清除信号！正在一键抹除所有 {len(self.spawned_obstacles)} 个障碍物...')
        
        # 遍历删除
        for name in list(self.spawned_obstacles):
            req = DeleteEntity.Request()
            req.name = name
            self.delete_client.call_async(req)
            self.get_logger().info(f'🗑️ 成功蒸发物理实体：{name}')
        
        # 清空小本本
        self.spawned_obstacles.clear()

def main(args=None):
    rclpy.init(args=args)
    node = FoxgloveObstacleSpawner()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
