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

    def to_dict(self, full_mode: bool = False) -> dict:
        d = {
            "version": self.version,
            "atlas_list": [a.to_dict(full_mode=full_mode) for a in self.atlas_list],
            "library": [t.to_dict(full_mode=full_mode) for t in self.library],
        }
        if full_mode:
            d["full_mode"] = True
        return d

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

    def merge_from(self, other: "ProjectModel") -> dict:
        """将另一个项目的数据合并到当前项目中（追加模式）

        Returns:
            合并统计信息字典 {"textures_added", "textures_skipped", "atlases_added"}
        """
        import uuid

        stats = {"textures_added": 0, "textures_skipped": 0, "atlases_added": 0}

        # 构建当前素材的名称+尺寸集合，用于去重判断
        existing_keys = set()
        for tex in self.library:
            key = (tex.name, tex.display_size[0], tex.display_size[1])
            existing_keys.add(key)

        # 构建 id 映射表（旧 id → 新 id），用于合图中贴图引用更新
        id_map = {}

        for tex in other.library:
            key = (tex.name, tex.display_size[0], tex.display_size[1])
            if key in existing_keys:
                stats["textures_skipped"] += 1
                # 即使跳过，也记录映射（找到已有的同名贴图 id）
                for existing_tex in self.library:
                    if (existing_tex.name, existing_tex.display_size[0],
                            existing_tex.display_size[1]) == key:
                        id_map[tex.id] = existing_tex.id
                        break
                continue

            # 生成新 id 避免冲突
            old_id = tex.id
            tex.id = str(uuid.uuid4())
            id_map[old_id] = tex.id
            self.library.append(tex)
            existing_keys.add(key)
            stats["textures_added"] += 1

        # 追加合图
        for atlas in other.atlas_list:
            atlas.id = str(uuid.uuid4())
            # 更新合图内贴图引用
            for pt in atlas.placed_textures:
                old_tex_id = pt.texture.id
                if old_tex_id in id_map:
                    pt.texture.id = id_map[old_tex_id]
                    # 尝试找到本项目中的贴图引用
                    local_tex = self.find_texture(id_map[old_tex_id])
                    if local_tex:
                        pt.texture = local_tex
            self.atlas_list.append(atlas)
            stats["atlases_added"] += 1

        if stats["textures_added"] > 0 or stats["atlases_added"] > 0:
            self._dirty = True

        return stats
