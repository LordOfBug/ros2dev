## Build command
docker buildx build --platform linux/arm64 -t r550-humble-bot:latest --load .


## Cross Build

 [ Ubuntu 开发 PC (x86_64) ] 
       │
       ▼ (使用 QEMU 虚拟出 ARM64 指令环境)
 [ Docker Buildx 交叉编译器 ] ──( 极速编译 )──> [ 生成物理 linux/arm64 镜像 ]
                                                            │
                                              ┌─────────────┴─────────────┐
                                              ▼ (方法 A: 局域网离线 Tar)     ▼ (方法 B: 云端 Push)
                                        [ scp 传输 .tar 压缩包 ]      [ Docker Hub 镜像站 ]
                                              │                           │
                                              └─────────────┬─────────────┘
                                                            ▼ (直接导入并免编译启动)
                                                 [ R550 物理小车 (ARM64) ]


### Steps

# 1. 安装 QEMU 虚拟仿真基础包
sudo apt-get update
sudo apt-get install -y qemu-user-static binfmt-support

# 2. 向 Docker 注册 QEMU 静态解析器（一锤定音 🔨）
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes

# 1. 创建一个名为 r550_builder 的多平台构建器
docker buildx create --name r550_builder --use

# 2. 启动并初始化该构建器
docker buildx inspect --bootstrap

运行后，在终端打印的 Platforms 列表中，只要看到 linux/arm64 和 linux/amd64，说明你的电脑已经完美具备了跨平台编译能力！

docker buildx build --platform linux/arm64 -t r550-humble-bot:latest --load .

--load 参数会强制把编译好的 ARM 镜像塞进你电脑的 docker images 仓库中


