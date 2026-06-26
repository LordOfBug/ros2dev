#!/bin/bash

source ~/work/ros2/r550/install/setup.bash
ros2 run r550_description frontier_explorer.py | tee ~/work/ros2/r550/plan.log
