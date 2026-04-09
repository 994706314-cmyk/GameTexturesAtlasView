"""单张合图数据模型"""

import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from utils.constants import DEFAULT_ATLAS_SIZE, GRID_UNIT
from .placed_texture import PlacedTexture


@dataclass
class AtlasModel:
    """单张合图，维护已放置贴图和占位网格"""
    name: str = "新合图"
    size: int = DEFAULT_ATLAS_SIZE
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    placed_textures: List[PlacedTexture] = field(default_factory=list)

    def __post_init__(self):
        self._rebuild_grid()

    @property
    def grid_count(self) -> int:
        return self.size // GRID_UNIT

    def _rebuild_grid(self):
        """重建占位网格"""
        n = self.grid_count
        self._grid = [[False] * n for _ in range(n)]
        for pt in self.placed_textures:
            self._mark_grid(pt, True)

    def _mark_grid(self, pt: PlacedTexture, value: bool):
        gw = pt.texture.grid_width
        gh = pt.texture.grid_height
        for dy in range(gh):
            for dx in range(gw):
                y, x = pt.grid_y + dy, pt.grid_x + dx
                if 0 <= y < self.grid_count and 0 <= x < self.grid_count:
                    self._grid[y][x] = value

    def can_place(self, grid_x: int, grid_y: int, grid_w: int, grid_h: int,
                  exclude_id: Optional[str] = None) -> bool:
        """检查指定网格区域是否可以放置（不越界、不重叠）"""
        n = self.grid_count
        if grid_x < 0 or grid_y < 0:
            return False
        if grid_x + grid_w > n or grid_y + grid_h > n:
            return False

        exclude_cells = set()
        if exclude_id:
            for pt in self.placed_textures:
                if pt.texture.id == exclude_id:
                    for dy in range(pt.texture.grid_height):
                        for dx in range(pt.texture.grid_width):
                            exclude_cells.add((pt.grid_y + dy, pt.grid_x + dx))
                    break

        for dy in range(grid_h):
            for dx in range(grid_w):
                y, x = grid_y + dy, grid_x + dx
                if self._grid[y][x] and (y, x) not in exclude_cells:
                    return False
        return True

    def place(self, pt: PlacedTexture) -> bool:
        """放置一张贴图，成功返回 True"""
        gw = pt.texture.grid_width
        gh = pt.texture.grid_height
        if not self.can_place(pt.grid_x, pt.grid_y, gw, gh):
            return False
        self.placed_textures.append(pt)
        self._mark_grid(pt, True)
        return True

    def remove(self, texture_id: str) -> Optional[PlacedTexture]:
        """移除贴图，返回被移除的 PlacedTexture"""
        for i, pt in enumerate(self.placed_textures):
            if pt.texture.id == texture_id:
                self._mark_grid(pt, False)
                return self.placed_textures.pop(i)
        return None

    def move(self, texture_id: str, new_grid_x: int, new_grid_y: int) -> bool:
        """移动贴图到新网格位置"""
        for pt in self.placed_textures:
            if pt.texture.id == texture_id:
                gw = pt.texture.grid_width
                gh = pt.texture.grid_height
                if not self.can_place(new_grid_x, new_grid_y, gw, gh, exclude_id=texture_id):
                    return False
                self._mark_grid(pt, False)
                pt.grid_x = new_grid_x
                pt.grid_y = new_grid_y
                self._mark_grid(pt, True)
                return True
        return False

    def utilization(self) -> float:
        """计算空间利用率 (0.0~1.0)"""
        if not self.placed_textures:
            return 0.0
        total_cells = self.grid_count * self.grid_count
        used_cells = sum(1 for row in self._grid for cell in row if cell)
        return used_cells / total_cells

    def set_size(self, new_size: int):
        """更新合图尺寸并重建网格"""
        self.size = new_size
        self._rebuild_grid()

    def find_placed(self, texture_id: str) -> Optional[PlacedTexture]:
        for pt in self.placed_textures:
            if pt.texture.id == texture_id:
                return pt
        return None

    def to_dict(self, full_mode: bool = False) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "size": self.size,
            "placed_textures": [pt.to_dict(full_mode=full_mode) for pt in self.placed_textures],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AtlasModel":
        atlas = cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", "新合图"),
            size=data.get("size", DEFAULT_ATLAS_SIZE),
            placed_textures=[
                PlacedTexture.from_dict(pt_data)
                for pt_data in data.get("placed_textures", [])
            ],
        )
        return atlas
