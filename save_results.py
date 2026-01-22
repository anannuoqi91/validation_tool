#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SaveResults Class for handling and saving matched results from Matcher class.

Features:
1. Save matched results to Excel file
2. Save images from ImageData to local files
3. Organize saved data with timestamps and region names
"""

import os
import cv2
import pandas as pd
from datetime import datetime
from typing import List, Tuple, Optional
from dataclasses import dataclass
import numpy as np
import threading

# Import the data classes from data_adapter
from data_adapter import ImageData, EventData
from parse_pointcloud import parse_point_cloud

@dataclass
class MatchedResult:
    """Container for matched ImageData and EventData"""
    image_data: ImageData
    event_data: EventData
    match_score: Optional[float] = None

class SaveResults:
    """Class for saving matched results to Excel and images"""
    
    def __init__(self, output_dir: str = "results"):
        """
        Initialize the SaveResults class
        
        Args:
            output_dir: Directory to save results (Excel and images)
        """
        # Use absolute path for output directory
        self.output_dir = os.path.abspath(output_dir)
        self.images_dir = os.path.join(self.output_dir, "images")
        self.excel_file = os.path.join(self.output_dir, "matched_results.xlsx")
        self.results_data = []  # 用于存储已保存到Excel的结果数据
        self.pending_save_data = []  # 用于存储待保存的数据
        
        # Create output directories if they don't exist
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.images_dir, exist_ok=True)
        
        # 线程控制
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.is_running = True
        self.save_thread = threading.Thread(target=self._save_worker)
        self.save_thread.daemon = True
        self.save_thread.start()
    
    def _save_pointcloud(self, event_data: EventData) -> str:
        if event_data.pointcloud is None:
            return ''
        points = parse_point_cloud(event_data.pointcloud.point_core, event_data.pointcloud.point_supplement) 
        print(f'get pointcloud: {len(points)}, points_size:{event_data.pointcloud.point_size}')
        
        # 点云俯视图投影参数
        resolution = 0.1  # 0.1米/像素
        image_size = (800, 800)  # 图像大小
        center_x = image_size[0] // 2
        center_y = image_size[1] // 2
        
        # 创建空白图像
        image = np.zeros((image_size[1], image_size[0], 3), dtype=np.uint8)
        
        # 绘制点云点
        for point in points:
            # 将3D坐标投影到2D俯视图
            x = int(point.y / resolution) + center_x
            y = int(point.z / resolution) + center_y
            
            # 检查点是否在图像范围内
            if 0 <= x < image_size[0] and 0 <= y < image_size[1]:
                # 使用点的强度作为颜色
                intensity = min(255, max(0, point.intensity))
                cv2.circle(image, (x, y), 1, (intensity, intensity, intensity), -1)
        
        # 绘制box
        if event_data.box:
            box = event_data.box
            
            # 计算box的四个角点（俯视图只需要x-y平面的坐标）
            half_length = box.length / 2
            half_width = box.width / 2
            
            # 计算box的四个角点
            corners = [
                (box.position_y - half_width, box.position_z - half_length),
                (box.position_y + half_width, box.position_z - half_length),
                (box.position_y + half_width, box.position_z + half_length),
                (box.position_y - half_width, box.position_z + half_length)
            ]
            
            # 将3D角点坐标投影到2D图像
            image_corners = []
            for x, y in corners:
                img_x = int(x / resolution) + center_x
                img_y = int(y / resolution) + center_y
                image_corners.append((img_x, img_y))
            
            # 绘制box边框
            image_corners = np.array(image_corners, np.int32)
            image_corners = image_corners.reshape((-1, 1, 2))
            cv2.polylines(image, [image_corners], True, (0, 255, 0), 2)
            
            # 添加box信息文本
            text = f"ID: {box.track_id}, Type: {box.object_type}"
            cv2.putText(image, text, (image_corners[0][0][0], image_corners[0][0][1] - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        
        # 保存图像
        timestamp_str = datetime.fromtimestamp(event_data.timestamp_ms / 1000).strftime("%Y%m%d_%H%M%S_%f")
        region_name = event_data.region_name or "unknown_region"
        pc_filename = f"{region_name}_{timestamp_str}_pc.jpg"
        pc_path = os.path.join(self.images_dir, pc_filename)
        
        cv2.imwrite(pc_path, image)
        print(f"Pointcloud top-view saved to: {pc_path}")
        
        return pc_path

    def add_matched_result(self, image_data: ImageData, event_data: EventData):
        """
        Add a matched result to the results list
        
        Args:
            image_data: The ImageData object from the match
            event_data: The EventData object from the match
            match_score: Optional match score for the pair
        """
        # 只缓存数据，不立即保存图片
        self.results_data.append({
            'image_data': image_data,
            'event_data': event_data
        })
        print("Matched result added to cache")
    
    def _save_image(self, image_data: ImageData) -> str:
        """
        Save the image from ImageData to a file
        
        Args:
            image_data: The ImageData object containing the image
            
        Returns:
            The filename of the saved image
        """
        # Generate a unique filename based on timestamp and region
        timestamp_str = datetime.fromtimestamp(image_data.timestamp_ms / 1000).strftime("%Y%m%d_%H%M%S_%f")
        region_name = image_data.region_name or "unknown_region"
        image_filename = f"{region_name}_{timestamp_str}.jpg"
        image_path = os.path.join(self.images_dir, image_filename)
        
        # Save the image using OpenCV
        cv2.imwrite(image_path, image_data.image)
        
        return image_path
    
    def save_to_excel(self):
        """
        Save all accumulated results to Excel file
        """
        if not self.results_data:
            print("No results to save to Excel")
            return
        
        # Create a DataFrame from the results data
        df = pd.DataFrame(self.results_data)
        
        # Save to Excel file with hyperlinks
        with pd.ExcelWriter(self.excel_file, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Matched Results')
            
            # Get the worksheet
            worksheet = writer.sheets['Matched Results']
            
            # Find column indices for 'image_filename' and 'pointcloud_filename'
            image_col_index = None
            pointcloud_col_index = None
            for col_idx, col_name in enumerate(worksheet.iter_cols(1, worksheet.max_column)):
                col_value = col_name[0].value
                if col_value == 'image_filename':
                    image_col_index = col_idx + 1  # Excel columns are 1-indexed
                elif col_value == 'pointcloud_filename':
                    pointcloud_col_index = col_idx + 1
            
            # Add hyperlinks to image filenames
            if image_col_index:
                for row_idx in range(2, worksheet.max_row + 1):  # Start from row 2 (header is row 1)
                    cell = worksheet.cell(row=row_idx, column=image_col_index)
                    image_path = cell.value
                    if image_path:
                        # Set hyperlink directly using the absolute path
                        cell.hyperlink = image_path
                        # Set hyperlink style (blue text, underline)
                        cell.style = 'Hyperlink'
            
            # Add hyperlinks to pointcloud filenames
            if pointcloud_col_index:
                for row_idx in range(2, worksheet.max_row + 1):  # Start from row 2 (header is row 1)
                    cell = worksheet.cell(row=row_idx, column=pointcloud_col_index)
                    pointcloud_path = cell.value
                    if pointcloud_path:
                        # Set hyperlink directly using the absolute path
                        cell.hyperlink = pointcloud_path
                        # Set hyperlink style (blue text, underline)
                        cell.style = 'Hyperlink'
        
        print(f"Results saved to Excel: {self.excel_file}")
        print(f"Images saved to: {self.images_dir}")
        print(f"Total matched results saved: {len(self.results_data)}")
    
    def _save_worker(self):
        """
        持续运行的工作线程函数，用于处理保存任务
        """
        print("Save worker thread started")
        
        while self.is_running:

            with self.condition:
                # 等待直到有数据需要保存或线程停止
                while not self.pending_save_data and self.is_running:
                    self.condition.wait(timeout=1.0)  # 1秒超时，定期检查线程状态
                
                if not self.is_running:
                    break
                
                # 复制待保存的数据，释放锁以便继续缓存新数据
                save_data = self.pending_save_data.copy()
                self.pending_save_data.clear()
            
            if not save_data:
                continue
            
            print(f"Processing {len(save_data)} results for saving")
            
            # 准备保存到Excel的数据
            excel_data = []
            
            # 保存图片并准备Excel数据
            for item in save_data:
                image_data = item['image_data']
                event_data = item['event_data']
                
                # 保存图片
                image_path = self._save_image(image_data) if image_data is not None else None
                # image_path = None
                # 保存点云
                # pointcloud_path = self._save_pointcloud(event_data) if event_data is not None else None
                pointcloud_path = None

                print(f"Image saved to: {image_path}")
                
                # 准备Excel数据
                excel_data.append({
                    'image_timestamp_ms': str(image_data.timestamp_ms) if image_data is not None else 'No Data',
                    'image_timestamp_ms_local': str(image_data.timestamp_ms_local) if image_data is not None else 'No Data',
                    'event_timestamp_ms': str(event_data.timestamp_ms) if event_data is not None else 'No Data',
                    'event_timestamp_ms_local': str(event_data.timestamp_ms_local) if event_data is not None else 'No Data',
                    'region_name': image_data.region_name if image_data is not None else event_data.region_name,
                    'image_filename': image_path,
                    'pointcloud_filename': pointcloud_path
                })
            
            # 将新的Excel数据添加到已有的结果数据中
            with self.lock:
                self.results_data.extend(excel_data)
            
            # 执行Excel保存
            self.save_to_excel()
            
            print("Save worker completed processing current batch")
        
        print("Save worker thread stopped")
    
    def save_results(self, results: List[Tuple[ImageData, EventData]]):
        """
        Save a list of matched results
        
        Args:
            results: List of tuples containing (ImageData, EventData, match_score)
        """
        with self.condition:
            # 将结果添加到待保存队列
            for result in results:
                self.pending_save_data.append({
                    'image_data': result['image'],
                    'event_data': result['event']
                })
            
            # 通知工作线程有新数据需要处理
            self.condition.notify()
            
            print(f"Added {len(results)} results to save queue")
    
    def clear_results(self):
        """
        Clear the accumulated results data
        """
        with self.lock:
            self.results_data = []
            self.pending_save_data = []
        print("Results data cleared")
    
    def stop(self):
        """
        停止保存线程
        """
        with self.condition:
            self.is_running = False
            self.condition.notify()
        
        # 等待线程结束
        if self.save_thread and self.save_thread.is_alive():
            self.save_thread.join(timeout=5.0)
        
        print("SaveResults stopped")

# Example usage
if __name__ == "__main__":
    # Create a simple test
    save_results = SaveResults()
    
    # Create test data (in real usage, this would come from Matcher)
    test_image = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(test_image, "Test Image", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    # Import BoxData from data_adapter
    from data_adapter import BoxData
    
    test_image_data = ImageData(
        timestamp_ms=int(datetime.now().timestamp() * 1000),
        timestamp_ms_local=int(datetime.now().timestamp() * 1000),
        image=test_image,
        width=640,
        height=480,
        channels=3,
        region_name="test_region"
    )
    
    # Create a BoxData object for the event
    test_box = BoxData(
        position_x=0.0,
        position_y=0.0,
        position_z=0.0,
        length=2.0,
        width=1.0,
        height=1.5,
        object_type=0,
        track_id=1,
        lane_id=1
    )
    
    test_event_data = EventData(
        timestamp_ms=int(datetime.now().timestamp() * 1000),
        timestamp_ms_local=int(datetime.now().timestamp() * 1000),
        region_name="test_region",
        region_id=1,
        box=test_box
    )
    
    # Add and save the test result
    save_results.add_matched_result(test_image_data, test_event_data)
    save_results.save_to_excel()
    
    print("Test completed successfully")