#!/bin/bash

# 拉起物理仿真世界
source ~/work/ros2/r550/install/setup.bash
ros2 launch r550_description r550_sim.launch.py | tee ~/work/ros2/r550/sim.log
