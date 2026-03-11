"""贴图素材数据模型"""

import uuid
from dataclasses import dataclass, field
from typing import Optional, Tuple

from utils.constants import GRID_UNIT
from utils.validators import validate_texture_size


@dataclass
class TextureItem:
    """素材库中的贴图素材"""
    original_path: str
    original_size: Tuple[int, int]
    display_size: Tuple[int, int]
    name: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    thumbnail_path: Optional[str] = None
    is_screenshot: bool = False  # 截图添加的贴图（无源文件）

    @property
    def display_width(self) -> int:
        return self.display_size[0]

    @property
    def display_height(self) -> int:
        return self.display_size[1]

    @property
    def grid_width(self) -> int:
        return self.display_size[0] // GRID_UNIT

    @property
    def grid_height(self) -> int:
        return self.display_size[1] // GRID_UNIT

    def validate_display_size(self) -> Tuple[bool, str]:
        return validate_texture_size(self.display_size[0], self.display_size[1])

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "original_path": self.original_path,
            "original_size": list(self.original_size),
            "display_size": list(self.display_size),
            "name": self.name,
            "thumbnail_path": self.thumbnail_path,
        }
        if self.is_screenshot:
            d["is_screenshot"] = True
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TextureItem":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            original_path=data.get("original_path", ""),
            original_size=tuple(data.get("original_size", [64, 64])),
            display_size=tuple(data.get("display_size", [64, 64])),
            name=data.get("name", "未命名"),
            thumbnail_path=data.get("thumbnail_path"),
            is_screenshot=data.get("is_screenshot", False),
        )
