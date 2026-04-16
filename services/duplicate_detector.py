"""检查模式 - 重复检测服务

哈希分桶快速检测：梯次网格 + 内容哈希
- 从最大尺寸（2048）开始逐级递减到 16×16
- 在每个尺寸级别，将所有图集切成网格块
- 对每个块的有效像素（排除透明、纯黑、纯白）做量化后计算 MD5 哈希
- 哈希相同的跨图集块即为重复（O(N) 而非 O(N²)）
- 已识别为重复的区域不再参与后续更小尺寸的检测
- 仅比较不同图集之间的块，同一图集内不比较
- 支持明度查重（感知哈希近似匹配）：对 MD5 不同但 pHash 相近的块标记为近似重复
"""

import hashlib
import time
from collections import defaultdict
from typing import List, Optional, Callable, Dict, Tuple, Set

import numpy as np
from PIL import Image
import imagehash

from models.reverse_atlas_item import SubRegion, ReverseAtlasItem
from models.duplicate_result import DuplicateResult


# 梯次检测的尺寸列表（从大到小）
TIER_SIZES = [2048, 1024, 512, 256, 128, 64, 32, 16]

# 判定网格块"有有效内容"的阈值：有效像素（非纯黑非纯白非全透明）占比
MIN_VALID_PIXEL_RATIO = 0.03  # 至少 3% 的像素是有效的才参与对比

# 像素完全匹配的容差（考虑压缩误差）
PIXEL_TOLERANCE = 3  # RGB 各通道差值 <= 3 视为一致

# 量化因子：PIXEL_TOLERANCE + 1，用于哈希前的像素量化以吸收压缩误差
QUANTIZE_STEP = PIXEL_TOLERANCE + 1  # = 4


def _format_eta(seconds: float) -> str:
    """格式化剩余时间"""
    if seconds < 0 or seconds > 86400:
        return ""
    seconds = int(seconds)
    if seconds < 60:
        return f"  预计剩余 {seconds} 秒"
    elif seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"  预计剩余 {m}分{s}秒"
    else:
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        return f"  预计剩余 {h}时{m}分"


class _AtlasImage:
    """缓存的图集图像数据"""
    __slots__ = ('atlas', 'rgba_array', 'width', 'height')

    def __init__(self, atlas: ReverseAtlasItem, rgba_array: np.ndarray):
        self.atlas = atlas
        self.rgba_array = rgba_array  # shape: (H, W, 4), dtype=uint8
        self.height, self.width = rgba_array.shape[:2]


class _GridBlock:
    """一个网格块的引用"""
    __slots__ = ('atlas_idx', 'x', 'y', 'size', 'atlas_id', 'phash')

    def __init__(self, atlas_idx: int, x: int, y: int, size: int, atlas_id: str):
        self.atlas_idx = atlas_idx
        self.x = x
        self.y = y
        self.size = size
        self.atlas_id = atlas_id
        self.phash = None  # 感知哈希，延迟计算


def _compute_block_phash(img_data: np.ndarray, x: int, y: int, size: int):
    """计算网格块的感知哈希 (pHash)

    将块裁切为 PIL Image 后通过 imagehash.phash 生成感知哈希。
    返回 imagehash.ImageHash 对象，支持直接做减法得到汉明距离。
    如果块内有效像素不足则返回 None。
    """
    block = img_data[y:y + size, x:x + size]
    total_pixels = size * size

    # 有效性检查
    alpha = block[:, :, 3]
    opaque_mask = alpha > 10
    opaque_count = np.count_nonzero(opaque_mask)
    if opaque_count < total_pixels * MIN_VALID_PIXEL_RATIO:
        return None

    # 转为 PIL Image（只取 RGB）用于 phash
    rgb_block = block[:, :, :3]
    pil_block = Image.fromarray(rgb_block, mode='RGB')
    return imagehash.phash(pil_block, hash_size=16)


def _block_has_content(img_data: np.ndarray, x: int, y: int, size: int) -> bool:
    """检查网格块是否有有效内容（非全透明、非纯黑、非纯白）

    返回 True 表示该块有足够的有效像素值得参与对比。
    """
    block = img_data[y:y + size, x:x + size]
    total_pixels = size * size
    if total_pixels == 0:
        return False

    # alpha 通道：大部分透明则无内容
    alpha = block[:, :, 3]
    opaque_mask = alpha > 10  # alpha > 10 才算不透明
    opaque_count = np.count_nonzero(opaque_mask)
    if opaque_count < total_pixels * MIN_VALID_PIXEL_RATIO:
        return False

    # 在不透明像素中，排除纯黑和纯白
    rgb = block[:, :, :3]
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]

    black_mask = (r <= 1) & (g <= 1) & (b <= 1)
    white_mask = (r >= 254) & (g >= 254) & (b >= 254)

    valid_mask = opaque_mask & (~black_mask) & (~white_mask)
    valid_count = np.count_nonzero(valid_mask)

    return valid_count >= total_pixels * MIN_VALID_PIXEL_RATIO


def _compute_block_hash(img_data: np.ndarray, x: int, y: int, size: int) -> Optional[str]:
    """计算网格块的内容哈希值

    步骤：
    1. 提取块的 RGBA 数据
    2. 构建有效像素掩码（不透明、非纯黑、非纯白）
    3. 对有效像素的 RGB 做量化（除以 QUANTIZE_STEP 取整）以吸收压缩误差
    4. 将无效像素置零（确保不影响哈希）
    5. 对量化后的像素数组计算 MD5

    如果有效像素不足则返回 None。
    """
    block = img_data[y:y + size, x:x + size]
    total_pixels = size * size

    alpha = block[:, :, 3]
    opaque_mask = alpha > 10

    rgb = block[:, :, :3]
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]

    black_mask = (r <= 1) & (g <= 1) & (b <= 1)
    white_mask = (r >= 254) & (g >= 254) & (b >= 254)

    valid_mask = opaque_mask & (~black_mask) & (~white_mask)
    valid_count = np.count_nonzero(valid_mask)

    if valid_count < total_pixels * MIN_VALID_PIXEL_RATIO:
        return None

    # 构建用于哈希的数组：量化有效像素 RGB，无效位置置零
    # 量化：pixel // QUANTIZE_STEP，消除 ±PIXEL_TOLERANCE 范围内的差异
    quantized = (rgb // QUANTIZE_STEP).astype(np.uint8)

    # 将无效像素全部置零，确保它们不影响哈希值
    invalid_mask = ~valid_mask
    quantized[invalid_mask] = 0

    # 计算 MD5 哈希
    return hashlib.md5(quantized.tobytes()).hexdigest()


class DuplicateDetector:
    """重复内容检测服务 - 哈希分桶快速检测"""

    @staticmethod
    def detect(
        atlases: List[ReverseAtlasItem],
        mode: str = "exact",
        fuzzy_threshold: int = 0,
        min_tier_size: int = 64,
        perceptual_threshold: int = 0,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> DuplicateResult:
        """执行梯次哈希分桶重复检测

        从 2048 到 min_tier_size 逐级检测：
        1. 在每个尺寸级别，将图集切成网格块
        2. 对每个块计算内容哈希（量化后的有效像素 MD5）
        3. 哈希相同且来自不同图集的块即为重复
        4. 已识别为重复的区域标记 occupied，不再参与后续检测
        5. 若 perceptual_threshold > 0，则在精确匹配后对剩余块进行
           感知哈希(pHash)近似匹配，识别明度/颜色偏移的近似重复

        复杂度从 O(N²) 降至 O(N)，速度提升数十到数百倍。

        Args:
            atlases: 图集列表
            mode: 仅 "exact" 有效
            fuzzy_threshold: 已废弃
            min_tier_size: 最低检测档位（默认 64）
            perceptual_threshold: 明度查重比率（0~100%），0=不启用
            progress_callback: 进度回调 (current, total, message)
            cancel_check: 取消检查

        Returns:
            DuplicateResult
        """
        result = DuplicateResult(
            total_atlases=len(atlases),
            analysis_mode="exact",
        )

        if len(atlases) < 2:
            if progress_callback:
                progress_callback(100, 100, "至少需要 2 个图集才能进行跨图集比较")
            return result

        time_start = time.time()

        # ---- 加载所有图集图像 ----
        if progress_callback:
            progress_callback(0, 100, "正在加载图集图像...")

        atlas_images: List[Optional[_AtlasImage]] = []
        for idx, atlas in enumerate(atlases):
            if cancel_check and cancel_check():
                return result
            try:
                pil_img = Image.open(atlas.file_path).convert("RGBA")
                arr = np.array(pil_img, dtype=np.uint8)
                pil_img.close()
                atlas_images.append(_AtlasImage(atlas, arr))
            except Exception as e:
                print(f"加载图集失败: {atlas.file_path} - {e}")
                atlas_images.append(None)

            if progress_callback:
                pct = int((idx + 1) / len(atlases) * 5)
                progress_callback(pct, 100, f"加载图集 ({idx + 1}/{len(atlases)})...")

        # 过滤掉加载失败的
        valid_images = [(i, img) for i, img in enumerate(atlas_images) if img is not None]
        if len(valid_images) < 2:
            if progress_callback:
                progress_callback(100, 100, "有效图集不足 2 个")
            return result

        # ---- 为每个图集建立 occupied 掩码 ----
        occupied: Dict[int, np.ndarray] = {}
        for atlas_idx, img in valid_images:
            occupied[atlas_idx] = np.zeros((img.height, img.width), dtype=bool)

        # ---- 梯次检测 ----
        # 根据 min_tier_size 过滤检测级别
        effective_tiers = [s for s in TIER_SIZES if s >= min_tier_size]
        active_tiers = []
        for tier_size in effective_tiers:
            count = sum(1 for _, img in valid_images
                        if img.width >= tier_size or img.height >= tier_size)
            if count >= 1:
                active_tiers.append(tier_size)

        if not active_tiers:
            if progress_callback:
                progress_callback(100, 100, "图集尺寸太小，无法进行网格检测")
            return result

        total_tiers = len(active_tiers)
        tier_progress_base = 8  # 前 8% 用于加载
        tier_progress_range = 90  # 8%~98% 用于梯次检测

        all_groups = []  # 收集所有重复组

        for tier_idx, tier_size in enumerate(active_tiers):
            if cancel_check and cancel_check():
                return result

            tier_pct_start = tier_progress_base + int(tier_idx / total_tiers * tier_progress_range)
            tier_pct_end = tier_progress_base + int((tier_idx + 1) / total_tiers * tier_progress_range)

            if progress_callback:
                progress_callback(
                    tier_pct_start, 100,
                    f"检测 {tier_size}×{tier_size} 级别..."
                )

            # ---- 收集所有有效块并计算哈希 ----
            all_blocks: List[_GridBlock] = []
            block_count = 0

            for atlas_idx, img in valid_images:
                cols = img.width // tier_size
                rows = img.height // tier_size

                for row in range(rows):
                    for col in range(cols):
                        x = col * tier_size
                        y = row * tier_size

                        # 检查是否已被占用（超过 50% 区域已识别为重复）
                        occ_block = occupied[atlas_idx][y:y + tier_size, x:x + tier_size]
                        if np.count_nonzero(occ_block) > tier_size * tier_size * 0.5:
                            continue

                        # 检查是否有有效内容
                        if not _block_has_content(img.rgba_array, x, y, tier_size):
                            continue

                        all_blocks.append(_GridBlock(
                            atlas_idx=atlas_idx,
                            x=x, y=y,
                            size=tier_size,
                            atlas_id=img.atlas.id,
                        ))
                        block_count += 1

            if block_count < 2:
                continue

            # ---- 计算每个块的哈希并分桶 ----
            # hash_buckets: hash_value -> list of _GridBlock
            hash_buckets: Dict[str, List[_GridBlock]] = defaultdict(list)
            hash_start = time.time()

            for bi, block in enumerate(all_blocks):
                if cancel_check and cancel_check():
                    return result

                img = atlas_images[block.atlas_idx]
                h = _compute_block_hash(img.rgba_array, block.x, block.y, block.size)
                if h is not None:
                    hash_buckets[h].append(block)

                # 进度更新
                if progress_callback and bi % max(1, block_count // 10) == 0:
                    pct = tier_pct_start + int(
                        (bi + 1) / block_count * (tier_pct_end - tier_pct_start)
                    )
                    elapsed = time.time() - hash_start
                    if bi > 5 and elapsed > 0.1:
                        rate = bi / elapsed
                        remaining = (block_count - bi) / rate
                        eta_str = _format_eta(remaining)
                    else:
                        eta_str = ""
                    progress_callback(
                        min(pct, tier_pct_end - 1), 100,
                        f"哈希 {tier_size}×{tier_size} ({bi}/{block_count}){eta_str}"
                    )

            # ---- 从桶中提取跨图集的重复组 ----
            for hash_val, bucket_blocks in hash_buckets.items():
                if len(bucket_blocks) < 2:
                    continue

                # 按图集分组
                by_atlas: Dict[int, List[_GridBlock]] = defaultdict(list)
                for blk in bucket_blocks:
                    by_atlas[blk.atlas_idx].append(blk)

                # 至少来自 2 个不同图集才算跨图集重复
                if len(by_atlas) < 2:
                    continue

                # 从每个图集中选取尚未被占用的块，合并为一个组
                group_blocks: List[_GridBlock] = []
                group_atlas_indices: Set[int] = set()

                for atlas_idx, blocks in by_atlas.items():
                    for blk in blocks:
                        occ_block = occupied[atlas_idx][blk.y:blk.y + blk.size, blk.x:blk.x + blk.size]
                        if np.count_nonzero(occ_block) > blk.size * blk.size * 0.5:
                            continue
                        group_blocks.append(blk)
                        group_atlas_indices.add(atlas_idx)

                # 确保合并后仍有 ≥2 个不同图集
                if len(group_atlas_indices) < 2 or len(group_blocks) < 2:
                    continue

                # 标记所有参与块为已占用
                for blk in group_blocks:
                    occupied[blk.atlas_idx][blk.y:blk.y + blk.size, blk.x:blk.x + blk.size] = True

                # 创建 SubRegion 对象列表
                regions = []
                atlas_list = []
                for blk in group_blocks:
                    region = SubRegion(
                        x=blk.x, y=blk.y,
                        width=blk.size, height=blk.size,
                        atlas_id=blk.atlas_id,
                    )
                    regions.append(region)
                    atlas_list.append(atlas_images[blk.atlas_idx].atlas)

                all_groups.append({
                    'tier_size': tier_size,
                    'regions': regions,
                    'atlases': atlas_list,
                })

        # ---- 构建结果（含组间去重合并）----
        if progress_callback:
            progress_callback(95, 100, "构建分析结果...")

        # ==== 感知哈希近似匹配（明度查重） ====
        perceptual_groups = []
        if perceptual_threshold > 0:
            if progress_callback:
                progress_callback(90, 100, "正在进行明度查重（感知哈希匹配）...")

            # 将百分比阈值转换为汉明距离阈值
            # pHash hash_size=16 → 256 bit → 最大汉明距离 256
            max_hamming = int(256 * perceptual_threshold / 100)

            # 收集所有未被精确匹配占用的有效块及其 pHash
            unmatched_blocks: List[_GridBlock] = []
            for tier_size in active_tiers:
                if cancel_check and cancel_check():
                    return result

                for atlas_idx, img in valid_images:
                    cols = img.width // tier_size
                    rows = img.height // tier_size

                    for row_i in range(rows):
                        for col_i in range(cols):
                            x = col_i * tier_size
                            y = row_i * tier_size

                            # 跳过已被精确匹配占用的
                            occ_block = occupied[atlas_idx][y:y + tier_size, x:x + tier_size]
                            if np.count_nonzero(occ_block) > tier_size * tier_size * 0.5:
                                continue

                            if not _block_has_content(img.rgba_array, x, y, tier_size):
                                continue

                            block = _GridBlock(
                                atlas_idx=atlas_idx,
                                x=x, y=y,
                                size=tier_size,
                                atlas_id=img.atlas.id,
                            )
                            # 计算感知哈希
                            ph = _compute_block_phash(img.rgba_array, x, y, tier_size)
                            if ph is not None:
                                block.phash = ph
                                unmatched_blocks.append(block)

            if progress_callback:
                progress_callback(92, 100,
                    f"明度查重：对 {len(unmatched_blocks)} 个未匹配块进行感知哈希比较...")

            # 按 tier_size 分组比较（同尺寸才能比较）
            by_tier: Dict[int, List[_GridBlock]] = defaultdict(list)
            for blk in unmatched_blocks:
                by_tier[blk.size].append(blk)

            for tier_size, tier_blocks in by_tier.items():
                if cancel_check and cancel_check():
                    return result
                if len(tier_blocks) < 2:
                    continue

                # 简单两两比较（已占用的块已被过滤，数量不会太多）
                used = set()
                for i in range(len(tier_blocks)):
                    if i in used:
                        continue
                    group_members = [tier_blocks[i]]
                    group_atlas_set = {tier_blocks[i].atlas_idx}

                    for j in range(i + 1, len(tier_blocks)):
                        if j in used:
                            continue
                        # 同图集内不比较
                        if tier_blocks[j].atlas_idx == tier_blocks[i].atlas_idx:
                            # 允许同图集的块加入组（但组中必须有跨图集的）
                            pass

                        dist = tier_blocks[i].phash - tier_blocks[j].phash
                        if dist <= max_hamming and dist > 0:
                            # 确保是不同图集
                            if tier_blocks[j].atlas_idx != tier_blocks[i].atlas_idx:
                                group_members.append(tier_blocks[j])
                                group_atlas_set.add(tier_blocks[j].atlas_idx)
                                used.add(j)

                    # 至少来自 2 个不同图集
                    if len(group_atlas_set) >= 2 and len(group_members) >= 2:
                        used.add(i)
                        # 计算组内最大汉明距离
                        max_dist_in_group = 0
                        for mi in range(len(group_members)):
                            for mj in range(mi + 1, len(group_members)):
                                d = group_members[mi].phash - group_members[mj].phash
                                if d > max_dist_in_group:
                                    max_dist_in_group = d

                        # 标记占用
                        for blk in group_members:
                            occupied[blk.atlas_idx][blk.y:blk.y + blk.size, blk.x:blk.x + blk.size] = True

                        # 创建 SubRegion
                        regions = []
                        atlas_list_for_group = []
                        for blk in group_members:
                            region = SubRegion(
                                x=blk.x, y=blk.y,
                                width=blk.size, height=blk.size,
                                atlas_id=blk.atlas_id,
                            )
                            regions.append(region)
                            atlas_list_for_group.append(atlas_images[blk.atlas_idx].atlas)

                        perceptual_groups.append({
                            'tier_size': tier_size,
                            'regions': regions,
                            'atlases': atlas_list_for_group,
                            'hamming_distance': max_dist_in_group,
                        })

            if progress_callback:
                progress_callback(95, 100,
                    f"明度查重完成，发现 {len(perceptual_groups)} 组近似重复")

        if progress_callback:
            progress_callback(96, 100, "合并分析结果...")

        # 先清空所有图集的 sub_regions（检测器统一管理）
        for atlas in atlases:
            atlas.clear_regions()

        # --- 组间去重合并：成员列表完全一致的组合并为一个 ---
        # 用每个组的成员签名（图集ID+坐标+尺寸 排序后的元组）作为 key
        merged_groups: Dict[tuple, dict] = {}
        for group_info in all_groups:
            regions = group_info['regions']
            atlases_for_group = group_info['atlases']

            # 构建成员签名：(atlas_id, x, y, w, h) 排序后作为 key
            members = []
            for region, atlas in zip(regions, atlases_for_group):
                members.append((atlas.id, region.x, region.y, region.width, region.height))
            signature = tuple(sorted(members))

            if signature in merged_groups:
                # 已有完全相同成员的组，取较大的 tier_size（保留更大块的信息）
                existing = merged_groups[signature]
                if group_info['tier_size'] > existing['tier_size']:
                    existing['tier_size'] = group_info['tier_size']
                # 无需再添加
            else:
                merged_groups[signature] = group_info

        # 收集所有需要添加的 regions
        atlas_regions: Dict[str, List[SubRegion]] = defaultdict(list)

        for group_info in merged_groups.values():
            regions = group_info['regions']
            atlases_for_group = group_info['atlases']

            region_ids = []
            atlas_ids = []
            for region, atlas in zip(regions, atlases_for_group):
                atlas_regions[atlas.id].append(region)
                region_ids.append(region.region_id)
                atlas_ids.append(atlas.id)

            result.add_group(
                region_ids=region_ids,
                atlas_ids=atlas_ids,
                match_type="exact",
                hamming_distance=0,
                tier_size=group_info['tier_size'],
            )

        # 添加感知哈希近似匹配组
        for group_info in perceptual_groups:
            regions = group_info['regions']
            atlases_for_group = group_info['atlases']

            region_ids = []
            atlas_ids = []
            for region, atlas in zip(regions, atlases_for_group):
                atlas_regions[atlas.id].append(region)
                region_ids.append(region.region_id)
                atlas_ids.append(atlas.id)

            result.add_group(
                region_ids=region_ids,
                atlas_ids=atlas_ids,
                match_type="fuzzy",
                hamming_distance=group_info.get('hamming_distance', 0),
                tier_size=group_info['tier_size'],
            )

        # 将 regions 注入图集
        for atlas in atlases:
            regions = atlas_regions.get(atlas.id, [])
            for region in regions:
                atlas.add_region(region)
            if regions:
                atlas.is_segmented = True

        result.total_regions_scanned = sum(
            len(regions) for regions in atlas_regions.values()
        )

        total_time = time.time() - time_start
        if progress_callback:
            progress_callback(
                100, 100,
                f"检测完成，发现 {result.group_count} 组重复，耗时 {total_time:.1f} 秒"
            )

        return result
