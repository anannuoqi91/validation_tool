#!/bin/bash

echo "创建所需的目录结构..."
mkdir -p apollo/cyber

echo "目录结构:"
echo "├── apollo/"
echo "│   └── cyber/  (用于存放Apollo Cyber文件)"
echo "├── app/        (当前项目目录)"
echo "    ├── models/     (现有)"
echo "    ├── data/       (现有)"
echo "    ├── results/    (现有)"
echo "    ├── data_adapter.py (现有)"
echo "    └── 其他项目文件"

echo ""
echo "请将您的Apollo Cyber文件复制到apollo/cyber目录:"
echo "cp -r /path/to/your/apollo/cyber/* ./apollo/cyber/"