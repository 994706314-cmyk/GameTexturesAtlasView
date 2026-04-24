"""贴图素材数据模型"""

import os
import uuid
import base64
import hashlib
import tempfile
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
    tag: str = ""  # 标记类型：""(无)、"E"(自发光)、"A"(半透明)、"M"(Mask)、"C1"/"C2"/"C3"(自定义)
    quality_tier: str = "None"  # 画质类型：None/High/VeryHigh/Extreme

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

    def to_dict(self, full_mode: bool = False) -> dict:
        """序列化为字典

        Args:
            full_mode: 如果为 True，会嵌入原图的 base64 数据（全量保存模式）
        """
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
        if self.tag:
            d["tag"] = self.tag
        if self.quality_tier and self.quality_tier != "None":
            d["quality_tier"] = self.quality_tier

        # 将缩略图以 base64 嵌入存档，解决分享后缩略图丢失问题
        if self.thumbnail_path and os.path.exists(self.thumbnail_path):
            try:
                with open(self.thumbnail_path, "rb") as f:
                    d["thumbnail_data"] = base64.b64encode(f.read()).decode("ascii")
            except Exception:
                pass  # 读取失败则不嵌入，降级为路径引用

        # 全量保存模式：嵌入原图数据
        if full_mode and self.original_path and os.path.exists(self.original_path):
            try:
                with open(self.original_path, "rb") as f:
                    d["original_data"] = base64.b64encode(f.read()).decode("ascii")
                # 记录原图扩展名，还原时需要
                d["original_ext"] = os.path.splitext(self.original_path)[1].lower()
            except Exception:
                pass  # 读取失败不嵌入

        return d

    @classmethod
    def _get_cache_dir(cls) -> str:
        """获取缩略图缓存目录"""
        cache_dir = os.path.join(tempfile.gettempdir(), "tatlas_thumbnails")
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir

    @classmethod
    def from_dict(cls, data: dict) -> "TextureItem":
        thumbnail_path = data.get("thumbnail_path")
        thumbnail_data = data.get("thumbnail_data")

        # 如果存档中有嵌入的缩略图数据，且本地缓存不存在，则还原到缓存
        if thumbnail_data:
            if not thumbnail_path or not os.path.exists(thumbnail_path):
                try:
                    raw = base64.b64decode(thumbnail_data)
                    # 用内容哈希作为文件名，避免冲突
                    content_hash = hashlib.md5(raw).hexdigest()
                    restored_path = os.path.join(
                        cls._get_cache_dir(), f"{content_hash}_restored.png"
                    )
                    if not os.path.exists(restored_path):
                        with open(restored_path, "wb") as f:
                            f.write(raw)
                    thumbnail_path = restored_path
                except Exception:
                    pass  # 还原失败则 thumbnail_path 保持原样

        # 如果存档中有嵌入的原图数据，且本地文件不存在，则还原到缓存
        original_path = data.get("original_path", "")
        original_data = data.get("original_data")
        if original_data:
            if not original_path or not os.path.exists(original_path):
                try:
                    raw = base64.b64decode(original_data)
                    content_hash = hashlib.md5(raw).hexdigest()
                    ext = data.get("original_ext", ".png")
                    restored_path = os.path.join(
                        cls._get_cache_dir(), f"{content_hash}_original{ext}"
                    )
                    if not os.path.exists(restored_path):
                        with open(restored_path, "wb") as f:
                            f.write(raw)
                    original_path = restored_path
                except Exception:
                    pass

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            original_path=original_path,
            original_size=tuple(data.get("original_size", [64, 64])),
            display_size=tuple(data.get("display_size", [64, 64])),
            name=data.get("name", "未命名"),
            thumbnail_path=thumbnail_path,
            is_screenshot=data.get("is_screenshot", False),
            tag=data.get("tag", ""),
            quality_tier=data.get("quality_tier", "None"),
        )
