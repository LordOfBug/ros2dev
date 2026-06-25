import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    pkg_share = get_package_share_directory('r550_description')

    # 地图文件路径 (由 SLAM mapping 模式生成并保存)
    map_file = os.path.join(pkg_share, 'config', 'test_map.yaml')

    # ========================================================
    # 1. Map Server — 加载已保存的地图并发布到 /map 话题
    # ========================================================
    node_map_server = Node(
        package='nav2_map_server',
        executable='map_server',
        name='map_server',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            'yaml_filename': map_file,
        }]
    )

    # ========================================================
    # 2. SLAM Toolbox — 定位模式 (localization)
    #    不再建新图，而是将实时 LiDAR 扫描与已有地图进行匹配，
    #    仅输出 map→odom 变换来纠正里程计漂移
    # ========================================================
    slam_params = {
        'use_sim_time': True,
        'odom_frame': 'odom',
        'map_frame': 'map',
        'base_frame': 'base_footprint',
        'scan_topic': '/scan',
        'mode': 'localization',            # 关键：定位模式，不建新图

        # Ceres 优化求解器 (与 mapping 模式保持一致)
        'solver_plugin': 'solver_plugins::CeresSolver',
        'ceres_linear_solver': 'SPARSE_NORMAL_CHOLESKY',
        'ceres_preconditioner': 'SCHUR_JACOBI',
        'ceres_trust_strategy': 'LEVENBERG_MARQUARDT',
        'ceres_loss_function_type': 'None',

        # 地图与激光参数 (与 mapping 模式保持一致)
        'resolution': 0.05,
        'max_laser_range': 12.0,
        'minimum_time_interval': 0.1,
        'transform_timeout': 0.2,
        'tf_buffer_duration': 30.0,
        'stack_size_to_use': 40000000,

        # 定位模式需要指定已有地图文件 (slam_toolbox 自有的序列化格式)
        # 注意: slam_toolbox 的 map_file_name 不带扩展名
        # 如果没有 .posegraph 文件，slam_toolbox 会从 /map 话题获取地图
    }

    node_slam_toolbox = Node(
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        name='slam_toolbox',
        output='screen',
        parameters=[slam_params]
    )

    # ========================================================
    # 3. Lifecycle Manager — 管理 map_server 的生命周期
    #    map_server 是 lifecycle 节点，需要被 configure + activate
    # ========================================================
    node_lifecycle_manager = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_localization',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            'autostart': True,
            'node_names': ['map_server'],
        }]
    )

    return LaunchDescription([
        node_map_server,
        node_lifecycle_manager,
        node_slam_toolbox,
    ])
