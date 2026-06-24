import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    # 1. 声明 SLAM Toolbox 的核心运行参数
    # 这些参数直接写在脚本里，免去了额外加载复杂参数配置文件的麻烦，确保 100% 顺畅运行！
    slam_params = {
        'use_sim_time': True,          # 在 Gazebo 仿真中必须设置为 True，使用仿真时钟
        'odom_frame': 'odom',          # 里程计坐标系
        'map_frame': 'map',            # 地图坐标系
        'base_frame': 'base_footprint',# 机器人底盘投影坐标系
        'scan_topic': '/scan',         # 订阅的雷达通道
        'mode': 'mapping',             # 运行模式：建图模式
        
        # 扫描匹配与闭环检测（Loop Closure）核心参数，保证建图时墙壁不会重影、错位
        'solver_plugin': 'solver_plugins::CeresSolver', # Ceres 优化求解器
        'ceres_linear_solver': 'SPARSE_NORMAL_CHOLESKY',
        'ceres_preconditioner': 'SCHUR_JACOBI',
        'ceres_trust_strategy': 'LEVENBERG_MARQUARDT',
        'ceres_loss_function_type': 'None',
        
        # 栅格地图分辨率（0.05m 代表每个地图像素代表真实世界的 5 厘米）
        'resolution': 0.05,
        'max_laser_range': 12.0,       # 雷达最大扫描范围（匹配我们 URDF 里的 12 米设定）
        'minimum_time_interval': 0.1,  # 激光帧处理的时间间隔
        'transform_timeout': 0.2,
        'tf_buffer_duration': 30.0,
        'stack_size_to_use': 40000000, # 内存分配大小
    }

    # 2. 声明 SLAM Toolbox 异步建图节点
    # 它会自动监听小车的 /scan 激光数据和 /tf 坐标变换，在内存中实时还原 2D 栅格地图，并广播 /map 话题
    node_slam_toolbox = Node(
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        name='slam_toolbox',
        output='screen',
        parameters=[slam_params]
    )

    # 3. 组装任务清单
    return LaunchDescription([
        node_slam_toolbox
    ])
