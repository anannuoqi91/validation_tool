from proto.region_pb2 import EventRegionAttribute
from proto.inno_event_pb2 import VolumeFunc, TRIGGER
from proto.drivers_pb2 import PointCloud2
from proto.camera_pb2 import DataFormat
import lz4.block as lz4b
import struct
from backend.modules.simpl_modules import EventData, BoxData
from backend.modules.camera_modules import ImageData
import time
import numpy as np


def handle_event_region_attr(event_region_attr):
    def parse_event(serialized_msg, event_class):
        event = event_class()
        event.ParseFromString(serialized_msg)
        return event

    def volume_func(serialized_msg):
        return parse_event(serialized_msg, VolumeFunc)

    switcher = {
        EventRegionAttribute.FLOW_EVENT: volume_func,
    }

    handle = switcher.get(event_region_attr, None)
    return handle


def handle_compressed_points(msg):
    _point_struct = {
        # core:   x(float32), y(float32), z(float32), intensity(uint16), timestamp(uint64)
        "core_fmt": "<fffHxxQ",
        # supplement: scan_id(int16), scan_idx(int16), sub_id(int32), label(uint8), elongation(uint8), flags(uint8)
        "supp_fmt": "<hhiBBxx",
        # 24 bytes：H add 2 bytes, Q add 8 bytes
        "core_size": struct.calcsize("fffHxxQ"),
        # 12 bytes: add 2 bytes, make total 4 bytes aligned
        "supp_size": struct.calcsize("hhiBBxx"),
    }

    def parse_point_15(data: bytes, little_endian=True):
        assert len(data) == 15
        # y, z, x: float32
        y = struct.unpack('<f' if little_endian else '>f', data[0:4])[0]
        z = struct.unpack('<f' if little_endian else '>f', data[4:8])[0]
        x = struct.unpack('<f' if little_endian else '>f', data[8:12])[0]
        # intensity: uint16
        intensity = int.from_bytes(
            data[12:14], 'little' if little_endian else 'big')
        # time_ms_off: uint8
        time_ms_off = data[14]
        return dict(y=y, z=z, x=x, intensity=intensity, time_ms_off=time_ms_off)

    def parse_supplement_4(data: bytes, little_endian: bool = True):
        if len(data) != 4:
            raise ValueError(f"need 4 bytes, but got {len(data)}")
        fmt = '<hh' if little_endian else '>hh'
        scan_id, scan_idx = struct.unpack_from(fmt, data, 0)
        return dict(scan_id=scan_id, scan_idx=scan_idx)

    original_size = msg.original_size
    raw = msg.data
    plain = lz4b.decompress(raw, uncompressed_size=original_size)
    new_msg = PointCloud2()
    new_msg.ParseFromString(plain)
    if new_msg.model == "packed":
        byte_single_len = 15
        frame_ns_start = new_msg.frame_ns_start
        num_points = len(new_msg.point_core) // byte_single_len
        core_buf = new_msg.point_core
        supplement_buf = new_msg.point_supplement
        core_size = _point_struct["core_size"]
        supp_size = _point_struct["supp_size"]
        core_fmt = _point_struct["core_fmt"]
        supp_fmt = _point_struct["supp_fmt"]
        new_core_buf = bytearray(core_size * num_points)
        new_supp_buf = bytearray(supp_size * num_points)
        for i in range(num_points):
            core_res = parse_point_15(
                core_buf[i * byte_single_len: (i + 1) * byte_single_len])
            core_res['timestamp'] = int(frame_ns_start +
                                        core_res.pop('time_ms_off') * 1_000_000)
            supp_res = parse_supplement_4(
                supplement_buf[i * 4:(i + 1) * 4])
            struct.pack_into(core_fmt, new_core_buf, i * core_size,
                             core_res['x'], core_res['y'], core_res['z'],
                             core_res['intensity'], core_res['timestamp'])
            struct.pack_into(supp_fmt, new_supp_buf, i * supp_size,
                             supp_res['scan_id'], supp_res['scan_idx'], 0, 0, 0)
        new_msg.point_core = bytes(new_core_buf)
        new_msg.point_supplement = bytes(new_supp_buf)
        new_msg.point_size = num_points
        new_msg.width = num_points
        new_msg.height = 1
        new_msg.model = "rev_i"
    return new_msg


def handle_base_event(base_event_msg, region_type):
    if base_event_msg.event_region_attr != region_type:
        return None
    handle = handle_event_region_attr(
        base_event_msg.event_region_attr)
    event = handle(base_event_msg.serialized_msg)

    # entry point
    if event.common_event.status != TRIGGER:
        return None

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
            track_id=event.common_event.boxes[0].track_id,
            lane_id=event.common_event.boxes[0].lane_id
        )

    return event_data


def handle_camera(msg):
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
    return image_data


def handle_pointscloud2_to_numpy(msg):
    dtype = np.dtype([
        ('x', '<f4'),
        ('y', '<f4'),
        ('z', '<f4'),
        ('intensity', '<u2'),
        ('_pad', 'V2'),
        ('timestamp', '<u8'),
    ])
    points = np.frombuffer(msg.point_core, dtype=dtype)
    points = points.copy()
    return points
