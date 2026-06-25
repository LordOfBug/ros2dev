#!/usr/bin/env python3
"""
读取已保存的 SLAM 地图，提取障碍物位置。
用法:
  python3 scripts/read_map_obstacles.py maps/test_map.yaml          # 仅分析
  python3 scripts/read_map_obstacles.py maps/test_map.yaml --spawn  # 分析并在 Gazebo 中重建
"""

import yaml
import numpy as np
from scipy.ndimage import label
import sys
import os

map_yaml = sys.argv[1] if len(sys.argv) > 1 else 'maps/test_map.yaml'
do_spawn = '--spawn' in sys.argv

with open(map_yaml) as f:
    meta = yaml.safe_load(f)

res = meta['resolution']
ox, oy = meta['origin'][0], meta['origin'][1]
pgm_path = os.path.join(os.path.dirname(map_yaml), meta['image'])

with open(pgm_path, 'rb') as f:
    magic = f.readline().decode().strip()
    line = f.readline().decode().strip()
    while line.startswith('#'):
        line = f.readline().decode().strip()
    w, h = map(int, line.split())
    maxval = int(f.readline().decode().strip())
    img = np.frombuffer(f.read(), dtype=np.uint8).reshape(h, w)

print(f'Map: {w}x{h}px = {w*res:.1f}m x {h*res:.1f}m')
print(f'Origin: ({ox}, {oy}), Resolution: {res}m/pixel')

occupied = (img == 0)
print(f'Occupied pixels: {np.sum(occupied)}')

labeled, n = label(occupied)
centers = []
for i in range(1, n + 1):
    rs, cs = np.where(labeled == i)
    if len(rs) < 3:
        continue
    cx = ox + np.mean(cs) * res
    cy = oy + (h - np.mean(rs)) * res
    sz = len(rs)
    centers.append((cx, cy, sz))
    print(f'  Obstacle #{len(centers)}: center=({cx:.2f}, {cy:.2f}), {sz} cells')

if not do_spawn:
    # 输出 stdin 管道形式的 spawn 命令
    print(f'\n=== Spawn commands ({len(centers)} obstacles) ===')
    print(f'=== 运行方式: python3 scripts/read_map_obstacles.py maps/test_map.yaml --spawn ===\n')
    for idx, (x, y, _) in enumerate(centers):
        print(f"echo '<sdf version=\"1.6\"><model name=\"box\"><static>true</static><link name=\"link\"><collision name=\"c\"><geometry><box><size>0.5 0.5 1.0</size></box></geometry></collision><visual name=\"v\"><geometry><box><size>0.5 0.5 1.0</size></box></geometry><material><ambient>1 0 0 1</ambient><diffuse>1 0 0 1</diffuse></material></visual></link></model></sdf>' | ros2 run gazebo_ros spawn_entity.py -entity map_obs_{idx} -x {x:.2f} -y {y:.2f} -z 0.5 -stdin")
else:
    # 直接通过 ROS 2 服务调用 Gazebo 投放障碍物
    import rclpy
    from gazebo_msgs.srv import SpawnEntity

    rclpy.init()
    node = rclpy.create_node('map_obstacle_spawner')
    client = node.create_client(SpawnEntity, '/spawn_entity')

    print(f'\n⏳ 等待 Gazebo spawn 服务...')
    if not client.wait_for_service(timeout_sec=5.0):
        print('❌ Gazebo spawn 服务未找到，请确保 Gazebo 正在运行！')
        sys.exit(1)

    sdf = """<sdf version='1.6'>
      <model name='box'>
        <static>true</static>
        <link name='link'>
          <collision name='c'>
            <geometry><box><size>0.5 0.5 1.0</size></box></geometry>
          </collision>
          <visual name='v'>
            <geometry><box><size>0.5 0.5 1.0</size></box></geometry>
            <material>
              <ambient>1 0 0 1</ambient>
              <diffuse>1 0 0 1</diffuse>
            </material>
          </visual>
        </link>
      </model>
    </sdf>"""

    for idx, (x, y, sz) in enumerate(centers):
        req = SpawnEntity.Request()
        req.name = f'map_obs_{idx}'
        req.xml = sdf
        req.initial_pose.position.x = x
        req.initial_pose.position.y = y
        req.initial_pose.position.z = 0.5
        req.reference_frame = 'world'

        future = client.call_async(req)
        rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)

        if future.result() and future.result().success:
            print(f'  ✅ Obstacle #{idx+1} spawned at ({x:.2f}, {y:.2f})')
        else:
            print(f'  ❌ Failed to spawn obstacle #{idx+1}')

    print(f'\n🎉 Done! {len(centers)} obstacles recreated from map.')
    node.destroy_node()
    rclpy.shutdown()
