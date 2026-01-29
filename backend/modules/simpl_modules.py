from dataclasses import dataclass
from typing import Optional, List
from backend.modules.common_modules import BoxData
import time
try:
    from proto.drivers_pb2 import PointCloud2
    from proto.inno_box_pb2 import Boxes
except ImportError as e:
    print(f"Failed to import PointCloud2: {e}")


RECORD_MSG_TYPE = {
    "omnividi.event.BaseEvent": "event",
    "omnividi.event.BaseEvents": "event",
    "omnividi.box.Boxes": "box",
    "omnividi.camera.CameraFrame": "camera",
    "omnividi.trig_recorder.CompressedMsg": "points",
    "omnividi.drivers.PointCloud2": "points"
}


@dataclass
class EventData:
    """Container for event data"""
    timestamp_ms: int
    timestamp_ms_local: int
    region_name: str
    region_id: int
    box: BoxData
    pointcloud: Optional[PointCloud2] = None


@dataclass
class PointsData:
    """Container for point cloud data"""
    timestamp_ms: int
    timestamp_ms_local: int
    pointcloud: Optional[PointCloud2] = None


@dataclass
class FrameData:
    """Container for frame data (simplified version)"""
    timestamp_ms: int
    timestamp_ms_local: int
    event_data: Optional[List[EventData]] = None
    pointcloud: Optional[PointsData] = None
    box_data: Optional[Boxes] = None


def code_pd2_pd(pd2: PointCloud2) -> PointsData:
    """Convert PointCloud2 to PointsData"""
    return PointsData(
        timestamp_ms=int(pd2.frame_ns_start / 1e6),
        timestamp_ms_local=int(time.time() * 1e3),
        pointcloud=pd2,
    )
