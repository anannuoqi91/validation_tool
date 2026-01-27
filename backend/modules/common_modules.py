from dataclasses import dataclass


@dataclass
class BoxData:
    """Container for box data (simplified version)"""
    position_x: float  # unit: meter
    position_y: float  # unit: meter
    position_z: float  # unit: meter
    length: float      # unit: meter
    width: float       # unit: meter
    height: float      # unit: meter
    object_type: int
    track_id: int
    lane_id: int
