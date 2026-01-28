#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import json
import logging
import tempfile
import queue
import time
import threading
from flask import Flask, request, jsonify, Response
import cv2
import numpy as np
from datetime import datetime
import settings
from backend.utils.log_util import logger
from backend.utils.tool_for_record import get_info_with_return
from backend.scripts.record_source import RecordSource
from backend.scripts.simpl_data_process import handle_pointscloud2_to_numpy
from backend.utils.points_to_img import (
    pointcloud_to_image, encode_image_to_jpeg)
try:
    from save_results import SaveResults
    from matcher import Matcher
    from trigger import Trigger
    from tracker import Tracker
    from backend.scripts.data_adapter import DataAdapter
    from backend.modules.camera_modules import ImageData
    from backend.modules.simpl_modules import *
    from backend.scripts.pointcloud_adapter import PointCloudAdapter
except Exception as e:
    raise ImportError(
        f"Failed to import required modules. Please check your installation.\n {e}")

# 创建Flask应用
app = Flask(__name__, static_folder=None)  # 禁用默认静态文件服务
app.config['UPLOAD_FOLDER'] = os.path.join(
    os.path.dirname(__file__), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

# CORS支持 - 添加响应头


@app.after_request
def set_csp_header(response):
    csp_policy = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-eval' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' http://localhost:5000 ws: wss:; "
        "media-src 'self' blob:;"
    )
    response.headers['Content-Security-Policy'] = csp_policy
    return response


@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers',
                         'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods',
                         'GET,PUT,POST,DELETE,OPTIONS')
    return response

# 处理OPTIONS请求（CORS预检）


@app.route('/api/<path:path>', methods=['OPTIONS'])
def options_handler(path):
    return '', 200


# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 全局变量
current_data_adapter = None
current_tracker = None
current_trigger = None
current_matcher = None
current_pointcloud_adapter = None
save_results = SaveResults()

# 统计数据映射
map_lock = threading.Lock()
image_stats_map = {}
event_stats_map = {}

#
# image_used_track_ids = set()

# 使用队列缓存图像数据
image_queue = queue.Queue(maxsize=10)  # 设置最大队列大小，防止内存溢出
# 使用条件量通知新图像到达
image_condition = threading.Condition()

config_file = os.path.join(os.path.dirname(__file__), 'config.json')

# 视频帧生成器


def generate_frames_from_adapter():
    """从DataAdapter生成视频帧"""
    while True:
        current_image_data = None

        # 等待新图像到达
        with image_condition:
            if image_queue.empty():
                # 等待新图像
                image_condition.wait(timeout=1)  # 设置超时，防止永久阻塞

            # 获取最新的图像
            if not image_queue.empty():
                # 清空队列，只保留最新的图像
                while not image_queue.empty():
                    current_image_data = image_queue.get()

        if current_image_data is not None:
            # 将图像数据转换为JPEG格式
            ret, buffer = cv2.imencode('.jpg', current_image_data.image)
            if ret:
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


def generate_points_from_adapter():
    global current_pointcloud_adapter
    """从DataAdapter生成点云，转换为图片流"""
    while True:
        if current_pointcloud_adapter is None:
            time.sleep(0.1)
            continue

        # 等待新点云到达
        if current_pointcloud_adapter.pointcloud_condition():
            # 获取合并后的点云numpy数组
            image = current_pointcloud_adapter.get_pointclouds_png()

            if image is not None:
                # 编码为JPEG
                frame_bytes = current_pointcloud_adapter.encode_image_to_jpeg(
                    image, quality=80)

                if frame_bytes is not None:
                    # 发送图片帧
                    yield (
                        b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n\r\n' +
                        frame_bytes +
                        b'\r\n'
                    )
        else:
            time.sleep(0.01)  # 无数据时短暂休眠


# 图像回调函数


def image_callback(image_data: ImageData):
    """处理接收到的图像数据"""
    # 处理跟踪结果
    if current_tracker is not None:
        track_results = current_tracker.detect_and_track(image_data.image)
        image_display = image_data.image.copy()
        # current_tracker.draw_tracking_results(image_display, track_results)

        if current_trigger is not None:
            trigger_results = current_trigger.process_boxes(track_results)
            for result in trigger_results:

                region_name = result.get('lane_name', None)
                cls_name = result.get('class_name', 'unknown')

                if cls_name not in ['car', 'truck', 'bus']:
                    continue

                if region_name is None:
                    continue

                # 线程安全更新统计数据
                with map_lock:
                    if region_name not in image_stats_map:
                        image_stats_map[region_name] = {'count': 0}

                    if result.get('status', 'ongoing') == 'triggered':
                        image_stats_map[region_name]['count'] += 1
                        # deep copy
                        image_data_triggered = ImageData(
                            timestamp_ms=image_data.timestamp_ms,
                            timestamp_ms_local=image_data.timestamp_ms_local,
                            image=image_data.image.copy(),
                            width=image_data.width,
                            height=image_data.height,
                            channels=image_data.channels,
                            region_name=region_name
                        )
                        current_tracker.draw_tracking_result(
                            image_data_triggered.image, result['box'], result['track_id'], result['class_id'])
                        matched_results = current_matcher.add_image_data(
                            image_data_triggered)
                        if len(matched_results) > 0:
                            save_results.save_results(matched_results)

                current_tracker.draw_tracking_result(
                    image_display, result['box'], result['track_id'], result['class_id'])

    # 将处理后的图像放入队列并通知等待的线程
    with image_condition:
        # 如果队列已满，移除最旧的图像
        if image_queue.full():
            try:
                image_queue.get_nowait()
            except queue.Empty:
                pass

        # deep copy
        image_data_copy = ImageData(
            timestamp_ms=image_data.timestamp_ms,
            timestamp_ms_local=image_data.timestamp_ms_local,
            image=image_display,
            width=image_data.width,
            height=image_data.height,
            channels=image_data.channels
        )

        image_queue.put(image_data_copy)
        # 通知等待的线程
        image_condition.notify_all()


def event_callback(event_data: EventData):
    """处理接收到的事件数据"""
    # logger.info(f"Received event: {event_data}")
    region_name = event_data.region_name
    if region_name is not None:
        with map_lock:
            if region_name not in event_stats_map:
                event_stats_map[region_name] = {'count': 0}
            event_stats_map[region_name]['count'] += 1

    if current_matcher is not None:
        matched_results = current_matcher.add_event_data(event_data)
        if len(matched_results) > 0:
            save_results.save_results(matched_results)


# RTSP流相关路由


@app.route('/api/rtsp/connect', methods=['POST'])
def connect():
    global current_data_adapter
    global current_tracker
    global current_trigger
    global current_matcher
    global current_pointcloud_adapter

    try:
        data = request.get_json()
        rtsp_url = data.get('rtsp_url')
        cyber_event_channel = data.get('cyber_event_channel', '')
        cyber_pointcloud_channel = data.get('cyber_pointcloud_channel', '')

        if not rtsp_url:
            return jsonify({"success": False, "message": "RTSP URL不能为空"})

        # 记录Cyber Event Channel和Pointcloud Channel（如果提供）
        logger.info(
            f"Cyber Event Channel: {cyber_event_channel}, Cyber Pointcloud Channel: {cyber_pointcloud_channel}")

        # 检查RTSP URL格式
        if not rtsp_url.startswith(('rtsp://', 'rtmp://', 'http://', 'https://')):
            return jsonify({"success": False, "message": "请输入有效的RTSP URL"})

        # 初始化Tracker
        current_tracker = Tracker(onnx_model_path='models/yolo11s.pt')

        # 初始化Trigger
        current_trigger = Trigger(
            lane_trigger_path=config_file, lane_detection_point="bottom_center")

        # 初始化Matcher
        current_matcher = Matcher()

        # 清空统计数据
        with map_lock:
            image_stats_map.clear()
            event_stats_map.clear()
            # image_used_track_ids.clear()

        # # 停止之前的适配器
        if current_data_adapter:
            current_data_adapter.stop()
        else:
            current_data_adapter = DataAdapter()

        current_data_adapter.set_image_callback(image_callback)
        current_data_adapter.set_event_callback(event_callback)
        current_data_adapter.set_online_mode(
            rtsp_url, cyber_event_channel, None)
        current_data_adapter.run()

        if current_pointcloud_adapter:
            current_pointcloud_adapter.stop()
        else:
            current_pointcloud_adapter = PointCloudAdapter()
        current_pointcloud_adapter.set_online_mode(cyber_pointcloud_channel)
        current_pointcloud_adapter.run()

        logger.info(f"Connected to RTSP stream: {rtsp_url}")
        return jsonify({"success": True, "stream_url": "/video_feed", "pointcloud_url": "/points"})

    except Exception as e:
        logger.error(f"connection error: {e}")
        return jsonify({"success": False, "message": str(e)})

# Record文件相关路由


@app.route('/api/record/load', methods=['POST'])
def load_record():
    """加载Record文件"""
    global current_data_adapter
    global current_trigger
    global current_matcher
    global current_tracker

    try:
        # 检查是否有文件上传
        if 'record_file' not in request.files:
            return jsonify({"success": False, "message": "未选择文件"})

        file = request.files['record_file']
        if file.filename == '':
            return jsonify({"success": False, "message": "未选择文件"})

        # 保存文件到临时目录
        temp_file_path = os.path.join(tempfile.gettempdir(), file.filename)
        file.save(temp_file_path)
        record_info = get_info_with_return(temp_file_path)
        channel_match = RecordSource.channel_match(record_info['channels'])

        return jsonify({"success": True, "channels": channel_match})

    except Exception as e:
        logger.error(f"Record file processing error: {e}")
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/record/playRecord', methods=['POST'])
def play_record():
    """加载Record文件"""
    global current_data_adapter
    global current_trigger
    global current_matcher
    global current_tracker

    try:
        # 检查是否有文件上传
        if 'record_file' not in request.files:
            return jsonify({"success": False, "message": "未选择文件"})

        file = request.files['record_file']
        if file.filename == '':
            return jsonify({"success": False, "message": "未选择文件"})

        # 保存文件到临时目录
        temp_file_path = os.path.join(tempfile.gettempdir(), file.filename)
        file.save(temp_file_path)

        logger.info(f"Loaded record file: {temp_file_path}")

        # 初始化Tracker
        current_tracker = Tracker(onnx_model_path='models/yolo11s.pt')

        # 初始化Trigger
        current_trigger = Trigger(lane_trigger_path=config_file)

        # 初始化Matcher
        current_matcher = Matcher()

        # 清空统计数据
        with map_lock:
            image_stats_map.clear()
            event_stats_map.clear()
            # image_used_track_ids.clear()

        if current_data_adapter:
            current_data_adapter.stop()
        else:
            current_data_adapter = DataAdapter()

        current_data_adapter.set_image_callback(image_callback)
        current_data_adapter.set_event_callback(event_callback)
        current_data_adapter.set_offline_mode(temp_file_path, fps=10,  camera_channel=request.form.get(
            'camera_channel'), event_channel=request.form.get('event_channel'), box_channel=request.form.get('box_channel'), points_channel=request.form.get('points_channel'))
        current_data_adapter.run()

        logger.info(f"Processing record file: {temp_file_path}")
        return jsonify({"success": True, "stream_url": "/video_feed", "pointcloud_url": "/points"})

    except Exception as e:
        logger.error(f"Record file processing error: {e}")
        return jsonify({"success": False, "message": str(e)})

# 视频流路由


@app.route('/video_feed')
def video_feed():
    """视频流输出"""
    return Response(generate_frames_from_adapter(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/points')
def pointcloud_feed():
    return Response(generate_points_from_adapter(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


# 配置相关路由


@app.route('/api/config/save', methods=['POST'])
def save_config():
    """保存配置"""
    try:
        config = request.get_json()

        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)

        logger.info("Config saved successfully")
        return jsonify({"success": True, "message": "配置保存成功"})

    except Exception as e:
        logger.error(f"Config save error: {e}")
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/config/load', methods=['GET'])
def load_config():
    """加载配置"""
    try:
        if not os.path.exists(config_file):
            return jsonify({"success": True, "config": {"lanes": [], "triggers": []}})

        with open(config_file, 'r') as f:
            config = json.load(f)

        logger.info("Config loaded successfully")
        return jsonify({"success": True, "config": config})

    except Exception as e:
        logger.error(f"Config load error: {e}")
        return jsonify({"success": False, "message": str(e)})

# 清理资源


@app.route('/api/cleanup', methods=['POST'])
def cleanup():
    """清理资源"""
    global current_data_adapter

    try:
        if current_data_adapter:
            current_data_adapter._clear_sources()
            current_data_adapter = None

        logger.info("Resources cleaned up successfully")
        return jsonify({"success": True, "message": "资源清理成功"})

    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        return jsonify({"success": False, "message": str(e)})

# 获取统计数据


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """获取统计数据"""
    with map_lock:
        # 合并统计数据，以image_stats_map为准
        merged_stats = {}
        total_image_count = 0
        total_event_count = 0

        for region_name, image_stats in image_stats_map.items():
            image_count = image_stats['count']
            event_count = event_stats_map.get(region_name, {}).get('count', 0)

            merged_stats[region_name] = {
                'image_count': image_count,
                'event_count': event_count
            }

            total_image_count += image_count
            total_event_count += event_count

        # 添加总计
        merged_stats['total'] = {
            'image_count': total_image_count,
            'event_count': total_event_count
        }

        return jsonify({"success": True, "stats": merged_stats})

# 健康检查


@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({"success": True, "status": "ok", "timestamp": datetime.now().isoformat()})


if __name__ == '__main__':
    logger.info("Starting web application...")
    # 确保uploads目录存在
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    # 启动Flask应用
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
