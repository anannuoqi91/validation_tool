import queue
import os
import sys
import logging
import threading
import time
import numpy as np
import cv2
from backend.utils.log_util import logger

try:
    from cyber_py3 import cyber
    from proto.drivers_pb2 import PointCloud2
except ImportError as e:
    logger.error(f"Failed to import cyber module: {e}")
    logger.info("Running in limited mode without cyber support")


class PointCloudAdapter:
    def __init__(self, channel_name: str = None) -> None:
        self.is_running = False
        self.processing_thread = None
        self.mode = "online"
        self.pointscore = []
        self._init_cyber()
        self._init_channels_name(channel_name)

    def _init_cyber(self, node_name: str = "pointcloud_adapter_node"):
        cyber.init()
        self.cyber_node = cyber.Node(node_name)

    def _init_channels_name(self, channel_name: str = None):
        if channel_name is None or channel_name.strip() == "":
            self.channels_name = []
            self.channels_type = []
        else:
            self.channels_name = [
                i.strip() for i in channel_name.split(";") if i.strip() != ""]
            self.channels_type = [
                'dynamic' if "dynamic" in _ else 'static' for _ in self.channels_name]
        self.pc_num = len(self.channels_name)
        self._init_reader()

    def _init_reader(self):
        self.pointcloud_readers = [None] * self.pc_num
        self.pointcloud_queues = [queue.Queue(
            maxsize=10) for _ in range(self.pc_num)]
        for i, channel_name in enumerate(self.channels_name):
            self.pointcloud_readers[i] = self.cyber_node.create_reader(
                channel_name, PointCloud2, self.__pointcloud_callback, i)

    def __pointcloud_callback(self, msg: PointCloud2, i: int):
        try:
            self.pointcloud_queues[i].put_nowait(msg)
        except queue.Full:
            try:
                # Remove oldest item
                self.pointcloud_queues[i].get_nowait()
                # Add new item
                self.pointcloud_queues[i].put_nowait(msg)
            except queue.Empty:
                # Queue was empty despite being full, just add the item
                self.pointcloud_queues[i].put_nowait(msg)

    def _get_pointcloud(self, i: int):
        try:
            return self.pointcloud_queues[i].get_nowait(), self.channels_type[i]
        except queue.Empty:
            return None, None

    def get_pointclouds_png(self):
        """获取所有点云数据并合并为numpy数组"""
        all_pointclouds = None
        for i in range(self.pc_num):
            i_p, i_type = self._get_pointcloud(i)
            if i_p is None:
                continue
            points = self._parse_point_core_numpy(i_p.point_core)
            points = points.copy()   # 或 np.array(points, copy=True)
            # 根据通道类型修改x坐标：dynamic时x=1，否则x=0
            if i_type == 'dynamic':
                points['x'][:] = 1.0
            else:
                points['x'][:] = 0.0
            if all_pointclouds is None:
                all_pointclouds = points
            else:
                all_pointclouds = np.concatenate(
                    (all_pointclouds, points), axis=0)
        return self._pointcloud_to_image(all_pointclouds) if all_pointclouds is not None else None

    def _pointcloud_to_image(self, points, width: int = 640, height: int = 640,
                             z_range: float = 200.0, y_range: float = 200.0) -> np.ndarray:
        """
        将点云转换为鸟瞰图(BEV)图像

        Args:
            points: numpy结构化数组，包含x, y, z, intensity等字段
            width: 图像宽度
            height: 图像高度
            z_range: z轴坐标范围(米)，例如100表示[-50, 50]
            y_range: y轴坐标范围(米)，例如100表示[-50, 50]

        Returns:
            RGB图像数组 (height, width, 3)
        """
        if points is None or len(points) == 0:
            return np.zeros((height, width, 3), dtype=np.uint8)

        # 提取y, z坐标
        y = points['y']
        z = points['z']
        x = points['x']  # 用于颜色区分

        # 坐标映射到图像坐标系
        # 点云坐标系: z向前，y向左，x表示高度（用于颜色）
        # 图像坐标系: (0,0)在左上角，y向下
        z_scale = height / z_range  # z轴对应图像纵向
        y_scale = width / y_range   # y轴对应图像横向

        # 过滤有效点（去除异常值）
        valid_mask = (np.abs(y) < y_range / 2) & (np.abs(z) < z_range / 2)
        y = y[valid_mask]
        z = z[valid_mask]
        x = x[valid_mask]  # x用于颜色区分

        # 转换坐标: 点云(y,z) -> 图像(col,row)
        img_x = ((y_range / 2 - y) * y_scale).astype(np.int32)
        img_y = ((z_range / 2 + z) * z_scale).astype(np.int32)

        # 创建黑色背景图像
        image = np.zeros((height, width, 3), dtype=np.uint8)

        # 使用彩虹色映射（基于过滤后的点数）
        colors = np.zeros((len(x), 3), dtype=np.uint8)
        colors[x == 0] = [255, 255, 255]  # 白色
        colors[x == 1] = [0, 100, 255]     # 蓝色
        # 将点绘制到图像上（使用过滤后的x坐标）
        image[img_y, img_x] = colors  # 绘制点云到图像上
        return image

    def encode_image_to_jpeg(self, image: np.ndarray, quality: int = 80) -> bytes:
        """将numpy图像编码为JPEG字节"""
        if len(image.shape) == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        ret, buffer = cv2.imencode(
            '.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ret:
            logger.error("Failed to encode image to JPEG")
        return buffer.tobytes() if ret else None

    def pointcloud_condition(self) -> bool:
        for i in range(self.pc_num):
            if not self.pointcloud_queues[i].empty():
                return True
        return False

    def stop(self):
        """
        Stop the data adapter processing thread.
        This method can be called to stop both online and offline mode processing.
        """
        if not self.is_running:
            logger.info("PointCloudAdapter is not running")
            return

        logger.info("Stopping PointCloudAdapter processing")

        # Set running flag to false to signal the processing thread to stop
        self.is_running = False

        # Wait for the processing thread to complete if it exists and is alive
        if hasattr(self, 'processing_thread'):
            if self.processing_thread.is_alive():
                self.processing_thread.join(
                    timeout=5.0)  # Wait up to 5 seconds

                if self.processing_thread.is_alive():
                    logger.warning(
                        "Processing thread did not terminate within timeout")
                else:
                    logger.info("Processing thread terminated successfully")

    def run(self, sync: bool = False):
        if self.is_running:
            logger.warning("PointCloudAdapter is already running")
            return
        self.is_running = True

        self.processing_thread = threading.Thread(
            target=self._run_with_mode)
        self.processing_thread.daemon = True  # Thread will exit when main thread exits
        self.processing_thread.start()

        logger.info(
            f"PointCloudAdapter Started {self.mode} mode in background thread")

    def _run_with_mode(self):
        """Internal method that runs in a separate thread and executes the appropriate processing logic"""
        try:
            if self.mode == "online":
                self._run_online()
            else:
                logger.error(f"Unknown mode: {self.mode}")
        except Exception as e:
            logger.error(f"Error in processing thread: {e}")
        finally:
            # Ensure running flag is reset even if an error occurs
            self.is_running = False
            logger.info(f"Stopped {self.mode} mode processing thread")

    def set_online_mode(self,  pointcloud_channel: str = None):
        self.mode = "online"
        # self._clear_sources()
        self.stop()
        self._init_channels_name(pointcloud_channel)

    def _run_online(self):
        """在线模式运行，保持Cyber节点运行以接收消息"""
        logger.info("Starting online mode - waiting for pointcloud messages")
        try:
            # 保持节点运行
            while self.is_running:
                time.sleep(0.1)  # 短暂休眠，避免CPU占用过高
        except KeyboardInterrupt:
            logger.info("Online mode interrupted by user")
        except Exception as e:
            logger.error(f"Error in online mode: {e}")

    def _parse_point_core_numpy(self, point_core_bytes):
        dtype = np.dtype([
            ('x', '<f4'),
            ('y', '<f4'),
            ('z', '<f4'),
            ('intensity', '<u2'),
            ('_pad', 'V2'),
            ('timestamp', '<u8'),
        ])
        return np.frombuffer(point_core_bytes, dtype=dtype)
