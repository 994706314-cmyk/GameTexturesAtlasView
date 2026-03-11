"""图片服务：缩略图生成、缓存与异步加载"""

import os
import hashlib
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional

from PIL import Image
from PySide6.QtCore import QThread, Signal, QObject

from utils.constants import SUPPORTED_IMAGE_FORMATS, THUMBNAIL_SIZE, THUMBNAIL_QUALITY_HD


class ImageService:
    """图片处理服务"""

    _cache_dir: str = ""

    @classmethod
    def get_cache_dir(cls) -> str:
        if not cls._cache_dir:
            cls._cache_dir = os.path.join(tempfile.gettempdir(), "tatlas_thumbnails")
            os.makedirs(cls._cache_dir, exist_ok=True)
        return cls._cache_dir

    @classmethod
    def generate_thumbnail(cls, image_path: str, size: int = THUMBNAIL_SIZE) -> Optional[str]:
        """生成缩略图并缓存到临时目录，返回缩略图路径"""
        if not os.path.exists(image_path):
            return None

        path_hash = hashlib.md5(image_path.encode()).hexdigest()
        thumb_path = os.path.join(cls.get_cache_dir(), f"{path_hash}_{size}.png")

        if os.path.exists(thumb_path):
            return thumb_path

        try:
            with Image.open(image_path) as img:
                img = img.convert("RGBA")
                img.thumbnail((size, size), Image.Resampling.LANCZOS)
                img.save(thumb_path, "PNG")
            return thumb_path
        except Exception as e:
            print(f"缩略图生成失败 [{image_path}]: {e}")
            return None

    @classmethod
    def generate_thumbnail_hd(cls, image_path: str) -> Optional[str]:
        """生成高清缩略图"""
        return cls.generate_thumbnail(image_path, size=THUMBNAIL_QUALITY_HD)

    @classmethod
    def clear_thumbnail_cache(cls):
        """清除所有缩略图缓存"""
        cache_dir = cls.get_cache_dir()
        if os.path.exists(cache_dir):
            for f in os.listdir(cache_dir):
                try:
                    os.remove(os.path.join(cache_dir, f))
                except Exception:
                    pass

    @classmethod
    def get_image_size(cls, image_path: str) -> Optional[Tuple[int, int]]:
        """获取图片的原始尺寸"""
        try:
            with Image.open(image_path) as img:
                return img.size
        except Exception as e:
            print(f"读取图片尺寸失败 [{image_path}]: {e}")
            return None

    @classmethod
    def scan_directory(cls, dir_path: str) -> List[str]:
        """递归扫描文件夹，返回所有支持格式的图片路径"""
        result = []
        for root, _, files in os.walk(dir_path):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in SUPPORTED_IMAGE_FORMATS:
                    result.append(os.path.join(root, f))
        result.sort()
        return result

    @classmethod
    def is_supported_format(cls, file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        return ext in SUPPORTED_IMAGE_FORMATS


class ThumbnailWorker(QThread):
    """异步缩略图加载线程"""
    progress = Signal(int, int)           # (当前索引, 总数)
    thumbnail_ready = Signal(str, str)    # (图片路径, 缩略图路径)
    finished_all = Signal()

    def __init__(self, image_paths: List[str], parent: QObject = None):
        super().__init__(parent)
        self._image_paths = image_paths
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        total = len(self._image_paths)
        for i, path in enumerate(self._image_paths):
            if self._cancelled:
                break
            thumb = ImageService.generate_thumbnail(path)
            if thumb:
                self.thumbnail_ready.emit(path, thumb)
            self.progress.emit(i + 1, total)
        self.finished_all.emit()
