#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Matcher class for managing maps of EventData and ImageData.
"""

import threading
from typing import Optional, Dict, List
from data_adapter import EventData, ImageData
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Matcher:
    """
    A class that maintains two maps for EventData and ImageData,
    and provides interfaces for inputting data into these maps.
    Uses region_name as the key and thread locks for thread safety.
    """
    
    def __init__(self, max_time_diff_ms: int = 5000, use_local_timestamp: bool = True, max_queue_size: int = 1000):
        """
        Initialize the Matcher with empty maps.
        
        Args:
            max_time_diff_ms (int): Maximum time difference allowed between matching data.
            use_local_timestamp (bool): Whether to use local timestamp for matching.
            max_queue_size (int): Maximum number of items per region_name in both maps. Defaults to 1000.
        """
        self.max_queue_size = max_queue_size
        self.max_time_diff_ms = max_time_diff_ms
        self.use_local_timestamp = use_local_timestamp
        
        # Map for storing EventData, key: region_name, value: list of EventData
        self.event_map: Dict[str, List[EventData]] = {}
        
        # Map for storing ImageData, key: region_name, value: list of ImageData
        self.image_map: Dict[str, List[ImageData]] = {}
        
        # Thread locks for thread safety
        # self.event_map_lock = threading.Lock()
        # self.image_map_lock = threading.Lock()
        self.map_lock = threading.Lock()

    def add_event_data(self, event_data: EventData) -> List[Dict]:
        """
        Add EventData to the event map.
        
        Args:
            event_data (EventData): The EventData to add to the map.
            
        Returns:
            List[Dict]: A list of matched pairs, each pair is a dictionary with "event" and "image" keys.
        """
        if not isinstance(event_data, EventData):
            logger.error("Invalid data type: expected EventData")
            return []
        
        if not hasattr(event_data, 'region_name') or event_data.region_name is None:
            logger.error("EventData must have a valid region_name")
            return []
        
        region_name = event_data.region_name

        output_pairs = []

        with self.map_lock:
            if region_name in self.image_map:
                while len(self.image_map[region_name]) > 0:
                    image_data = self.image_map[region_name][0]
                    # if self.use_local_timestamp:
                    #Explain:
                    # If event timestamp is later than image timestamp + max diff, image can't be matched, remove it
                    # If event timestamp + max diff is earlier than image timestamp, event can't be matched, stop checking
                    # Else, we have a match
                    if event_data.timestamp_ms_local > image_data.timestamp_ms_local + self.max_time_diff_ms:
                        image_data_to_remove = self.image_map[region_name].pop(0)
                        output_pairs.append({"event": None, "image": image_data_to_remove})
                        logger.info(f"Dropping ImageData with local timestamp {image_data_to_remove.timestamp_ms_local} for region {region_name}")
                    elif event_data.timestamp_ms_local + self.max_time_diff_ms < image_data.timestamp_ms_local:
                        break
                    else:
                        image_data_to_match = self.image_map[region_name].pop(0)
                        output_pairs.append({"event": event_data, "image": image_data_to_match})
                        logger.info(f"Matched EventData with local timestamp {event_data.timestamp_ms_local} to ImageData with local timestamp {image_data_to_match.timestamp_ms_local} for region {region_name}")
                        return output_pairs
                    # else:
                    #     pass

            # Initialize list if region_name not in map
            if region_name not in self.event_map:
                self.event_map[region_name] = []
            
            # Check if the list for this region is full
            if len(self.event_map[region_name]) >= self.max_queue_size:
                logger.warning(f"Event list for region {region_name} is full, dropping oldest data")
                # Remove oldest data
                self.event_map[region_name].pop(0)
            
            # Add new event data to the end of the list
            self.event_map[region_name].append(event_data)

        return output_pairs
    
    def add_image_data(self, image_data: ImageData) -> List[Dict]:
        """
        Add ImageData to the image map.
        
        Args:
            image_data (ImageData): The ImageData to add to the map.
            
        Returns:
            List[Dict]: A list of matched pairs, each pair is a dictionary with "event" and "image" keys.
        """
        if not isinstance(image_data, ImageData):
            logger.error("Invalid data type: expected ImageData")
            return []
        
        if not hasattr(image_data, 'region_name') or image_data.region_name is None:
            logger.error("ImageData must have a valid region_name")
            return []
        
        region_name = image_data.region_name
        
        output_pairs = []
        with self.map_lock:
            if region_name in self.event_map:
                while len(self.event_map[region_name]) > 0:
                    event_data = self.event_map[region_name][0]
                    # if self.use_local_timestamp:
                    #Explain:
                    # If image timestamp is later than event timestamp + max diff, event can't be matched, remove it
                    # If image timestamp + max diff is earlier than event timestamp, image can't be matched, stop checking
                    # Else, we have a match
                    if image_data.timestamp_ms_local > event_data.timestamp_ms_local + self.max_time_diff_ms:
                        event_data_to_remove = self.event_map[region_name].pop(0)
                        output_pairs.append({"event": event_data_to_remove, "image": None})
                        logger.info(f"Dropping EventData with local timestamp {event_data_to_remove.timestamp_ms_local} for region {region_name}")
                    elif image_data.timestamp_ms_local + self.max_time_diff_ms < event_data.timestamp_ms_local:
                        break
                    else:
                        event_data_to_match = self.event_map[region_name].pop(0)
                        output_pairs.append({"event": event_data_to_match, "image": image_data})
                        logger.info(f"Matched EventData with local timestamp {event_data_to_match.timestamp_ms_local} to ImageData with local timestamp {image_data.timestamp_ms_local} for region {region_name}")
                        return output_pairs
                    # else:
                    #     pass

            # Initialize list if region_name not in map
            if region_name not in self.image_map:
                self.image_map[region_name] = []
            
            # Check if the list for this region is full
            if len(self.image_map[region_name]) >= self.max_queue_size:
                logger.warning(f"Image list for region {region_name} is full, dropping oldest data")
                # Remove oldest data
                self.image_map[region_name].pop(0)
            
            # Add new image data to the end of the list
            self.image_map[region_name].append(image_data)

        return output_pairs
    
    def clear_queues(self):
        """
        Clear both maps, removing all stored data.
        """
        with self.map_lock:
            self.event_map.clear()
            self.image_map.clear()