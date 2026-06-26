#!/bin/bash

# 获取脚本目录和工作空间目录的绝对路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# 1. 清理残留进程与旧日志
echo "========================================"
echo "🧹 清理残留的 ROS 2 与 Gazebo 进程..."
echo "========================================"
pkill -f "ros2 launch" 2>/dev/null
pkill -f "ros2 run" 2>/dev/null
pkill -f "gzserver" 2>/dev/null
pkill -f "gzclient" 2>/dev/null
pkill -f "frontier_explorer" 2>/dev/null
sleep 1

echo "========================================"
echo "📦 正在编译 r550_description 并清理日志..."
echo "========================================"
cd "$WORKSPACE_DIR" || exit 1
colcon build --packages-select r550_description

if [ $? -ne 0 ]; then
    echo "❌ 编译失败，请检查编译错误！"
    exit 1
fi
echo "✅ 编译成功！"

echo "🧹 清理旧的日志文件..."
rm -f "$WORKSPACE_DIR"/*.log

# 2. 载入 ROS 2 环境
if [ -f "$WORKSPACE_DIR/install/setup.bash" ]; then
    echo "🔄 载入工作区环境 (setup.bash)..."
    source "$WORKSPACE_DIR/install/setup.bash"
else
    echo "❌ 未找到 install/setup.bash，请确保编译生成了环境！"
    exit 1
fi

# 3. 准备后台进程列表，并启用工作控制 (Job Control)
# 开启 set -m 可以使后台进程单独运行在其所属的进程组中，方便后续整组 kill，防止残留孤儿进程
set -m
declare -a pids=()

# 定义清理退出函数
cleanup() {
    echo ""
    echo "========================================"
    echo "🛑 收到中断信号 (Ctrl+C)，正在安全退出所有后台进程..."
    echo "========================================"
    
    # 逆序停止进程 (先停 explorer -> nav2 -> slam -> sim)
    for ((i=${#pids[@]}-1; i>=0; i--)); do
        pid="${pids[i]}"
        if kill -0 "$pid" 2>/dev/null; then
            echo "   正在终止进程 PID: $pid (及所属进程组)..."
            # 发送 TERM 信号给进程组 (-pid)
            kill -TERM -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
        fi
    done
    
    # 等待进程退出
    wait 2>/dev/null
    echo "✅ 所有后台进程已彻底退出！"
    exit 0
}

# 绑定 SIGINT (Ctrl+C) 和 SIGTERM 到 cleanup 函数
trap cleanup SIGINT SIGTERM

echo "========================================"
echo "🚀 正在拉起机器人系统 (输出均重定向至日志)..."
echo "========================================"

# 1. 启动 Gazebo 物理仿真世界
echo "   [1/4] 启动物理仿真世界 (sim.log)..."
(ros2 launch r550_description r550_sim.launch.py 2>&1 | awk '{ print "[" strftime("%Y-%m-%d %H:%M:%S") "] " $0; fflush() }' > "$WORKSPACE_DIR/sim.log") &
pids+=($!)
sleep 4  # 等待仿真物理引擎就绪

# 2. 启动 SLAM 建图与定位
echo "   [2/4] 启动 SLAM 建图 (slam.log)..."
(ros2 launch r550_description r550_slam.launch.py 2>&1 | awk '{ print "[" strftime("%Y-%m-%d %H:%M:%S") "] " $0; fflush() }' > "$WORKSPACE_DIR/slam.log") &
pids+=($!)
sleep 3  # 等待 SLAM/TF 广播就绪

# 3. 启动 Nav2 导航
echo "   [3/4] 启动 Nav2 导航服务 (nav.log)..."
(ros2 launch r550_description r550_nav2.launch.py 2>&1 | awk '{ print "[" strftime("%Y-%m-%d %H:%M:%S") "] " $0; fflush() }' > "$WORKSPACE_DIR/nav.log") &
pids+=($!)
sleep 6  # 等待行为树与控制器激活

# 4. 启动 Frontier 自动探索
echo "   [4/4] 启动 Frontier 自动探索节点 (plan.log)..."
export PYTHONUNBUFFERED=1
export RCUTILS_LOGGING_BUFFERED_STREAM=0
(ros2 run r550_description frontier_explorer.py 2>&1 | awk '{ print "[" strftime("%Y-%m-%d %H:%M:%S") "] " $0; fflush() }' > "$WORKSPACE_DIR/plan.log") &
pids+=($!)

echo "========================================"
echo "🎯 系统拉起完毕！监控日志请运行："
echo "   - 仿真: tail -f sim.log"
echo "   - 建图: tail -f slam.log"
echo "   - 导航: tail -f nav.log"
echo "   - 探索: tail -f plan.log"
echo ""
echo "💡 按 [Ctrl + C] 退出并清理全部进程。"
echo "========================================"

# 维持脚本挂起，等待 Ctrl+C
# 当 Ctrl+C 被按下时，wait 会被立即中断，并触发 cleanup 陷阱函数
wait
