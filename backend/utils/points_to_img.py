import numpy as np
import cv2


def pointcloud_to_image(points: np.ndarray,
                        width: int = 640, height: int = 640, z_range_m=[-150, 150], y_range_m=[-150, 150]) -> np.ndarray:
    """
        将点云转换为鸟瞰图(BEV)图像

        Args:
            points: numpy结构化数组，包含x, y, z, intensity等字段
            width: 图像宽度
            height: 图像高度
            自适应点云范围，根据点云的最大最小值动态调整

        Returns:
            RGB图像数组 (height, width, 3)
        """
    if points is None or len(points) == 0:
        return np.zeros((height, width, 3), dtype=np.uint8)

    # 提取y, z坐标
    y = points['y']
    z = points['z']
    x = points['x']  # 用于颜色区分
    # 自适应范围
    y_abs_max = float(np.max(np.abs(np.array(y_range_m)))
                      ) if len(y_range_m) > 0 else 1.0
    z_abs_max = float(np.max(np.abs(np.array(z_range_m)))
                      ) if len(z_range_m) > 0 else 1.0
    cx = width / 2.0
    cy = height / 2.0
    scale_y = (cx - 1) / y_abs_max * 0.95
    scale_z = (cy - 1) / z_abs_max * 0.95
    img_x = (cx - y * scale_y).astype(np.int32)
    img_y = (cy - z * scale_z).astype(np.int32)

    valid = (
        (img_x >= 0) & (img_x < width) &
        (img_y >= 0) & (img_y < height)
    )

    # 创建黑色背景图像
    image = np.zeros((height, width, 3), dtype=np.uint8)

    # 使用彩虹色映射（基于过滤后的点数）
    colors = np.zeros((len(x), 3), dtype=np.uint8)
    colors[x == 0] = [255, 255, 255]  # 白色
    colors[x == 1] = [0, 100, 255]     # 蓝色
    # 将点绘制到图像上（使用过滤后的x坐标）
    image[img_y[valid], img_x[valid]] = colors[valid]
    return image


def encode_image_to_jpeg(image: np.ndarray, quality: int = 80) -> bytes:
    """将numpy图像编码为JPEG字节"""
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    ret, buffer = cv2.imencode(
        '.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buffer.tobytes() if ret else None
