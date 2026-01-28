import numpy as np
import cv2


def pointcloud_to_image(points: np.ndarray,
                        width: int = 640, height: int = 640,
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


def encode_image_to_jpeg(image: np.ndarray, quality: int = 80) -> bytes:
    """将numpy图像编码为JPEG字节"""
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    ret, buffer = cv2.imencode(
        '.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buffer.tobytes() if ret else None
