"""截图服务 - 管理截图文件的保存、清理"""

import os
import time
from typing import Optional

from PySide6.QtGui import QPixmap

from utils.constants import SCREENSHOT_DIR_NAME, get_runtime_dir


class ScreenshotService:
    """截图文件管理服务"""

    @classmethod
    def get_screenshot_dir(cls) -> str:
        """获取截图保存目录（工具根目录下的 ScreenShot 文件夹）"""
        base_dir = get_runtime_dir()
        screenshot_dir = os.path.join(base_dir, SCREENSHOT_DIR_NAME)
        os.makedirs(screenshot_dir, exist_ok=True)
        return screenshot_dir

    @classmethod
    def save_screenshot(cls, pixmap: QPixmap, name_prefix: str = "screenshot") -> Optional[str]:
        """保存截图到 ScreenShot 目录

        Args:
            pixmap: 截图 QPixmap
            name_prefix: 文件名前缀

        Returns:
            保存后的文件路径，失败返回 None
        """
        if pixmap.isNull():
            return None

        screenshot_dir = cls.get_screenshot_dir()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        # 加毫秒避免冲突
        ms = int(time.time() * 1000) % 1000
        filename = f"{name_prefix}_{timestamp}_{ms:03d}.png"
        file_path = os.path.join(screenshot_dir, filename)

        try:
            pixmap.save(file_path, "PNG")
            return file_path
        except Exception as e:
            print(f"截图保存失败: {e}")
            return None

    @classmethod
    def get_screenshot_count(cls) -> int:
        """获取截图缓存数量"""
        screenshot_dir = cls.get_screenshot_dir()
        if not os.path.exists(screenshot_dir):
            return 0
        return len([
            f for f in os.listdir(screenshot_dir)
            if f.lower().endswith(('.png', '.jpg', '.jpeg'))
        ])

    @classmethod
    def get_screenshot_size_mb(cls) -> float:
        """获取截图缓存总大小（MB）"""
        screenshot_dir = cls.get_screenshot_dir()
        if not os.path.exists(screenshot_dir):
            return 0.0
        total = 0
        for f in os.listdir(screenshot_dir):
            fp = os.path.join(screenshot_dir, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
        return total / (1024 * 1024)

    @classmethod
    def clear_screenshots(cls) -> int:
        """清理所有截图缓存

        Returns:
            删除的文件数量
        """
        screenshot_dir = cls.get_screenshot_dir()
        if not os.path.exists(screenshot_dir):
            return 0

        count = 0
        for f in os.listdir(screenshot_dir):
            fp = os.path.join(screenshot_dir, f)
            if os.path.isfile(fp):
                try:
                    os.remove(fp)
                    count += 1
                except Exception:
                    pass
        return count
