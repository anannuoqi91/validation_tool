# 使用Ubuntu 18.04作为基础镜像
FROM ubuntu:18.04

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV APOLLO_PATH=/apollo
ENV CYBER_PATH=$APOLLO_PATH/cyber
ENV APP_PATH=/app
ENV NODE_VERSION=18

# 创建apollo目录结构
RUN mkdir -p $APOLLO_PATH/cyber

# 设置工作目录为app
WORKDIR $APP_PATH

# 安装系统依赖（包含Node.js）
RUN apt-get update && apt-get install -y \
    python3.8 \
    python3.8-dev \
    python3-pip \
    python3.8-venv \
    wget \
    curl \
    git \
    build-essential \
    cmake \
    pkg-config \
    libopencv-dev \
    libgoogle-glog-dev \
    libboost-all-dev \
    libeigen3-dev \
    libgflags-dev \
    libprotobuf-dev \
    protobuf-compiler \
    libhdf5-dev \
    libatlas-base-dev \
    libgtest-dev \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# 安装Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y nodejs

# 验证Node.js和npm安装
RUN node --version && npm --version

# 创建Python虚拟环境
RUN python3.8 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 升级pip
RUN pip install --upgrade pip

# 安装Python依赖
COPY requirements.txt .
RUN pip install -r requirements.txt

# 安装Apollo Cyber Python绑定
RUN pip install cyber_record

# 设置Python路径
ENV PYTHONPATH=$APP_PATH:$APP_PATH/proto

# 复制前端代码
COPY frontend/ ./frontend/

# 构建前端
WORKDIR $APP_PATH/frontend
RUN npm install \
    && npm run build \
    && cp -r dist/ ../web/ \
    && rm -rf node_modules/ .npm/ package-lock.json

# 返回工作目录
WORKDIR $APP_PATH

# 创建启动脚本
RUN echo '#!/bin/bash\n\
    source /opt/venv/bin/activate\n\
    # 检查是否映射了外部apollo目录\n\
    if [ -d "/host_apollo" ] && [ -f "/host_apollo/cyber/setup.bash" ]; then\n\
    echo "使用外部映射的apollo目录"\n\
    export APOLLO_PATH=/host_apollo\n\
    export CYBER_PATH=$APOLLO_PATH/cyber\n\
    source $APOLLO_PATH/cyber/setup.bash\n\
    elif [ -f "$APOLLO_PATH/cyber/setup.bash" ]; then\n\
    echo "使用容器内的apollo目录"\n\
    source $APOLLO_PATH/cyber/setup.bash\n\
    else\n\
    echo "警告: 未找到cyber/setup.bash文件，将使用默认配置"\n\
    fi\n\
    cd $APP_PATH\n\
    exec "$@"' > /entrypoint.sh && chmod +x /entrypoint.sh

# 设置入口点
ENTRYPOINT ["/entrypoint.sh"]

# 默认命令
# CMD ["python3", "data_adapter.py"]