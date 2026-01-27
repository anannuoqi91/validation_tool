from dataclasses import dataclass
from typing import Optional, Tuple, Callable
from backend.modules.common_modules import BoxData
import numpy as np


@dataclass
class ImageData:
    """Container for image data"""
    timestamp_ms: int  # in milliseconds
    timestamp_ms_local: int
    image: np.ndarray
    width: int
    height: int
    channels: int
    region_name: Optional[str] = None
    box: Optional[BoxData] = None
