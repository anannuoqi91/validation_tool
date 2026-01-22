#!/bin/bash

# 构建脚本 - 构建前端并重新构建Docker镜像

echo "=== 开始构建验证工具 ==="

# 检查是否在项目根目录
if [ ! -f "Dockerfile" ]; then
    echo "错误：请在项目根目录运行此脚本"
    exit 1
fi

# 构建前端
echo "1. 构建前端..."
cd frontend
if [ ! -f "package.json" ]; then
    echo "错误：frontend目录缺少package.json文件"
    exit 1
fi

# 安装依赖并构建
npm install
if [ $? -ne 0 ]; then
    echo "错误：前端依赖安装失败"
    exit 1
fi

npm run build
if [ $? -ne 0 ]; then
    echo "错误：前端构建失败"
    exit 1
fi

cd ..

# 构建Docker镜像
echo "2. 构建Docker镜像..."
docker build -t validation_tool:latest .

if [ $? -eq 0 ]; then
    echo "=== 构建完成 ==="
    echo "镜像名称: validation_tool:latest"
    echo "运行命令: docker-compose up -d"
else
    echo "错误：Docker镜像构建失败"
    exit 1
fi