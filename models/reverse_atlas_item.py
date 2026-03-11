"""检查模式 - 图集数据模型"""

import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class SubRegion:
    """图集中分割出的子图区域"""
    x: int = 0                      # 区域左上角 x 坐标（像素）
    y: int = 0                      # 区域左上角 y 坐标（像素）
    width: int = 0                  # 区域宽度
    height: int = 0                 # 区域高度
    phash: str = ""                 # 感知哈希
    dhash: str = ""                 # 差异哈希
    atlas_id: str = ""              # 所属图集 ID
    region_id: str = ""             # 子区域唯一 ID
    
    def __post_init__(self):
        if not self.region_id:
            self.region_id = str(uuid.uuid4())[:8]
    
    @property
    def area(self) -> int:
        """区域面积"""
        return self.width * self.height
    
    @property
    def rect(self) -> Tuple[int, int, int, int]:
        """返回 (x, y, w, h) 元组"""
        return (self.x, self.y, self.width, self.height)
    
    @property
    def center(self) -> Tuple[int, int]:
        """区域中心点"""
        return (self.x + self.width // 2, self.y + self.height // 2)
    
    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "phash": self.phash,
            "dhash": self.dhash,
            "atlas_id": self.atlas_id,
            "region_id": self.region_id,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SubRegion":
        """从字典反序列化"""
        return cls(
            x=data.get("x", 0),
            y=data.get("y", 0),
            width=data.get("width", 0),
            height=data.get("height", 0),
            phash=data.get("phash", ""),
            dhash=data.get("dhash", ""),
            atlas_id=data.get("atlas_id", ""),
            region_id=data.get("region_id", ""),
        )


@dataclass
class ReverseAtlasItem:
    """检查模式的图集数据"""
    id: str = ""                                # 图集唯一 ID
    name: str = ""                              # 图集文件名（不含路径）
    file_path: str = ""                         # 图集完整文件路径
    image_size: Tuple[int, int] = (0, 0)        # 图集尺寸 (width, height)
    thumbnail_path: Optional[str] = None        # 缩略图缓存路径
    sub_regions: List[SubRegion] = field(default_factory=list)  # 分割出的子图区域
    is_segmented: bool = False                  # 是否已完成分割
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:12]
    
    @property
    def region_count(self) -> int:
        """子图区域数量"""
        return len(self.sub_regions)
    
    @property
    def size_str(self) -> str:
        """尺寸描述字符串"""
        w, h = self.image_size
        return f"{w}×{h}"
    
    def add_region(self, region: SubRegion):
        """添加子图区域"""
        region.atlas_id = self.id
        self.sub_regions.append(region)
    
    def clear_regions(self):
        """清空所有子图区域"""
        self.sub_regions.clear()
        self.is_segmented = False
    
    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "file_path": self.file_path,
            "image_size": list(self.image_size),
            "thumbnail_path": self.thumbnail_path,
            "sub_regions": [r.to_dict() for r in self.sub_regions],
            "is_segmented": self.is_segmented,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ReverseAtlasItem":
        """从字典反序列化"""
        item = cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            file_path=data.get("file_path", ""),
            image_size=tuple(data.get("image_size", [0, 0])),
            thumbnail_path=data.get("thumbnail_path"),
            is_segmented=data.get("is_segmented", False),
        )
        for r_data in data.get("sub_regions", []):
            item.sub_regions.append(SubRegion.from_dict(r_data))
        return item
