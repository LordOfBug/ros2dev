#!/bin/bash

# 编译并刷新环境
cd ~/work/ros2/r550
colcon build --packages-select r550_description

echo "Clean logs ..."
rm -f *.log
