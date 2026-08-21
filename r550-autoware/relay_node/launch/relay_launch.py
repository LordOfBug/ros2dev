import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory('r550_autoware_relay')
    config_file = os.path.join(pkg_share, 'config', 'relay_topics.yaml')

    relay_node = Node(
        package='r550_autoware_relay',
        executable='relay_node',
        name='r550_autoware_relay',
        output='screen',
        parameters=[config_file],
    )

    return LaunchDescription([relay_node])
