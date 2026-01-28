from abc import ABC, abstractmethod
from typing import Optional
import queue
import numpy as np
import cv2
from backend.modules.simpl_modules import *
from backend.utils.log_util import logger

from proto.region_pb2 import EventRegionAttribute
from cyber_py3 import cyber
from proto.inno_event_pb2 import BaseEvents, TRIGGER
from proto.drivers_pb2 import PointCloud2
from proto.inno_box_pb2 import Boxes
from backend.utils.safe_queue import SafeQueue

from backend.scripts.simpl_data_process import (
    handle_base_event, handle_compressed_points, handle_pointscloud2_to_numpy)
from backend.utils.points_to_img import (
    pointcloud_to_image, encode_image_to_jpeg)


class EventSource(ABC):
    """Abstract base class for event sources"""

    @abstractmethod
    def get_events(self) -> Optional[EventData]:
        """Get the next event data from the source"""
        pass

    @abstractmethod
    def release(self):
        """Release the event source"""
        pass


class ChannelEventSource(EventSource):
    """Event source from Apollo Cyber channel subscription"""

    def __init__(self, event_channel_name: str = None,
                 pointcloud_channel_name: str = None,
                 boxes_channel_name: str = None,
                 event_type: int = EventRegionAttribute.FLOW_EVENT):
        self.event_channel_name = event_channel_name
        self.pointcloud_channel_name = pointcloud_channel_name
        self.boxes_channel_name = boxes_channel_name
        self._init_support_channel()
        self.subscribed = True
        self.event_type = event_type

    def _init_cyber_node(self):
        # Initialize cyber and create node
        cyber.init()
        self.cyber_node = cyber.Node("validation_tool_node")
        self._init_reader(self.event_channel_name,
                          self.pointcloud_channel_name, self.boxes_channel_name)

    def _init_reader(self, event_channel_name: str = None,
                     pointcloud_channel_name: str = None,
                     boxes_channel_name: str = None):
        if event_channel_name is not None:
            self.event_channel_name = event_channel_name
            self.event_reader = self.cyber_node.create_reader(
                self.event_channel_name, BaseEvents, self._event_callback)
        if pointcloud_channel_name is not None:
            self.pointcloud_channel_name = pointcloud_channel_name
            self.pointcloud_reader = self.cyber_node.create_reader(
                self.pointcloud_channel_name, PointCloud2, self._pointcloud_callback)
        if boxes_channel_name is not None:
            self.boxes_channel_name = boxes_channel_name
            self.boxes_reader = self.cyber_node.create_reader(
                self.boxes_channel_name, Boxes, self._boxes_callback)

    def _init_support_channel(self):
        if self.event_channel_name is None:
            raise ValueError("event_channel_name must be provided")
        self.event_reader = None
        self.pointcloud_reader = None
        self.boxes_reader = None
        self.event_queue = SafeQueue(maxsize=10, name="event_queue")
        self.pointcloud_queue = SafeQueue(maxsize=10, name="pointcloud_queue")
        self.boxes_queue = SafeQueue(maxsize=10, name="boxes_queue")

    def set_channel_name(self, event_channel_name: str = None,
                         pointcloud_channel_name: str = None,
                         boxes_channel_name: str = None):
        self._init_reader(event_channel_name,
                          pointcloud_channel_name, boxes_channel_name)

    def _boxes_callback(self, msg: Boxes):
        return None

    def _event_callback(self, msg: BaseEvents):
        """Callback function for processing received events and queuing them"""
        # Process the message and convert it to EventData
        # print(f"Received event message with {len(msg.base_events)} base events")
        events = []
        for base_event in msg.base_events:
            event_data = handle_base_event(base_event)
            if event_data is None:
                continue
            events.append(event_data)
        self.event_queue.put(events)

    def _pointcloud_callback(self, msg):
        """Callback function for processing received pointclouds and queuing them"""
        type_name = msg.DESCRIPTOR.full_name
        if type_name in RECORD_MSG_TYPE and RECORD_MSG_TYPE[type_name] == "points":
            if "trig_recorder" in type_name:
                new_msg = handle_compressed_points(msg)
            else:
                new_msg = msg
            points_data = code_pd2_pd(new_msg)
            self.pointcloud_queue.put(points_data)

    def get_points_image(self) -> Optional[bytes]:
        if not self.subscribed:
            return None

        # Return queued data if available
        try:
            points_msg = self.pointcloud_queue.get()
            points_np = handle_pointscloud2_to_numpy(points_msg)
            image = pointcloud_to_image(points_np)
            return encode_image_to_jpeg(image)
        except queue.Empty:
            return None

    def get_points(self) -> Optional[PointCloud2]:
        if not self.subscribed:
            return None
        return self.pointcloud_queue.get()

    def get_events(self) -> Optional[EventData]:
        """Get the oldest event data from the queue"""
        if not self.subscribed:
            return None
        return self.event_queue.get()

    def get_boxes(self) -> Optional[Boxes]:
        """Get the oldest event data from the queue"""
        if not self.subscribed:
            return None
        return self.boxes_queue.get()

    def get_frame(self) -> Optional[FrameData]:
        if not self.subscribed:
            return None
        event_data = self.get_events()
        points_data = self.get_points()
        if (event_data.timestamp_ms - points_data.timestamp_ms) > 100:
            logger.warning(
                f"Ttimestamp gap = event_data - pointcloud =  {event_data.timestamp_ms} - {points_data.timestamp_ms} = {event_data.timestamp_ms - points_data.timestamp_ms} ms > 100 ms, drop this points_data")
            points_data = None
        if (event_data.timestamp_ms_local - points_data.timestamp_ms_local) > 100:
            logger.warning(
                f"Ttimestamp gap = event_data - pointcloud =  {event_data.timestamp_ms_local} - {points_data.timestamp_ms_local} = {event_data.timestamp_ms_local - points_data.timestamp_ms_local} ms > 100 ms, drop this points_data")
            points_data = None
        return FrameData(
            timestamp_ms=event_data.timestamp_ms,
            timestamp_ms_local=event_data.timestamp_ms_local,
            points=points_data,
            events=event_data,
            boxes=self.get_boxes(),
        )

    def release(self):
        self.subscribed = False
        cyber.shutdown()
