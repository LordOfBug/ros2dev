#!/bin/bash

# 解冻物理世界服务
source ~/work/ros2/r550/install/setup.bash
ros2 service call /unpause_physics std_srvs/srv/Empty {}
