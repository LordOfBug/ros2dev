import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.substitutions import Command
from launch_ros.actions import Node

def generate_launch_description():
    # Find the package and the URDF file
    pkg_share = get_package_share_directory('mk_mini_simulator')
    urdf_file = os.path.join(pkg_share, 'urdf', 'mk_mini.urdf.xacro')

    # Tell ROS 2 to use xacro to read the file
    robot_description_content = Command(['xacro ', urdf_file])
    
    return LaunchDescription([
        # The Robot State Publisher calculates the 3D transforms (TF)
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            parameters=[{'robot_description': robot_description_content}]
        ),
        # The Joint State Publisher GUI gives you the testing sliders
        Node(
            package='joint_state_publisher_gui',
            executable='joint_state_publisher_gui'
        ),
        # RViz2 is the actual 3D visualization window
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            output='screen'
        )
    ])
