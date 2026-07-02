import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    # 1. 寻找我们的小车描述包路径
    pkg_share = get_package_share_directory('r550_description')
    
    # 2. 寻找 ROS 2 官方标准导航包 (nav2_bringup) 的路径
    nav2_bringup_share = get_package_share_directory('nav2_bringup')

    # 3. 定位我们在 Canvas 中设计好的核心配置文件 (nav2_params.yaml)
    params_file_path = os.path.join(pkg_share, 'config', 'nav2_params.yaml')

    # 4. 声明启动参数，默认关闭仿真时间 (use_sim_time:=False，适配真机测试)
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Use simulation (Gazebo) clock if true'
    )

    declare_params_file = DeclareLaunchArgument(
        'params_file',
        default_value=params_file_path,
        description='Full path to the ROS2 parameters file to use for all launched nodes'
    )

    # 5. 动态解析自定义无恢复行为树 XML 路径并传给 navigation_launch.py
    default_bt_xml_path = os.path.join(pkg_share, 'config', 'navigate_to_pose_no_recovery.xml')

    launch_navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_bringup_share, 'launch', 'navigation_launch.py')
        ),
        launch_arguments={
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'params_file': LaunchConfiguration('params_file'),
            'default_bt_xml_filename': default_bt_xml_path,
            'use_lifecycle_mgr': 'true'
        }.items()
    )

    # 6. 将所有启动任务打包成一张任务清单
    return LaunchDescription([
        declare_use_sim_time,
        declare_params_file,
        launch_navigation
    ])
