#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trigger
-------
1) 读取 lane_trigger_data.json 里的车道多边形和触发线配置
2) 输入检测框，输出命中触发线的框及其所在车道信息
"""
import json
from typing import Dict, List, Tuple, Optional, Any

import numpy as np


def point_in_polygon(point: Tuple[float, float], polygon: List[Dict[str, float]]) -> bool:
    """射线法判断点是否在多边形内"""
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]['x'], polygon[i]['y']
        x2, y2 = polygon[(i + 1) % n]['x'], polygon[(i + 1) % n]['y']
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-9) + x1):
            inside = not inside
    return inside


def point_to_segment_distance(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    ab = (x2 - x1, y2 - y1)
    ap = (px - x1, py - y1)
    cross_product = abs(ab[0] * ap[1] - ab[1] * ap[0])
    ab_length = np.sqrt(ab[0]**2 + ab[1]**2)
    return cross_product / ab_length

class Trigger:
    """
    用于车道与触发线分析。
    - 读取车道和触发线配置文件
    - 输入检测框，输出命中触发线的框及其所在车道信息
    - 支持配置车道检测点：中心点、上边沿中心点或下边沿中心点
    """

    def __init__(
        self,
        lane_trigger_path: str = "lane_trigger_data.json",
        video_size: Optional[Dict[str, int]] = None,
        lane_detection_point: str = "center"  # 可选值: "center", "top_center", "bottom_center"
    ) -> None:
        self.lane_trigger_path = lane_trigger_path

        # 加载配置
        self.lanes, self.triggers, config_video_size = self._load_lane_trigger()
        
        # 视频尺寸（优先使用外部传入的参数，其次使用配置文件中的尺寸）
        self.video_size = video_size or config_video_size

        # 缩放因子（根据实际视频尺寸和配置尺寸计算）
        self.scale_x = 1.0
        self.scale_y = 1.0
        
        # 车道检测点配置
        valid_points = ["center", "top_center", "bottom_center"]
        if lane_detection_point not in valid_points:
            raise ValueError(f"lane_detection_point 必须是 {valid_points} 中的一个，当前值: {lane_detection_point}")
        self.lane_detection_point = lane_detection_point

        self.used_track_ids = set()
        self.max_track_ids = 1000

    def _load_lane_trigger(self) -> Tuple[List[Dict], List[Dict], Dict[str, int]]:
        """加载车道线和触发线配置文件"""
        with open(self.lane_trigger_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        lanes = data.get("lanes", [])
        triggers = data.get("triggers", [])
        video_size = data.get("videoSize", {})
        return lanes, triggers, video_size

    def set_scale(self, frame_width: int, frame_height: int) -> None:
        """根据实际视频尺寸和配置尺寸计算缩放因子"""
        if not self.video_size:
            self.scale_x = self.scale_y = 1.0
            return
        
        vw = self.video_size.get("width", frame_width)
        vh = self.video_size.get("height", frame_height)
        
        if vw == 0 or vh == 0:
            self.scale_x = self.scale_y = 1.0
            return
        
        self.scale_x = frame_width / vw
        self.scale_y = frame_height / vh

    def _scale_point(self, p: Dict[str, float]) -> Tuple[float, float]:
        """缩放点坐标"""
        return p["x"] * self.scale_x, p["y"] * self.scale_y

    def _trigger_hits(self, box: Tuple[float, float, float, float]) -> List[Dict]:
        """判断一个框是否命中任意触发线，返回命中的触发线列表"""
        x1, y1, x2, y2 = box
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        w = max(1.0, x2 - x1)
        h = max(1.0, y2 - y1)
        threshold = 0.5 * min(w, h)  # 距离阈值
        hits = []
        
        for trig in self.triggers:
            pts = trig.get("points", [])
            for i in range(len(pts) - 1):
                x3, y3 = self._scale_point(pts[i])
                x4, y4 = self._scale_point(pts[i + 1])
                dist = point_to_segment_distance(cx, cy, x3, y3, x4, y4)
                if dist <= threshold:
                    hits.append(trig)
                    break
        
        return hits

    def _locate_lane(self, box: Tuple[float, float, float, float]) -> Optional[Dict]:
        """
        使用配置的检测点判断落在哪个车道多边形内
        
        参数:
            box: (x1, y1, x2, y2) 坐标
            
        返回:
            车道信息，如果未找到返回 None
        """
        x1, y1, x2, y2 = box
        
        # 根据配置选择检测点
        if self.lane_detection_point == "center":
            # 中心点
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        elif self.lane_detection_point == "top_center":
            # 上边沿中心点
            cx, cy = (x1 + x2) / 2, y1
        elif self.lane_detection_point == "bottom_center":
            # 下边沿中心点
            cx, cy = (x1 + x2) / 2, y2
        else:
            # 默认使用中心点
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        
        for lane in self.lanes:
            poly = [{"x": p["x"] * self.scale_x, "y": p["y"] * self.scale_y} for p in lane.get("points", [])]
            if len(poly) >= 3 and point_in_polygon((cx, cy), poly):
                return lane
        
        return None

    # @staticmethod
    # def _hex_to_bgr(hex_color: str) -> Tuple[int, int, int]:
    #     """'#rrggbb' 转 BGR（保留但可能不再使用）"""
    #     hex_color = hex_color.lstrip('#')
    #     if len(hex_color) != 6:
    #         return (0, 255, 0)
    #     r = int(hex_color[0:2], 16)
    #     g = int(hex_color[2:4], 16)
    #     b = int(hex_color[4:6], 16)
    #     return (b, g, r)

    def process_boxes(self, boxes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        处理输入的检测框，返回命中触发线的框信息
        
        参数:
            boxes: 检测框列表，每个框包含以下字段:
                - box: (x1, y1, x2, y2) 坐标
                - class_id: 类别ID（可选）
                - class_name: 类别名称（可选）
                - track_id: 跟踪ID（可选）
                - timestamp_ms: 时间戳（可选）
                - 其他自定义字段
        
        返回:
            触发的框列表，每个框包含原始字段加上:
                - lane_name: 车道名称
                - lane_number: 车道编号
                - trigger_name: 触发线名称
        
        说明:
            使用的车道检测点由构造函数中的 lane_detection_point 参数决定，
            可选值: "center" (中心点), "top_center" (上边沿中心点), "bottom_center" (下边沿中心点)
        """
        triggered_boxes = []
        
        for box_info in boxes:
            box = box_info["box"]
            track_id = box_info['track_id']

            hits = self._trigger_hits(box)
            
            if not hits:
                continue
            
            # 查找所在车道
            lane = self._locate_lane(box)

            if not lane:
                continue
            
            # 记录所有命中的触发线
            for trig in hits:
                result = box_info.copy()
                result.update({
                    "lane_name": lane.get("name") if lane else None,
                    "lane_number": lane.get("number") if lane else None,
                    "trigger_name": trig.get("name", "trigger"),
                    "status": "triggered" if track_id not in self.used_track_ids else "ongoing"
                })
                triggered_boxes.append(result)
                
                if track_id not in self.used_track_ids:
                    self.used_track_ids.add(track_id)
                    while len(self.used_track_ids) >= self.max_track_ids:
                        self.used_track_ids.pop()
        
        return triggered_boxes

    def get_lanes(self) -> List[Dict]:
        """获取所有车道信息"""
        return self.lanes
    
    def get_triggers(self) -> List[Dict]:
        """获取所有触发线信息"""
        return self.triggers