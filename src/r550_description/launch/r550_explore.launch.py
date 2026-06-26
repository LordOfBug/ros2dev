import os
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    # Frontier Explorer 自主探索节点
    # 订阅 /map 检测未知边界，通过 Nav2 驱动机器人自动建图
    node_explorer = Node(
        package='r550_description',
        executable='frontier_explorer.py',
        name='frontier_explorer',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            'min_frontier_size': 5,       # 最小 frontier 集群大小（过滤噪声）
            'exploration_timeout': 120.0, # 单次导航超时（秒）
            'robot_frame': 'base_footprint',
            'blacklist_radius': 0.5,      # 失败目标屏蔽半径（米）
            'update_interval': 2.0,       # 地图分析间隔（秒）
            'min_goal_distance': 1.0,     # 跳过距离太近的 frontier（米）
            'goal_offset': 0.5,           # 目标从 frontier 向机器人方向偏移（米）
        }]
    )

    return LaunchDescription([
        node_explorer
    ])
