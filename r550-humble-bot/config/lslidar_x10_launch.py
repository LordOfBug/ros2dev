import os
import subprocess
from ament_index_python.packages import get_package_share_directory
from launch_ros.actions import LifecycleNode
from launch import LaunchDescription

def generate_launch_description():
    driver_config = os.path.join(get_package_share_directory('lslidar_driver'),'config','lslidar_x10.yaml')

    p = subprocess.Popen("echo $ROS_DISTRO", stdout=subprocess.PIPE, shell=True)
    driver_node = ""
    ros_version = p.communicate()[0]

    if ros_version == b'dashing\n' or ros_version == b'eloquent\n':
        driver_node = LifecycleNode(package='lslidar_driver',
                                    node_executable='lslidar_driver_node',
                                    node_name='lslidar_driver_node',
                                    node_namespace='x10',
                                    output='screen',
                                    parameters=[driver_config],
                                    remappings=[('scan', '/scan')],
                                    )
    else:
        driver_node = LifecycleNode(package='lslidar_driver',
                                    executable='lslidar_driver_node',
                                    name='lslidar_driver_node',
                                    namespace='x10',
                                    parameters=[driver_config],
                                    remappings=[('scan', '/scan')],
                                    output='screen'
                                    )

    return LaunchDescription([
        driver_node
    ])
