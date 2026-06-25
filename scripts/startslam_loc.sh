#!/bin/bash

# 启动自动驾驶仪
source ~/work/ros2/r550/install/setup.bash
ros2 launch r550_description r550_slam_loc.launch.py | tee ~/work/ros2/r550/slam_loc.log
