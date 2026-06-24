#!/bin/bash

# 解冻物理世界服务
ros2 service call /unpause_physics std_srvs/srv/Empty {}
