#!/bin/bash

colcon build --packages-select r550_description
source install/setup.bash
ros2 launch r550_description r550_sim.launch.py
