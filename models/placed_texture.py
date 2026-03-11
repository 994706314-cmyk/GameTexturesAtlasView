"""已放置贴图数据模型"""

from dataclasses import dataclass
from typing import Tuple

from utils.constants import GRID_UNIT
from .texture_item import TextureItem


@dataclass
class PlacedTexture:
    """编辑器中已放置的贴图"""
    texture: TextureItem
    grid_x: int = 0
    grid_y: int = 0

    @property
    def pixel_x(self) -> int:
        return self.grid_x * GRID_UNIT

    @property
    def pixel_y(self) -> int:
        return self.grid_y * GRID_UNIT

    @property
    def pixel_rect(self) -> Tuple[int, int, int, int]:
        """返回 (x, y, w, h) 像素矩形"""
        return (
            self.pixel_x,
            self.pixel_y,
            self.texture.display_width,
            self.texture.display_height,
        )

    def to_dict(self) -> dict:
        return {
            "texture": self.texture.to_dict(),
            "grid_x": self.grid_x,
            "grid_y": self.grid_y,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlacedTexture":
        return cls(
            texture=TextureItem.from_dict(data.get("texture", {})),
            grid_x=data.get("grid_x", 0),
            grid_y=data.get("grid_y", 0),
        )
