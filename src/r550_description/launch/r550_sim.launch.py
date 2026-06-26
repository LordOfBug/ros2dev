import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, Command
from launch_ros.actions import Node

def generate_launch_description():
    # 1. 寻找机器人描述包的路径
    pkg_share = get_package_share_directory('r550_description')
    
    # 2. 找到 xacro 模型文件并将其翻译成 xml 格式的 urdf
    xacro_file = os.path.join(pkg_share, 'urdf', 'r550.urdf.xacro')
    robot_description_raw = Command(['xacro ', xacro_file])
    
    # 3. 启动机器状态发布器 (Robot State Publisher)
    # 它负责向系统广播小车的所有关节和连接处的空间相对位置
    node_robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[{'robot_description': robot_description_raw, 'use_sim_time': True}]
    )

    # 4. 导入 Gazebo 官方的启动脚本 (Turn off GUI by setting gui to false)
    #    支持通过 world:=xxx 参数加载自定义世界文件
    default_world = os.path.join(pkg_share, 'worlds', 'empty.world')
    gazebo_pkg_launch = os.path.join(get_package_share_directory('gazebo_ros'), 'launch', 'gazebo.launch.py')

    declare_world = DeclareLaunchArgument(
        'world', default_value='',
        description='Path to Gazebo world file (leave empty for default empty world)')

    launch_gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(gazebo_pkg_launch),
        launch_arguments={'world': LaunchConfiguration('world'), 'gui': 'false'}.items()
    )
    
    # 5. 启动一个叫 spawn_entity 的节点，把我们的 3D R550 小车“扔”进 Gazebo 虚拟世界中
    node_spawn_entity = Node(
        package='gazebo_ros',
        executable='spawn_entity.py',
        arguments=['-topic', 'robot_description', '-entity', 'r550_robot',
                   '-x', '0.0', '-y', '-2.0', '-z', '0.1'],
        output='screen'
    )

    # 6. 整合所有任务
    return LaunchDescription([
        declare_world,
        node_robot_state_publisher,
        launch_gazebo,
        node_spawn_entity
    ])
