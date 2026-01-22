#!/bin/bash

# 设置环境变量
APP_PATH="/app"
PROJECT_PATH=$(pwd)

# 检查容器是否已存在
if [ "$(docker ps -aq -f name=validation_tool)" ]; then
    echo "停止并删除现有容器..."
    docker stop validation_tool
    docker rm validation_tool
fi

# 检查镜像是否存在，如果不存在则构建
if [ -z "$(docker images -q validation_tool:latest)" ]; then
    echo "构建Docker镜像..."
    docker build -t validation_tool:latest .
fi

# 运行容器
echo "启动验证工具容器..."
docker run -it -d \
    --name validation_tool \
    --net=host \
    --privileged \
    --gpus all \
    -v /etc/localtime:/etc/localtime:ro \
    -v /etc/timezone:/etc/timezone:ro \
    -v /dev:/dev \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$PROJECT_PATH":"$APP_PATH" \
    -v "$PROJECT_PATH/apollo":"/apollo" \
    -w "$APP_PATH" \
    -e PYTHONPATH="$APP_PATH:$APP_PATH" \
    -e APP_PATH="$APP_PATH" \
    --ipc=host \
    validation_tool:latest \
    bash


# docker run --restart=always --env HOST_IP=172.30.0.1 -it -d --net=host --privileged -v /etc/localtime:/etc/localtime:ro -v /etc/timezone:/etc/timezone:ro -v /usr/share/zoneinfo:/usr/share/zoneinfo:ro -v /home/seyond_user/od/SW:/apollo/ -v /dev:/dev --gpus all --ipc=host --name OmniVidi_VL virtual_loop:x86 bash /apollo/apollo_od.bash