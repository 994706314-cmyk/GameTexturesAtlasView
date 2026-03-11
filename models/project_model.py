"""项目根数据模型"""

from dataclasses import dataclass, field
from typing import List, Optional

from utils.constants import PROJECT_VERSION
from .texture_item import TextureItem
from .atlas_model import AtlasModel


@dataclass
class ProjectModel:
    """项目根模型，支持完整序列化/反序列化"""
    version: str = PROJECT_VERSION
    atlas_list: List[AtlasModel] = field(default_factory=list)
    library: List[TextureItem] = field(default_factory=list)
    _dirty: bool = field(default=False, repr=False, compare=False)

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_dirty(self):
        self._dirty = True

    def mark_clean(self):
        self._dirty = False

    def reset(self):
        """清空所有数据，回到初始空白状态"""
        self.atlas_list.clear()
        self.library.clear()
        self._dirty = False

    def add_atlas(self, atlas: AtlasModel):
        self.atlas_list.append(atlas)
        self._dirty = True

    def remove_atlas(self, atlas_id: str) -> Optional[AtlasModel]:
        for i, a in enumerate(self.atlas_list):
            if a.id == atlas_id:
                self._dirty = True
                return self.atlas_list.pop(i)
        return None

    def find_atlas(self, atlas_id: str) -> Optional[AtlasModel]:
        for a in self.atlas_list:
            if a.id == atlas_id:
                return a
        return None

    def add_texture(self, item: TextureItem):
        self.library.append(item)
        self._dirty = True

    def remove_texture(self, texture_id: str) -> Optional[TextureItem]:
        for i, t in enumerate(self.library):
            if t.id == texture_id:
                self._dirty = True
                return self.library.pop(i)
        return None

    def find_texture(self, texture_id: str) -> Optional[TextureItem]:
        for t in self.library:
            if t.id == texture_id:
                return t
        return None

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "atlas_list": [a.to_dict() for a in self.atlas_list],
            "library": [t.to_dict() for t in self.library],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectModel":
        return cls(
            version=data.get("version", PROJECT_VERSION),
            atlas_list=[
                AtlasModel.from_dict(a) for a in data.get("atlas_list", [])
            ],
            library=[
                TextureItem.from_dict(t) for t in data.get("library", [])
            ],
        )
