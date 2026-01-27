#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DataAdapter Class for handling image and event data from various sources.

Features:
1. Output image and event data
2. Support RTSP URL for direct camera access or parsing CameraFrame from Apollo Cyber records
3. Support subscribing to Apollo Cyber channels for events or parsing BaseEvents from records
"""

import queue
from abc import ABC, abstractmethod
from typing import Optional, Tuple, Callable
import time
import threading
import numpy as np
import cv2
from backend.utils.log_util import logger
from backend.scripts.record_source import RecordSource
from backend.scripts.simpl_data_process import handle_event_region_attr
try:
    from cyber_record.record import Record
    from cyber_py3 import cyber
    from proto.inno_event_pb2 import BaseEvents, TRIGGER
    from proto.region_pb2 import EventRegionAttribute
    from proto.drivers_pb2 import PointCloud2
    from backend.modules.common_modules import BoxData
    from backend.modules.camera_modules import ImageData
    from backend.modules.simpl_modules import EventData
except ImportError as e:
    logger.error(f"Failed to import cyber module: {e}")
    logger.info("Running in limited mode without cyber support")


class CameraSource(ABC):
    """Abstract base class for camera sources"""

    @abstractmethod
    def get_image(self) -> Optional[ImageData]:
        """Get the next image from the source"""
        pass

    @abstractmethod
    def release(self):
        """Release the camera source"""
        pass


class RtspCameraSource(CameraSource):
    """Camera source from RTSP URL"""

    def __init__(self, rtsp_url: str):
        self.rtsp_url = rtsp_url
        self.cap = cv2.VideoCapture(rtsp_url)
        if not self.cap.isOpened():
            raise RuntimeError(f"Failed to open RTSP stream: {rtsp_url}")

        # Create a queue for caching image data
        # Limit queue size to 10 frames
        self.image_queue = queue.Queue(maxsize=10)
        self.is_running = True

        # Start a thread for capturing images
        self.capture_thread = threading.Thread(target=self._capture_loop)
        self.capture_thread.daemon = True
        self.capture_thread.start()

    def _capture_loop(self):
        """Internal thread for capturing images from RTSP stream"""
        while self.is_running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.1)  # Small delay if frame read fails
                continue

            timestamp_ms = int(time.time() * 1e3)  # milliseconds
            height, width, channels = frame.shape

            image_data = ImageData(
                timestamp_ms=timestamp_ms,
                timestamp_ms_local=timestamp_ms,
                image=frame,
                width=width,
                height=height,
                channels=channels
            )

            # Add to queue, removing oldest frame if full
            try:
                self.image_queue.put_nowait(image_data)
            except queue.Full:
                # Remove oldest frame
                self.image_queue.get_nowait()
                self.image_queue.put_nowait(image_data)

            # Small delay to control capture rate
            # time.sleep(0.033)  # ~30 FPS

    def get_image(self) -> Optional[ImageData]:
        """Get the latest image data from the queue"""
        if self.image_queue.empty():
            return None

        # Get the latest image by clearing the queue except for the last frame
        latest_image = None
        while not self.image_queue.empty():
            latest_image = self.image_queue.get_nowait()

        return latest_image

    def release(self):
        """Stop the capture thread and release resources"""
        self.is_running = False

        # Only join the capture thread if it exists and is alive
        if hasattr(self, 'capture_thread') and self.capture_thread.is_alive():
            # Add timeout to avoid blocking
            self.capture_thread.join(timeout=1.0)

        # Only release the capture if it's open
        try:
            if self.cap.isOpened():
                self.cap.release()
        except Exception as e:
            logger.error(f"Error releasing RTSP capture: {e}")

        # Clear the queue safely
        try:
            while not self.image_queue.empty():
                self.image_queue.get_nowait()
        except Exception as e:
            logger.error(f"Error clearing image queue: {e}")


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

    def __init__(self, channel_name: str = None,  pointcloud_channel_name: str = None, event_type: int = EventRegionAttribute.FLOW_EVENT):
        if channel_name is None:
            raise ValueError("channel_name must be provided")

        self.channel_name = channel_name
        self.pointcloud_channel_name = pointcloud_channel_name
        self.subscribed = True
        self.event_type = event_type
        # Queue for storing event data with a maximum size to prevent unbounded growth
        self.event_queue = queue.Queue(maxsize=1000)
        self.pointcloud_queue = queue.Queue(maxsize=10)
        self.event_reader = None
        self.pointcloud_reader = None

        # Initialize cyber and create node
        cyber.init()
        self.cyber_node = cyber.Node("validation_tool_node")
        self.event_reader = self.cyber_node.create_reader(
            self.channel_name, BaseEvents, self._event_callback)

        if self.pointcloud_channel_name is not None:
            self.pointcloud_reader = self.cyber_node.create_reader(
                self.pointcloud_channel_name, PointCloud2, self._pointcloud_callback)

    def set_channel_name(self, channel_name: str = None, pointcloud_channel_name: str = None):
        # if not cyber.ok():
        #     raise RuntimeError("Cyber is not initialized.")
        if channel_name is not None:
            self.channel_name = channel_name
            self.event_reader = self.cyber_node.create_reader(
                self.channel_name, BaseEvents, self._event_callback)
        if pointcloud_channel_name is not None:
            self.pointcloud_channel_name = pointcloud_channel_name
            self.pointcloud_reader = self.cyber_node.create_reader(
                self.pointcloud_channel_name, PointCloud2, self._pointcloud_callback)

    def _event_callback(self, msg: BaseEvents):
        """Callback function for processing received events and queuing them"""
        # Process the message and convert it to EventData
        # print(f"Received event message with {len(msg.base_events)} base events")

        for base_event in msg.base_events:
            if base_event.event_region_attr != self.event_type:
                continue
            handle = handle_event_region_attr(base_event.event_region_attr)
            event = handle(base_event.serialized_msg)

            # entry point
            if event.common_event.status != TRIGGER:
                continue

            # search pointcloud
            pointcloud_data = None
            while not self.pointcloud_queue.empty():
                pointcloud_data = self.pointcloud_queue.get_nowait()
                if pointcloud_data.idx >= event.common_event.frame_id:
                    break

            if pointcloud_data is not None:
                print(f'match pointcloud {pointcloud_data.idx}, \
                      point core struct size: {len(pointcloud_data.point_core) / pointcloud_data.point_size},\
                        point supplement struct size: {len(pointcloud_data.point_supplement) / pointcloud_data.point_size}')

            # Create EventData object
            event_data = EventData(
                timestamp_ms=event.common_event.timestamp_ms,
                timestamp_ms_local=int(time.time() * 1e3),
                region_name=event.common_event.region_name,
                region_id=event.common_event.region_id,
                box=None,
                pointcloud=pointcloud_data
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
                    track_id=event.common_event.boxes[0].track_id,
                    lane_id=event.common_event.boxes[0].lane_id
                )
            else:
                logger.error(
                    f"Event {event.common_event.event_id} has no boxes")

            # Add to queue, removing oldest item if queue is full
            try:
                self.event_queue.put_nowait(event_data)
            except queue.Full:
                try:
                    # Remove oldest item
                    self.event_queue.get_nowait()
                    # Add new item
                    self.event_queue.put_nowait(event_data)
                except queue.Empty:
                    # Queue was empty despite being full, just add the item
                    self.event_queue.put_nowait(event_data)

    def _pointcloud_callback(self, msg: PointCloud2):
        """Callback function for processing received pointclouds and queuing them"""
        # Add to queue, removing oldest item if queue is full
        try:
            self.pointcloud_queue.put_nowait(msg)
        except queue.Full:
            try:
                # Remove oldest item
                self.pointcloud_queue.get_nowait()
                # Add new item
                self.pointcloud_queue.put_nowait(msg)
            except queue.Empty:
                # Queue was empty despite being full, just add the item
                self.pointcloud_queue.put_nowait(msg)

    def get_events(self) -> Optional[EventData]:
        """Get the oldest event data from the queue"""
        if not self.subscribed:
            return None

        # Return queued data if available
        try:
            return self.event_queue.get_nowait()
        except queue.Empty:
            return None

    def release(self):
        self.subscribed = False
        cyber.shutdown()

    def _cvt_pointcloud_to_image(self, pointcloud: PointCloud2) -> np.ndarray:
        """Convert PointCloud2 message to numpy array"""


class DataAdapter:
    """
    Data Adapter class for handling image and event data from various sources.
    Supports online mode (RTSP + event channel) and offline mode (record file).
    """

    def __init__(self):
        self.camera_source: Optional[CameraSource] = None
        self.event_source: Optional[EventSource] = None
        self.record_source: Optional[RecordSource] = None
        self.is_running = False
        self.image_callback: Optional[Callable[[ImageData], None]] = None
        self.event_callback: Optional[Callable[[EventData], None]] = None
        self.mode = None

    def set_image_callback(self, callback: Callable[[ImageData], None]):
        """Set callback function for receiving image data"""
        self.image_callback = callback

    def set_event_callback(self, callback: Callable[[EventData], None]):
        """Set callback function for receiving event data"""
        self.event_callback = callback

    def set_online_mode(self, rtsp_url: str = None, event_channel: str = None, pointcloud_channel: str = None, event_type: int = EventRegionAttribute.FLOW_EVENT):
        """Set adapter to online mode (RTSP + event channel)"""
        self.mode = "online"
        # self._clear_sources()
        self.stop()
        if rtsp_url is None and event_channel is None:
            logger.error(
                "RTSP URL and event channel cannot be None at the same time")
            return
        if rtsp_url is not None:
            self.camera_source = RtspCameraSource(rtsp_url)
        if event_channel is not None:
            if self.event_source is None:
                self.event_source = ChannelEventSource(
                    event_channel, pointcloud_channel, event_type)
            else:
                self.event_source.set_channel_name(
                    event_channel, pointcloud_channel)

    def set_offline_mode(self, record_path: str, camera_channel: str = None, event_channel: str = None, event_type: int = EventRegionAttribute.FLOW_EVENT, fps: int = None):
        """Set adapter to offline mode (record file)"""
        self.mode = "offline"
        # self._clear_sources()
        self.stop()
        self.record_source = RecordSource(
            record_path, camera_channel=camera_channel, event_channel=event_channel, event_type=event_type, fps=fps)

    def run(self, sync: bool = False):
        """
        Run the data adapter based on the current mode in a separate thread.
        - Online mode: Continuously get data from sources and call callbacks
        - Offline mode: Process the record file and call callbacks

        This method starts the processing in a new thread and returns immediately,
        allowing the main thread to continue its execution.
        """
        if self.mode is None:
            logger.error(
                "Mode not set. Please call set_online_mode or set_offline_mode first.")
            return

        if self.is_running:
            logger.warning("DataAdapter is already running")
            return

        # Set running flag
        self.is_running = True

        # Register signal handlers for graceful shutdown
        # def signal_handler(sig, frame):
        #     logger.info(f"Received signal {sig}. Stopping DataAdapter...")
        #     self.stop()

        # signal.signal(signal.SIGINT, signal_handler)
        # signal.signal(signal.SIGTERM, signal_handler)

        # Create and start the processing thread
        if sync:
            self._run_with_mode()
        else:
            self.processing_thread = threading.Thread(
                target=self._run_with_mode)
            self.processing_thread.daemon = True  # Thread will exit when main thread exits
            self.processing_thread.start()

        logger.info(f"Started {self.mode} mode in background thread")

    def _run_with_mode(self):
        """Internal method that runs in a separate thread and executes the appropriate processing logic"""
        try:
            if self.mode == "online":
                self._run_online()
            elif self.mode == "offline":
                self._run_offline()
            else:
                logger.error(f"Unknown mode: {self.mode}")
        except Exception as e:
            logger.error(f"Error in processing thread: {e}")
        finally:
            # Ensure running flag is reset even if an error occurs
            self.is_running = False
            logger.info(f"Stopped {self.mode} mode processing thread")

    def _run_online(self):
        """Run in online mode - continuously process streaming data"""
        logger.info("Running in online mode")

        if not self.camera_source and not self.event_source:
            logger.error("No sources configured for online mode")
            return

        try:
            # Continuously process data while running flag is true
            while self.is_running:
                image_data, event_data = self._get_online_data()

                # Call image callback if provided and data is available
                if self.image_callback and image_data:
                    self.image_callback(image_data)

                # Call event callback if provided and data is available
                if self.event_callback and event_data:
                    self.event_callback(event_data)

                # Small delay to prevent busy looping
                # time.sleep(0.033)  # ~30 FPS
        except KeyboardInterrupt:
            logger.info("Online mode stopped by user")
        except Exception as e:
            logger.error(f"Error in online mode: {e}")
        finally:
            self._release_sources()

    def _run_offline(self):
        """Run in offline mode - process record file"""
        logger.info("Running in offline mode")

        if not self.record_source:
            logger.error("No record source configured for offline mode")
            return

        try:
            # Set callbacks for the record source if not already set
            if self.image_callback:
                self.record_source.set_camera_call_back(self.image_callback)
            if self.event_callback:
                self.record_source.set_event_call_back(self.event_callback)

            # Process the record file
            self.record_source.run()
            logger.info("Offline mode processing complete")
        except Exception as e:
            logger.error(f"Error in offline mode: {e}")
        finally:
            self._release_sources()

    def _get_online_data(self) -> Tuple[Optional[ImageData], Optional[EventData]]:
        """Get data from online sources"""
        image_data = None
        event_data = None

        if self.camera_source:
            image_data = self.camera_source.get_image()

        if self.event_source:
            event_data = self.event_source.get_events()

        return image_data, event_data

    def stop(self):
        """
        Stop the data adapter processing thread.
        This method can be called to stop both online and offline mode processing.
        """
        if not self.is_running:
            logger.info("DataAdapter is not running")
            return

        logger.info("Stopping DataAdapter processing")

        # Set running flag to false to signal the processing thread to stop
        self.is_running = False

        if self.record_source:
            # Stop the record source if it's running
            if hasattr(self.record_source, 'stop'):
                self.record_source.stop()

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

        # Release all sources
        # self._release_sources()

    def _clear_sources(self):
        """Clear all existing sources"""
        self.stop()  # Ensure processing is stopped before clearing sources
        self._release_sources()
        self.camera_source = None
        self.event_source = None
        self.record_source = None

    def _release_sources(self):
        """Release resources for all sources"""
        if self.camera_source:
            self.camera_source.release()
        if self.event_source:
            self.event_source.release()
        if self.record_source:
            self.record_source.release()


# Example usage
if __name__ == "__main__":
    # Create data adapter
    adapter = DataAdapter()

    # Define callbacks for all examples
    def image_callback(image_data):
        print(f"Image processed at {image_data.timestamp_ms} ms")
        # save image to disk
        # cv2.imwrite(f"image_{image_data.timestamp_ms}.jpg", image_data.image)

    def event_callback(event_data):
        print(
            f"Event in region {event_data.region_name} at {event_data.timestamp_ms} ms")

    # Example 1: Online mode using run method
    # print("Example 1: Online mode using run method (press Ctrl+C to stop)")
    try:
        # Set callbacks
        adapter.set_image_callback(image_callback)
        adapter.set_event_callback(event_callback)

        # Configure online mode with RTSP and event channel
        adapter.set_online_mode(
            event_channel="omnisense/event/172.30.0.3_1/events")

        # Run in online mode (this will block until interrupted)
        # Note: Uncomment the next line to actually run
        adapter.run(sync=True)
        print("Online mode run method configured (commented out for example)")
    except Exception as e:
        print(f"Error in example 1: {e}")

    # # Example 2: Offline mode using run method
    # print("\nExample 2: Offline mode using run method")
    # try:
    #     # Set callbacks
    #     adapter.set_image_callback(image_callback)
    #     adapter.set_event_callback(event_callback)

    #     # Configure offline mode with record file
    #     adapter.set_offline_mode("./1765877996291.record.00000", event_channel="replay_omnisense/event/01/events")

    #     # Run in offline mode (this will process the entire file)
    #     # Note: Uncomment the next line to actually run
    #     adapter.run(sync=True)
    #     print("Offline mode run method configured (commented out for example)")
    # except Exception as e:
    #     print(f"Error in example 2: {e}")
