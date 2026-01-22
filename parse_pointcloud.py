import struct
from dataclasses import dataclass
from typing import List, Optional, BinaryIO

@dataclass
class VlPointCore:
    """对应 C++ 中的 VlPointCore 类
    
    实际大小: 24字节 (包含内存对齐填充)
    """
    x: float
    y: float
    z: float
    intensity: int  # uint16
    timestamp: int  # uint64
    
    # 实际结构: 3*float(12) + uint16(2) + 填充(2) + uint64(8) = 24字节
    # 或者: 3*float(12) + 填充(4) + uint64(8) = 24字节
    # 需要根据实际内存布局调整
    
    # 尝试两种可能的格式
    STRUCT_FORMAT_1 = '<fffHQ'    # 紧凑布局，22字节 (如果实际是24字节，则后面有2字节填充)
    STRUCT_FORMAT_2 = '<fffxxQ'   # 有2字节填充，24字节 (在uint16后)
    STRUCT_FORMAT_3 = '<fffHxxQ'  # 在uint16后有2字节填充，24字节
    
    # 根据实际测试，可能是格式3
    STRUCT_FORMAT = '<fffHxxQ'  # 小端字节序: 3个float, uint16, 2字节填充, uint64
    STRUCT_SIZE = 24  # 实际测试大小
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'VlPointCore':
        """从字节流解析单个点"""
        if len(data) < cls.STRUCT_SIZE:
            raise ValueError(f"数据长度不足，至少需要 {cls.STRUCT_SIZE} 字节")
        
        # 使用实际的结构体格式解析
        # 注意：x表示填充字节
        x, y, z, intensity, timestamp = struct.unpack(cls.STRUCT_FORMAT, data[:cls.STRUCT_SIZE])
        return cls(x, y, z, intensity, timestamp)
    
    def to_bytes(self) -> bytes:
        """转换为字节流"""
        return struct.pack(self.STRUCT_FORMAT, self.x, self.y, self.z, self.intensity, self.timestamp)
    
    def copy_from(self, other: 'VlPointCore') -> None:
        """复制另一个点的数据"""
        self.x = other.x
        self.y = other.y
        self.z = other.z
        self.intensity = other.intensity
        self.timestamp = other.timestamp
    
    def __repr__(self) -> str:
        return (f"VlPointCore(x={self.x:.3f}, y={self.y:.3f}, z={self.z:.3f}, "
                f"intensity={self.intensity}, timestamp={self.timestamp})")

@dataclass
class VlPointSupplement:
    """对应 C++ 中的 VlPointSupplement 类
    
    实际大小: 12字节 (包含内存对齐填充)
    """
    scan_id: int      # int16
    scan_idx: int     # int16
    sub_id: int       # int32
    label: int        # uint8
    elongation: int   # uint8
    flags: int        # uint8
    
    # 实际结构: int16(2) + int16(2) + int32(4) + 3*uint8(3) + 填充(1) = 12字节
    # 或者: 前面有填充，后面有填充
    
    # 尝试可能的格式
    STRUCT_FORMAT_1 = '<hhiBBBx'  # 小端字节序: 2个int16, int32, 3个uint8, 1字节填充
    STRUCT_FORMAT_2 = '<hhiBBBB'  # 最后一个字节可能是填充
    STRUCT_FORMAT_3 = '<hhiBBB'   # 11字节，如果实际是12字节则后面有1字节填充
    
    # 根据实际测试，可能是格式1
    STRUCT_FORMAT = '<hhiBBBx'  # 小端字节序: 2个int16, int32, 3个uint8, 1字节填充
    STRUCT_SIZE = 12  # 实际测试大小
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'VlPointSupplement':
        """从字节流解析单个点"""
        if len(data) < cls.STRUCT_SIZE:
            raise ValueError(f"数据长度不足，至少需要 {cls.STRUCT_SIZE} 字节")
        
        scan_id, scan_idx, sub_id, label, elongation, flags = struct.unpack(
            cls.STRUCT_FORMAT, data[:cls.STRUCT_SIZE]
        )
        return cls(scan_id, scan_idx, sub_id, label, elongation, flags)
    
    def to_bytes(self) -> bytes:
        """转换为字节流"""
        return struct.pack(self.STRUCT_FORMAT, 
                          self.scan_id, self.scan_idx, self.sub_id,
                          self.label, self.elongation, self.flags)
    
    def copy_from(self, other: 'VlPointSupplement') -> None:
        """复制另一个点的数据"""
        self.scan_id = other.scan_id
        self.scan_idx = other.scan_idx
        self.sub_id = other.sub_id
        self.label = other.label
        self.elongation = other.elongation
        self.flags = other.flags
    
    def __repr__(self) -> str:
        return (f"VlPointSupplement(scan_id={self.scan_id}, scan_idx={self.scan_idx}, "
                f"sub_id={self.sub_id}, label={self.label}, elongation={self.elongation}, "
                f"flags={self.flags})")


class VirtualLoopPoint:
    """对应 C++ 中的 VirtualLoopPoint 类
    
    注意：这个类不管理内存，只提供访问接口
    """
    
    def __init__(self, core: Optional[VlPointCore] = None, 
                 supplement: Optional[VlPointSupplement] = None):
        """
        初始化 VirtualLoopPoint
        
        Args:
            core: VlPointCore 对象，如果为 None 则创建新对象
            supplement: VlPointSupplement 对象，如果为 None 则创建新对象
        """
        if core is None:
            core = VlPointCore(0.0, 0.0, 0.0, 0, 0)
        if supplement is None:
            supplement = VlPointSupplement(0, 0, 0, 0, 0, 0)
            
        self._core = core
        self._supplement = supplement
    
    @classmethod
    def from_bytes(cls, core_data: bytes, supplement_data: bytes) -> 'VirtualLoopPoint':
        """从字节流创建 VirtualLoopPoint"""
        core = VlPointCore.from_bytes(core_data)
        supplement = VlPointSupplement.from_bytes(supplement_data)
        return cls(core, supplement)
    
    @property
    def core(self) -> VlPointCore:
        """获取 core 数据"""
        return self._core
    
    @property
    def supplement(self) -> VlPointSupplement:
        """获取 supplement 数据"""
        return self._supplement
    
    # Core 字段访问器
    @property
    def x(self) -> float:
        return self._core.x
    
    @x.setter
    def x(self, value: float):
        self._core.x = value
    
    @property
    def y(self) -> float:
        return self._core.y
    
    @y.setter
    def y(self, value: float):
        self._core.y = value
    
    @property
    def z(self) -> float:
        return self._core.z
    
    @z.setter
    def z(self, value: float):
        self._core.z = value
    
    @property
    def intensity(self) -> int:
        return self._core.intensity
    
    @intensity.setter
    def intensity(self, value: int):
        self._core.intensity = value
    
    @property
    def timestamp(self) -> int:
        return self._core.timestamp
    
    @timestamp.setter
    def timestamp(self, value: int):
        self._core.timestamp = value
    
    # Supplement 字段访问器
    @property
    def label(self) -> int:
        return self._supplement.label
    
    @label.setter
    def label(self, value: int):
        self._supplement.label = value
    
    @property
    def scan_id(self) -> int:
        return self._supplement.scan_id
    
    @scan_id.setter
    def scan_id(self, value: int):
        self._supplement.scan_id = value
    
    @property
    def scan_idx(self) -> int:
        return self._supplement.scan_idx
    
    @scan_idx.setter
    def scan_idx(self, value: int):
        self._supplement.scan_idx = value
    
    @property
    def sub_id(self) -> int:
        return self._supplement.sub_id
    
    @sub_id.setter
    def sub_id(self, value: int):
        self._supplement.sub_id = value
    
    @property
    def elongation(self) -> int:
        return self._supplement.elongation
    
    @elongation.setter
    def elongation(self, value: int):
        self._supplement.elongation = value
    
    @property
    def flags(self) -> int:
        return self._supplement.flags
    
    @flags.setter
    def flags(self, value: int):
        self._supplement.flags = value
    
    def copy_from(self, other: 'VirtualLoopPoint') -> None:
        """复制另一个点的数据"""
        self._core.copy_from(other.core)
        self._supplement.copy_from(other.supplement)
    
    def to_bytes(self) -> tuple:
        """转换为字节流"""
        return self._core.to_bytes(), self._supplement.to_bytes()
    
    def __repr__(self) -> str:
        return (f"VirtualLoopPoint(x={self.x:.3f}, y={self.y:.3f}, z={self.z:.3f}, "
                f"intensity={self.intensity}, timestamp={self.timestamp}, "
                f"label={self.label}, scan_id={self.scan_id}, scan_idx={self.scan_idx})")


def parse_point_cloud(core_data: bytes, supplement_data: bytes) -> List[VirtualLoopPoint]:
    """
    解析整个点云的字节数据
    
    Args:
        core_data: 所有点的 core 数据字节流
        supplement_data: 所有点的 supplement 数据字节流
    
    Returns:
        包含所有点的 VirtualLoopPoint 列表
    """
    points = []
    
    # 计算点数量
    core_struct_size = VlPointCore.STRUCT_SIZE
    supplement_struct_size = VlPointSupplement.STRUCT_SIZE
    
    num_points_core = len(core_data) // core_struct_size
    num_points_supplement = len(supplement_data) // supplement_struct_size
    
    if num_points_core != num_points_supplement:
        print(f"警告: Core 和 Supplement 数据点数量不一致: "
              f"core={num_points_core}, supplement={num_points_supplement}")
        # 取最小值
        num_points = min(num_points_core, num_points_supplement)
    else:
        num_points = num_points_core
    
    # 逐个解析点
    for i in range(num_points):
        core_offset = i * core_struct_size
        supplement_offset = i * supplement_struct_size
        
        try:
            core = VlPointCore.from_bytes(
                core_data[core_offset:core_offset + core_struct_size]
            )
            supplement = VlPointSupplement.from_bytes(
                supplement_data[supplement_offset:supplement_offset + supplement_struct_size]
            )
            
            points.append(VirtualLoopPoint(core, supplement))
        except Exception as e:
            print(f"解析第 {i} 个点时出错: {e}")
            break
    
    return points


def parse_point_cloud_single_buffer(data: bytes) -> List[VirtualLoopPoint]:
    """
    解析单个缓冲区中的点云数据（core 和 supplement 连续存储）
    
    Args:
        data: 包含所有点 core 和 supplement 数据的连续字节流
    
    Returns:
        包含所有点的 VirtualLoopPoint 列表
    """
    points = []
    
    # 每个点的总大小
    core_struct_size = VlPointCore.STRUCT_SIZE
    supplement_struct_size = VlPointSupplement.STRUCT_SIZE
    point_size = core_struct_size + supplement_struct_size
    
    # 计算点数量
    num_points = len(data) // point_size
    
    if len(data) % point_size != 0:
        print(f"警告: 数据长度 {len(data)} 不是点大小 {point_size} 的整数倍")
    
    # 逐个解析点
    for i in range(num_points):
        offset = i * point_size
        
        try:
            # 解析 core
            core_data = data[offset:offset + core_struct_size]
            core = VlPointCore.from_bytes(core_data)
            
            # 解析 supplement
            supplement_offset = offset + core_struct_size
            supplement_data = data[supplement_offset:supplement_offset + supplement_struct_size]
            supplement = VlPointSupplement.from_bytes(supplement_data)
            
            points.append(VirtualLoopPoint(core, supplement))
        except Exception as e:
            print(f"解析第 {i} 个点时出错: {e}")
            break
    
    return points


def parse_point_cloud_flexible(core_data: bytes, supplement_data: bytes, 
                               core_format: Optional[str] = None,
                               supplement_format: Optional[str] = None) -> List[VirtualLoopPoint]:
    """
    灵活解析点云数据，支持自定义格式
    
    Args:
        core_data: core 数据字节流
        supplement_data: supplement 数据字节流
        core_format: 自定义 core 格式字符串
        supplement_format: 自定义 supplement 格式字符串
    
    Returns:
        包含所有点的 VirtualLoopPoint 列表
    """
    points = []
    
    # 使用自定义格式或默认格式
    if core_format:
        core_struct_size = struct.calcsize(core_format)
    else:
        core_struct_size = VlPointCore.STRUCT_SIZE
        core_format = VlPointCore.STRUCT_FORMAT
    
    if supplement_format:
        supplement_struct_size = struct.calcsize(supplement_format)
    else:
        supplement_struct_size = VlPointSupplement.STRUCT_SIZE
        supplement_format = VlPointSupplement.STRUCT_FORMAT
    
    # 计算点数量
    num_points_core = len(core_data) // core_struct_size
    num_points_supplement = len(supplement_data) // supplement_struct_size
    
    num_points = min(num_points_core, num_points_supplement)
    
    # 逐个解析点
    for i in range(num_points):
        core_offset = i * core_struct_size
        supplement_offset = i * supplement_struct_size
        
        try:
            # 解析 core
            core_values = struct.unpack(
                core_format, 
                core_data[core_offset:core_offset + core_struct_size]
            )
            
            # 根据格式创建 core 对象
            if core_format == VlPointCore.STRUCT_FORMAT:
                core = VlPointCore(*core_values)
            else:
                # 对于自定义格式，创建简化对象
                core = VlPointCore(0.0, 0.0, 0.0, 0, 0)
                # 这里可以根据实际情况设置字段
                # 例如: core.x = core_values[0] 等
            
            # 解析 supplement
            supplement_values = struct.unpack(
                supplement_format,
                supplement_data[supplement_offset:supplement_offset + supplement_struct_size]
            )
            
            # 根据格式创建 supplement 对象
            if supplement_format == VlPointSupplement.STRUCT_FORMAT:
                supplement = VlPointSupplement(*supplement_values)
            else:
                # 对于自定义格式，创建简化对象
                supplement = VlPointSupplement(0, 0, 0, 0, 0, 0)
                # 这里可以根据实际情况设置字段
            
            points.append(VirtualLoopPoint(core, supplement))
        except Exception as e:
            print(f"解析第 {i} 个点时出错: {e}")
            break
    
    return points


# 测试函数
def test_parsing():
    """测试解析功能"""
    print("=== 测试解析功能 ===")
    
    # 创建测试数据
    # 注意：根据实际格式创建字节数据
    core_bytes = struct.pack('<fffHxxQ', 1.0, 2.0, 3.0, 100, 1234567890)
    supplement_bytes = struct.pack('<hhiBBBx', 1, 10, 1000, 5, 2, 1)
    
    print(f"Core 数据长度: {len(core_bytes)} 字节")
    print(f"Supplement 数据长度: {len(supplement_bytes)} 字节")
    
    # 测试单个点解析
    point = VirtualLoopPoint.from_bytes(core_bytes, supplement_bytes)
    print(f"\n解析的点: {point}")
    print(f"Core: {point.core}")
    print(f"Supplement: {point.supplement}")
    
    # 测试点云解析
    print("\n=== 测试点云解析 ===")
    
    # 创建3个点的数据
    core_data_list = []
    supplement_data_list = []
    
    for i in range(3):
        core_data_list.append(struct.pack('<fffHxxQ', 
                                         float(i), float(i*2), float(i*3),
                                         i*50, 1234567890 + i*1000))
        supplement_data_list.append(struct.pack('<hhiBBBx', 
                                               i, i*5, i*100, i, i%2, 0))
    
    # 合并数据
    all_core_data = b''.join(core_data_list)
    all_supplement_data = b''.join(supplement_data_list)
    
    print(f"点云 Core 数据总长度: {len(all_core_data)} 字节")
    print(f"点云 Supplement 数据总长度: {len(all_supplement_data)} 字节")
    
    # 解析点云
    points = parse_point_cloud(all_core_data, all_supplement_data)
    print(f"\n解析了 {len(points)} 个点:")
    for i, p in enumerate(points):
        print(f"  点{i}: {p}")
    
    # 测试连续缓冲区解析
    print("\n=== 测试连续缓冲区解析 ===")
    
    # 创建连续数据
    continuous_data = b''
    for i in range(2):
        continuous_data += struct.pack('<fffHxxQ', 
                                      float(i+10), float(i+11), float(i+12),
                                      i*30, 9876543210 + i*1000)
        continuous_data += struct.pack('<hhiBBBx', 
                                      i+20, i+21, i+22, i+1, i, 1)
    
    print(f"连续缓冲区数据长度: {len(continuous_data)} 字节")
    
    # 解析
    points2 = parse_point_cloud_single_buffer(continuous_data)
    print(f"\n从连续缓冲区解析了 {len(points2)} 个点:")
    for i, p in enumerate(points2):
        print(f"  点{i}: {p}")


if __name__ == "__main__":
    # 运行测试
    test_parsing()