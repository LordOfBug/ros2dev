cmake_minimum_required(VERSION 3.8)
project(r550_description)

# 开启 C++ 编译器警告（良好的编程习惯）
if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# 寻找编译依赖的 ROS 2 核心库
find_package(ament_cmake REQUIRED)

# 核心：将我们的 3D 模型(urdf)和启动脚本(launch)安装到系统共享路径中
install(
  DIRECTORY urdf launch config
  DESTINATION share/${PROJECT_NAME}
)

# 声明这是一个标准的 ROS 2 宏包
ament_package()
