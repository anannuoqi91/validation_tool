from typing import Callable
import time
import numpy as np
from backend.utils.log_util import logger
from backend.scripts.simpl_data_process import handle_event_region_attr
from backend.modules.common_modules import BoxData

try:
    from cyber_record.record import Record
    from cyber_py3 import cyber
    from proto.inno_event_pb2 import TRIGGER
    from proto.region_pb2 import EventRegionAttribute
    from proto.camera_pb2 import DataFormat
    from backend.modules.camera_modules import ImageData
    from backend.modules.simpl_modules import EventData
except ImportError as e:
    logger.error(f"Failed to import cyber module: {e}")
    logger.info("Running in limited mode without cyber support")


RECORD_MSG_TYPE = {
    "omnividi.event.BaseEvent": "event",
    "omnividi.event.BaseEvents": "event",
    "omnividi.box.Boxes": "box",
    "omnividi.camera.CameraFrame": "camera",
    "omnividi.trig_recorder.CompressedMsg": "points_compress",
    "omnividi.drivers.PointCloud2": "points"
}


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
        self.frame_interval = 1.0 / fps if fps is not None else 0  # seconds per frame

        # Initialize record reader
        self._init_reader(record_path)
        self._init_msg_type()
        self._init_channels()

    def _init_msg_type(self):
        self.camera_msg_type = "omnividi.camera.CameraFrame"
        self.event_msg_type = "omnividi.event.BaseEvents"

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

            if self.camera_channel == channel_name or \
                    (self.camera_channel is None and message.DESCRIPTOR.full_name == self.camera_msg_type):
                image_data = self._parse_camera(message)

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

            elif self.event_channel == channel_name or \
                    (self.event_channel is None and message.DESCRIPTOR.full_name == self.event_msg_type):
                base_events = message
                # base_events.ParseFromString(msg)

                for base_event in base_events.base_events:
                    if base_event.event_region_attr != self.event_type:
                        continue
                    handle = handle_event_region_attr(
                        base_event.event_region_attr)
                    event = handle(base_event.serialized_msg)

                    # entry point
                    if event.common_event.status != TRIGGER:
                        continue

                    # Create EventData object
                    event_data = EventData(
                        timestamp_ms=event.common_event.timestamp_ms,
                        timestamp_ms_local=int(time.time() * 1e3),
                        region_name=event.common_event.region_name,
                        region_id=event.common_event.region_id,
                        box=None
                    )

                    if len(event.common_event.boxes) > 0:
                        event_data.box = BoxData(
                            position_x=event.common_event.boxes[0].x,
                            position_y=event.common_event.boxes[0].y,
                            position_z=event.common_event.boxes[0].z,
                            length=event.common_event.boxes[0].length,
                            width=event.common_event.boxes[0].width,
                            height=event.common_event.boxes[0].height,
                            object_type=event.common_event.boxes[0].object_type,
                            track_id=event.common_event.boxes[0].track_id
                        )
                    else:
                        logger.error(
                            f"Event {event.common_event.event_id} has no boxes")

                    # Call callback if provided
                    if self.event_call_back:
                        self.event_call_back(event_data)
                    else:
                        logger.error(f"Event callback not set!")

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

    def _parse_events(self, message):
        """Parse event messages"""
        for channel_name, msg, timestamp in self.record_reader.read_messages(self._channels):
            if channel_name == self.event_channel:
                self._handle_event(msg, timestamp)

    def _parse_camera(self, msg):
        """Parse camera messages"""
        image_data = ImageData(
            timestamp_ms=msg.timestamp_ns / 1000000,
            timestamp_ms_local=int(time.time() * 1e3),
            width=None,
            height=None,
            channels=None,
            image=None
        )

        if msg.data_format == DataFormat.OPENCV:
            image_data.width = msg.cols
            image_data.height = msg.rows
            image_data.channels = msg.channels
            image_data.image = np.frombuffer(
                msg.data, dtype=np.uint8)
            image_data.image = image_data.image.reshape(
                (msg.rows, msg.cols, msg.channels))
        else:
            logger.error(
                f"Unsupported data format: {msg.data_format}")
        return image_data

    @staticmethod
    def channel_match(channels):
        out = {}
        for channel in channels:
            if channel.message_type in RECORD_MSG_TYPE:
                out[channel.name] = RECORD_MSG_TYPE[channel.message_type]
            else:
                out[channel.name] = channel.message_type
        return out
