#!/bin/bash

# 开发环境启动脚本

echo "=== 启动开发环境 ==="

# 启动前端开发服务器
echo "1. 启动前端开发服务器..."
cd frontend
npm run dev &
FRONTEND_PID=$!

# 返回项目根目录
cd ..

# 启动后端服务器
echo "2. 启动后端服务器..."
python3 web/app.py &
BACKEND_PID=$!

echo "前端开发服务器 PID: $FRONTEND_PID"
echo "后端服务器 PID: $BACKEND_PID"
echo "前端地址: http://localhost:3000"
echo "后端地址: http://localhost:5000"

# 等待用户中断
echo "按 Ctrl+C 停止开发服务器"
trap 'kill $FRONTEND_PID $BACKEND_PID; exit' INT
wait