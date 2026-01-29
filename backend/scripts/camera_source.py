from abc import ABC, abstractmethod
from typing import Optional
import threading
import queue
import time
import cv2
from backend.modules.camera_modules import ImageData
from backend.utils.log_util import logger


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
        self.is_running = True

        # Create a queue for caching image data
        # Limit queue size to 10 frames
        self.image_queue = queue.Queue(maxsize=10)

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
        latest_image = None
        while True:
            try:
                latest_image = self.image_queue.get_nowait()
            except queue.Empty:
                break
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
