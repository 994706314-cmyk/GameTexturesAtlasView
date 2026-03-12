"""检查模式 - 图集分割服务

使用梯次网格切割策略（从大到小）：
1. 从图集整图尺寸开始（如 2048），检查是否整图就是一个纹理
2. 依次按 1024 → 512 → 256 的网格尺寸切割
3. 在每个网格位置检查是否有实际内容（非空区域）
4. 对已被大块覆盖的区域不再细分

这样每个图集最多切出几十个纹理块（而非几百个碎片），
且每个块代表一个完整的纹理图，适合跨图集比对。
"""

import os
from typing import List, Optional, Callable, Tuple

import cv2
import numpy as np
import imagehash
from PIL import Image

from models.reverse_atlas_item import SubRegion, ReverseAtlasItem
from utils.constants import (
    DEFAULT_HASH_SIZE,
    DEFAULT_NORMALIZE_SIZE,
    SUPPORTED_IMAGE_FORMATS,
    DEFAULT_ATLAS_SUFFIX,
)

# 梯次切割的尺寸列表（从大到小）
# 图集本身可能是 2048 或 4096，所以先检查整图，再逐级细分
TIER_SIZES = [2048, 1024, 512, 256]

# 判定网格块"有内容"的阈值：非透明像素占比超过此值才认为有内容
CONTENT_RATIO_THRESHOLD = 0.05  # 5%


class AtlasSegmenter:
    """图集分割服务：从 atlas 中提取子图区域并计算哈希

    采用梯次网格切割策略：从大块到小块逐级识别纹理。
    """

    @staticmethod
    def is_atlas_file(file_path: str, suffix: str = DEFAULT_ATLAS_SUFFIX) -> bool:
        """判断文件是否为符合后缀规则的图集文件"""
        if not os.path.isfile(file_path):
            return False
        name, ext = os.path.splitext(os.path.basename(file_path))
        if ext.lower() not in SUPPORTED_IMAGE_FORMATS:
            return False
        return name.endswith(suffix)

    @staticmethod
    def scan_atlas_files(dir_path: str, suffix: str = DEFAULT_ATLAS_SUFFIX) -> List[str]:
        """递归扫描目录，返回所有符合后缀规则的图集文件路径"""
        result = []
        if not os.path.isdir(dir_path):
            return result
        for root, _, files in os.walk(dir_path):
            for f in files:
                full_path = os.path.join(root, f)
                if AtlasSegmenter.is_atlas_file(full_path, suffix):
                    result.append(full_path)
        result.sort()
        return result

    @staticmethod
    def segment_atlas(
        image_path: str,
        min_area: int = 0,  # 保留兼容，实际不再使用
        hash_size: int = DEFAULT_HASH_SIZE,
        normalize_size: int = DEFAULT_NORMALIZE_SIZE,
    ) -> List[SubRegion]:
        """分割图集，提取所有子图纹理块

        使用梯次网格切割：从整图开始，逐级按 2048→1024→512→256 切割。
        每个网格位置检查是否有实际内容，有内容的区域作为一个纹理块。
        已被大块覆盖的区域不再细分。

        Args:
            image_path: 图集文件路径
            hash_size: 感知哈希的尺寸参数
            normalize_size: 统一缩放的对比尺寸

        Returns:
            SubRegion 列表
        """
        if not os.path.exists(image_path):
            return []

        img = AtlasSegmenter._imread_unicode(image_path)
        if img is None:
            return []

        h, w = img.shape[:2]

        # 构建 alpha 掩码用于判定"有内容"
        if len(img.shape) == 3 and img.shape[2] == 4:
            alpha = img[:, :, 3]
        else:
            # 无 alpha 通道，全部视为有内容
            alpha = np.full((h, w), 255, dtype=np.uint8)

        # ---- 梯次网格切割 ----
        # occupied 记录已被识别为纹理块的区域（避免重复）
        occupied = np.zeros((h, w), dtype=bool)

        texture_rects: List[Tuple[int, int, int, int]] = []  # (x, y, w, h)

        for tier_size in TIER_SIZES:
            if tier_size > w and tier_size > h:
                continue
            # 如果 tier_size == 图集尺寸，检查整图是否是单个纹理
            # 否则按网格切割
            AtlasSegmenter._scan_tier(
                alpha, occupied, texture_rects,
                w, h, tier_size,
            )

        # 如果所有层级都没找到纹理块，把整图作为一个区域
        if not texture_rects:
            texture_rects = [(0, 0, w, h)]

        # ---- 构建 SubRegion 列表 ----
        regions = []
        try:
            pil_img = Image.open(image_path).convert("RGBA")
        except Exception:
            return []

        for x, y, rw, rh in texture_rects:
            try:
                sub_img = pil_img.crop((x, y, x + rw, y + rh))
            except Exception:
                continue

            phash_val, dhash_val = AtlasSegmenter._compute_hashes(
                sub_img, hash_size, normalize_size
            )
            region = SubRegion(
                x=x, y=y, width=rw, height=rh,
                phash=phash_val, dhash=dhash_val,
            )
            regions.append(region)

        pil_img.close()
        regions.sort(key=lambda r: (r.y, r.x))
        return regions

    @staticmethod
    def _scan_tier(
        alpha: np.ndarray,
        occupied: np.ndarray,
        texture_rects: List[Tuple[int, int, int, int]],
        img_w: int, img_h: int,
        tier_size: int,
    ):
        """在指定网格尺寸下扫描所有位置，找出有内容且未被占用的纹理块。

        对于每个 tier_size x tier_size 的网格块：
        1. 检查该区域是否大部分已被更大的块占用 → 跳过
        2. 检查该区域是否有足够的实际内容 → 是则标记为纹理块
        """
        # 按网格遍历（允许最后一行/列不足 tier_size 的情况）
        rows = (img_h + tier_size - 1) // tier_size
        cols = (img_w + tier_size - 1) // tier_size

        for row in range(rows):
            for col in range(cols):
                x = col * tier_size
                y = row * tier_size
                # 实际块大小（处理边界情况）
                bw = min(tier_size, img_w - x)
                bh = min(tier_size, img_h - y)

                if bw < 16 or bh < 16:
                    continue

                # 检查是否大部分已被占用
                occ_block = occupied[y:y + bh, x:x + bw]
                occupied_ratio = np.count_nonzero(occ_block) / (bw * bh)
                if occupied_ratio > 0.5:
                    # 超过 50% 已被更大的块占用，跳过
                    continue

                # 检查是否有内容
                alpha_block = alpha[y:y + bh, x:x + bw]
                # 只看未被占用区域的内容
                free_mask = ~occ_block
                free_count = np.count_nonzero(free_mask)
                if free_count == 0:
                    continue

                # 在自由区域内检查有内容（alpha > 10）的像素占比
                content_pixels = np.count_nonzero(
                    (alpha_block > 10) & free_mask
                )
                content_ratio = content_pixels / free_count

                if content_ratio >= CONTENT_RATIO_THRESHOLD:
                    # 该块有内容，标记为纹理块
                    texture_rects.append((x, y, bw, bh))
                    # 标记已占用
                    occupied[y:y + bh, x:x + bw] = True

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _imread_unicode(file_path: str, flags: int = cv2.IMREAD_UNCHANGED) -> Optional[np.ndarray]:
        """读取含中文/Unicode路径的图片，含重试和降级方案"""
        import time

        # 尝试 OpenCV 读取（最多重试 3 次）
        for attempt in range(3):
            try:
                data = np.fromfile(file_path, dtype=np.uint8)
                img = cv2.imdecode(data, flags)
                if img is not None:
                    return img
            except Exception:
                pass
            if attempt < 2:
                time.sleep(0.1)  # 短暂等待后重试

        # OpenCV 失败时降级到 PIL 读取
        try:
            from PIL import Image as _PILImage
            pil_img = _PILImage.open(file_path)
            pil_img = pil_img.convert("RGBA")
            np_arr = np.array(pil_img)
            # PIL 是 RGBA，OpenCV 需要 BGRA
            img = cv2.cvtColor(np_arr, cv2.COLOR_RGBA2BGRA)
            return img
        except Exception:
            return None

    @staticmethod
    def _compute_hashes(
        pil_img: Image.Image,
        hash_size: int = DEFAULT_HASH_SIZE,
        normalize_size: int = DEFAULT_NORMALIZE_SIZE,
    ) -> tuple:
        """计算子图的感知哈希和差异哈希

        先将图片统一缩放到 normalize_size，确保跨分辨率对比一致性。

        Returns:
            (phash_str, dhash_str)
        """
        try:
            normalized = pil_img.resize(
                (normalize_size, normalize_size),
                Image.Resampling.LANCZOS
            ).convert("RGB")

            phash_val = str(imagehash.phash(normalized, hash_size=hash_size))
            dhash_val = str(imagehash.dhash(normalized, hash_size=hash_size))
            return phash_val, dhash_val
        except Exception as e:
            print(f"哈希计算失败: {e}")
            return "", ""

    @staticmethod
    def build_atlas_item(
        file_path: str,
        suffix: str = DEFAULT_ATLAS_SUFFIX,
        min_area: int = 0,
        hash_size: int = DEFAULT_HASH_SIZE,
        normalize_size: int = DEFAULT_NORMALIZE_SIZE,
    ) -> Optional[ReverseAtlasItem]:
        """从文件路径构建完整的 ReverseAtlasItem（含分割和哈希）"""
        if not os.path.exists(file_path):
            return None

        try:
            with Image.open(file_path) as img:
                image_size = img.size
        except Exception:
            return None

        name = os.path.basename(file_path)
        atlas_item = ReverseAtlasItem(
            name=name,
            file_path=file_path,
            image_size=image_size,
        )

        regions = AtlasSegmenter.segment_atlas(
            file_path, min_area, hash_size, normalize_size
        )
        for region in regions:
            atlas_item.add_region(region)

        atlas_item.is_segmented = True
        return atlas_item

    @staticmethod
    def batch_build(
        file_paths: List[str],
        suffix: str = DEFAULT_ATLAS_SUFFIX,
        min_area: int = 0,
        hash_size: int = DEFAULT_HASH_SIZE,
        normalize_size: int = DEFAULT_NORMALIZE_SIZE,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[ReverseAtlasItem]:
        """批量构建图集数据"""
        items = []
        total = len(file_paths)
        for i, path in enumerate(file_paths):
            item = AtlasSegmenter.build_atlas_item(
                path, suffix, min_area, hash_size, normalize_size
            )
            if item:
                items.append(item)
            if progress_callback:
                progress_callback(i + 1, total)
        return items
