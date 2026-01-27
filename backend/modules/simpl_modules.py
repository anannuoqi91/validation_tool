from dataclasses import dataclass
from typing import Optional
from backend.modules.common_modules import BoxData
try:
    from proto.drivers_pb2 import PointCloud2
except ImportError as e:
    print(f"Failed to import PointCloud2: {e}")


@dataclass
class EventData:
    """Container for event data"""
    timestamp_ms: int
    timestamp_ms_local: int
    region_name: str
    region_id: int
    box: BoxData
    pointcloud: Optional[PointCloud2] = None
