from typing import Callable
import time
import numpy as np
from backend.utils.log_util import logger
from backend.scripts.simpl_data_process import (
    handle_base_event, handle_camera)
from backend.modules.simpl_modules import EventData, RECORD_MSG_TYPE

try:
    from cyber_record.record import Record
    from cyber_py3 import cyber
    from proto.region_pb2 import EventRegionAttribute
    from backend.modules.camera_modules import ImageData
    from backend.modules.simpl_modules import EventData, RECORD_MSG_TYPE
except ImportError as e:
    logger.error(f"Failed to import cyber module: {e}")
    logger.info("Running in limited mode without cyber support")


class RecordSource:
    """Unified source for reading both camera frames and events from Apollo Cyber record files"""

    def __init__(self, record_path: str, camera_channel: str = None,
                 event_channel: str = None, event_type: int = EventRegionAttribute.FLOW_EVENT, fps: int = None, box_channel: str = None, points_channel: str = None):
        self.record_path = record_path
        self.camera_channel = camera_channel
        self.camera_call_back = None
        self.event_channel = event_channel
        self.box_channel = box_channel
        self.points_channel = points_channel
        self.event_type = event_type
        self.event_call_back = None
        self.is_running = False
        self.fps = fps
        # seconds per frame
        self.frame_interval = 1.0 / fps if fps is not None else 0

        # Initialize record reader
        self._init_reader(record_path)
        self._init_channels()

    def _init_channels(self):
        self._channels = []
        if self.camera_channel:
            self._channels.append(self.camera_channel)
        if self.event_channel:
            self._channels.append(self.event_channel)
        if self.box_channel:
            self._channels.append(self.box_channel)
        if self.points_channel:
            self._channels.append(self.points_channel)

    def _init_reader(self, path):
        self.record_reader = None
        try:
            self.record_reader = Record(open(path, 'rb'))
        except Exception as e:
            logger.error(f"Failed to initialize record reader: {e}")
            self.record_reader = None

    def set_camera_call_back(self, camera_call_back: Callable[[ImageData], None]):
        self.camera_call_back = camera_call_back

    def set_event_call_back(self, event_call_back: Callable[[EventData], None]):
        self.event_call_back = event_call_back

    def _msg_type_supported(self, msg_type: str) -> bool:
        if msg_type in RECORD_MSG_TYPE:
            return RECORD_MSG_TYPE[msg_type]
        return None

    def _parse_messages(self):
        """Parse all messages from the record file"""
        last_frame_time = time.time()  # Track time of last processed frame
        for channel_name, message, timestamp in self.record_reader.read_messages(self._channels):
            # Check if we should stop processing
            if not self.is_running:
                break
            if not hasattr(message, 'DESCRIPTOR'):
                logger.error(f"Message {channel_name} has no DESCRIPTOR")
                continue
            msg_type = message.DESCRIPTOR.full_name
            support_bz = self._msg_type_supported(msg_type)
            if support_bz is None:
                continue
            if support_bz == "camera" and \
                    (self.camera_channel == channel_name or self.camera_channel is None):
                image_data = handle_camera(message)
                # Call callback if provided
                if self.camera_call_back:
                    self.camera_call_back(image_data)
                    # Control frame rate if fps is set
                    if self.fps is not None:
                        current_time = time.time()
                        elapsed_time = current_time - last_frame_time
                        if elapsed_time < self.frame_interval:
                            time.sleep(self.frame_interval - elapsed_time)
                        last_frame_time = current_time
                else:
                    logger.error(f"Camera callback not set!")

            elif support_bz == "event" and \
                    (self.event_channel == channel_name or self.event_channel is None):
                base_events = message
                if "BaseEvents" not in msg_type:
                    continue
                for base_event in base_events.base_events:
                    event_data = handle_base_event(base_event, self.event_type)
                    if event_data is None:
                        continue
                    if self.event_call_back:
                        self.event_call_back(event_data)
                    else:
                        logger.error(f"Event callback not set!")
            elif support_bz == "points":
                pass

    def run(self):
        """Start parsing messages"""
        self.is_running = True
        self._parse_messages()
        self.is_running = False

    def stop(self):
        """Stop parsing messages"""
        self.is_running = False

    def release(self):
        """Release resources"""
        # Stop parsing if still running
        self.stop()

    @staticmethod
    def channel_match(channels: list) -> dict:
        out = {}
        for channel in channels:
            if channel["type"] in RECORD_MSG_TYPE:
                out[channel["name"]] = RECORD_MSG_TYPE[channel["type"]]
            else:
                out[channel["name"]] = channel["type"]
        return out
