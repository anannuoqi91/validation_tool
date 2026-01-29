import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional, Any
from ultralytics import YOLO


class Tracker:
    """
    A class that combines object detection with DeepSort tracking.
    """

    def __init__(self,
                 onnx_model_path: str):
        """
        Initialize the Tracker with ObjectDetector and DeepSort.

        Args:
            onnx_model_path (str): Path to the ONNX model file.
            classes_path (str): Path to the YAML file containing class names.
            confidence_threshold (float): Minimum confidence threshold for detections.
            nms_threshold (float): Threshold for Non-Maximum Suppression.
            max_age (int): Maximum number of frames to keep a track without updates.
            n_init (int): Number of consecutive detections needed to initialize a track.
            nn_budget (int): Maximum size of the appearance descriptor gallery.
            device (str): Device to use for inference ("cpu" or "cuda").
        """
        self.track_colors = {}
        self.model = YOLO(onnx_model_path, task='detect')
        self.classes = self.model.names

    def detect_and_track(self, image: np.ndarray) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Perform object detection and tracking on the input image.

        Args:
            image (np.ndarray): Input image in BGR format.

        Returns:
            Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
                - List of detection results from ObjectDetector
                - List of tracking results with track IDs
        """
        result = self.model.track(
            image, persist=True, verbose=False, tracker='models/botsort.yaml', conf=0.5)[0]

        tracking_results = []
        if result.boxes and result.boxes.is_track:
            boxes = result.boxes.xyxy.cpu().tolist()
            track_ids = result.boxes.id.int().cpu().tolist()
            cls = result.boxes.cls.int().cpu().tolist()
            for box, track_id, cls_id in zip(boxes, track_ids, cls):
                tracking_result = {
                    'track_id': track_id,
                    'class_id': cls_id,
                    'class_name': self.classes[cls_id],
                    'box': box
                }
                tracking_results.append(tracking_result)

        return tracking_results

    def draw_tracking_results(self, image: np.ndarray, tracking_results: List[Dict[str, Any]]) -> np.ndarray:
        """
        Draw tracking results on the input image.

        Args:
            image (np.ndarray): Input image in BGR format (will be modified in place).
            tracking_results (List[Dict[str, Any]]): Tracking results from detect_and_track() method.

        Returns:
            np.ndarray: Image with tracking results drawn (same reference as input).
        """
        for tracking_result in tracking_results:
            track_box = tracking_result['box']
            track_id = tracking_result['track_id']
            track_class_id = tracking_result['class_id']

            # Draw tracking ID on the image
            self.draw_tracking_result(
                image, track_box, track_id, track_class_id)

        return image

    def detect_and_track_from_image_path(self, image_path: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Load an image from file, perform detection and tracking.

        Args:
            image_path (str): Path to the input image file.

        Returns:
            Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
                - List of detection results from ObjectDetector
                - List of tracking results with track IDs
        """
        # Read the image from file
        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(f"Could not read image from {image_path}")

        # Perform detection and tracking
        return self.detect_and_track(image)

    def draw_tracking_result(self,
                             image: np.ndarray,
                             box: Tuple[Any, Any, Any, Any],
                             track_id: int,
                             class_id: int) -> None:
        """
        Draw tracking ID and bounding box on the input image.

        Args:
            image (np.ndarray): Input image to draw on.
            box (Tuple[Any, Any, Any, Any]): Bounding box coordinates (x1, y1, x2, y2).
            track_id (int): Tracking ID.
            class_id (int): Class ID of the tracked object.
        """
        # Convert coordinates to integers
        x1, y1, x2, y2 = map(int, box)

        # Get or generate a color for this track ID
        if track_id not in self.track_colors:
            self.track_colors[track_id] = tuple(
                int(c) for c in np.random.randint(0, 255, size=3))

        color = self.track_colors[track_id]

        # Draw bounding box
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)

        # Draw track ID above the bounding box
        label = f"ID: {track_id} ({self.classes[class_id]})"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        thickness = 2

        # Calculate text size
        text_size = cv2.getTextSize(label, font, font_scale, thickness)[0]

        # Draw background rectangle for text
        cv2.rectangle(
            image,
            (x1, y1 - text_size[1] - 10),
            (x1 + text_size[0], y1),
            color,
            -1
        )

        # Draw text
        cv2.putText(
            image,
            label,
            (x1, y1 - 5),
            font,
            font_scale,
            (255, 255, 255),
            thickness
        )
