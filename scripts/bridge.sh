#!/bin/bash

# ros2 launch foxglove_bridge foxglove_bridge_launch.xml capabilities:="[clientPublish,parameters,services,connectionGraph]" send_buffer_limit:=100000000
ros2 launch foxglove_bridge foxglove_bridge_launch.xml use_sim_time:=true capabilities:="[clientPublish,parameters,services,connectionGraph]" send_buffer_limit:=100000000
