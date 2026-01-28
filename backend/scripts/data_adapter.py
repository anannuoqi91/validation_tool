#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DataAdapter Class for handling image and event data from various sources.

Features:
1. Output image and event data
2. Support RTSP URL for direct camera access or parsing CameraFrame from Apollo Cyber records
3. Support subscribing to Apollo Cyber channels for events or parsing BaseEvents from records
"""


from typing import Optional, Tuple, Callable
import threading
from backend.utils.log_util import logger
from backend.scripts.record_source import RecordSource
from backend.scripts.camera_source import *
from backend.scripts.simpl_source import EventSource, ChannelEventSource
from backend.modules.simpl_modules import RECORD_MSG_TYPE
try:
    from cyber_py3 import cyber
    from proto.region_pb2 import EventRegionAttribute
    from backend.modules.camera_modules import ImageData
    from backend.modules.simpl_modules import FrameData
except ImportError as e:
    logger.error(f"Failed to import cyber module: {e}")
    logger.info("Running in limited mode without cyber support")


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
        self.event_callback: Optional[Callable[[FrameData], None]] = None
        self.mode = None

    def set_image_callback(self, callback: Callable[[ImageData], None]):
        """Set callback function for receiving image data"""
        self.image_callback = callback

    def set_event_callback(self, callback: Callable[[FrameData], None]):
        """Set callback function for receiving event data"""
        self.event_callback = callback

    def set_online_mode(self, rtsp_url: str = None, event_channel: str = None, pointcloud_channel: str = None, event_type: int = EventRegionAttribute.FLOW_EVENT, boxes_channel_name: str = None):
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
                    event_channel_name=event_channel, pointcloud_channel_name=pointcloud_channel,
                    boxes_channel_name=boxes_channel_name)

    def set_offline_mode(self, record_path: str, camera_channel: str = None, event_channel: str = None, event_type: int = EventRegionAttribute.FLOW_EVENT, fps: int = None, box_channel: str = None, points_channel: str = None):
        """Set adapter to offline mode (record file)"""
        self.mode = "offline"
        # self._clear_sources()
        self.stop()
        self.record_source = RecordSource(
            record_path, camera_channel=camera_channel, event_channel=event_channel, event_type=event_type, fps=fps, box_channel=box_channel, points_channel=points_channel)

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
                image_data, frame_data = self._get_online_data()

                # Call image callback if provided and data is available
                if self.image_callback and image_data:
                    self.image_callback(image_data)

                # Call event callback if provided and data is available
                event_data = frame_data.event_data
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

    def _get_online_data(self) -> Tuple[Optional[ImageData], Optional[FrameData]]:
        """Get data from online sources"""
        image_data = None
        event_data = None

        if self.camera_source:
            image_data = self.camera_source.get_image()

        if self.event_source:
            event_data = self.event_source.get_frame()

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
