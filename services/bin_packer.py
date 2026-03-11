"""MaxRects-BSSF 矩形装箱算法"""

from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class PackRect:
    """待装箱矩形"""
    id: str
    width: int
    height: int


@dataclass
class PackResult:
    """装箱结果"""
    id: str
    x: int
    y: int
    width: int
    height: int


class MaxRectsBinPacker:
    """MaxRects Best Short Side Fit 装箱算法"""

    def __init__(self, bin_width: int, bin_height: int):
        self.bin_width = bin_width
        self.bin_height = bin_height
        self._free_rects: List[Tuple[int, int, int, int]] = []  # (x, y, w, h)
        self._free_rects.append((0, 0, bin_width, bin_height))

    def pack(self, rects: List[PackRect]) -> List[PackResult]:
        """执行装箱，返回放置结果列表（未能放入的不包含在结果中）"""
        sorted_rects = sorted(rects, key=lambda r: r.width * r.height, reverse=True)

        results = []
        for rect in sorted_rects:
            pos = self._find_best_position(rect.width, rect.height)
            if pos is None:
                continue

            bx, by = pos
            results.append(PackResult(
                id=rect.id, x=bx, y=by,
                width=rect.width, height=rect.height
            ))
            self._place_rect(bx, by, rect.width, rect.height)

        return results

    def _find_best_position(self, width: int, height: int) -> Optional[Tuple[int, int]]:
        """BSSF: 找到最短边差距最小的空闲矩形"""
        best_short_side = float('inf')
        best_long_side = float('inf')
        best_pos = None

        for fx, fy, fw, fh in self._free_rects:
            if width <= fw and height <= fh:
                leftover_h = abs(fw - width)
                leftover_v = abs(fh - height)
                short_side = min(leftover_h, leftover_v)
                long_side = max(leftover_h, leftover_v)

                if short_side < best_short_side or (
                    short_side == best_short_side and long_side < best_long_side
                ):
                    best_short_side = short_side
                    best_long_side = long_side
                    best_pos = (fx, fy)

        return best_pos

    def _place_rect(self, x: int, y: int, w: int, h: int):
        """放置矩形后更新空闲矩形列表"""
        new_free = []
        i = 0
        while i < len(self._free_rects):
            free = self._free_rects[i]
            split = self._split_free_rect(free, x, y, w, h)
            if split is not None:
                new_free.extend(split)
                self._free_rects.pop(i)
            else:
                i += 1

        self._free_rects.extend(new_free)
        self._prune_free_rects()

    def _split_free_rect(
        self, free: Tuple[int, int, int, int],
        px: int, py: int, pw: int, ph: int
    ) -> Optional[List[Tuple[int, int, int, int]]]:
        """如果放置的矩形与空闲矩形有交集，裁切空闲矩形"""
        fx, fy, fw, fh = free

        if px >= fx + fw or px + pw <= fx or py >= fy + fh or py + ph <= fy:
            return None

        splits = []

        if px > fx:
            splits.append((fx, fy, px - fx, fh))

        if px + pw < fx + fw:
            splits.append((px + pw, fy, (fx + fw) - (px + pw), fh))

        if py > fy:
            splits.append((fx, fy, fw, py - fy))

        if py + ph < fy + fh:
            splits.append((fx, py + ph, fw, (fy + fh) - (py + ph)))

        return splits

    def _prune_free_rects(self):
        """移除被其他空闲矩形完全包含的矩形"""
        i = 0
        while i < len(self._free_rects):
            j = i + 1
            while j < len(self._free_rects):
                if self._is_contained(self._free_rects[i], self._free_rects[j]):
                    self._free_rects.pop(i)
                    i -= 1
                    break
                if self._is_contained(self._free_rects[j], self._free_rects[i]):
                    self._free_rects.pop(j)
                else:
                    j += 1
            i += 1

    @staticmethod
    def _is_contained(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> bool:
        """检查 a 是否完全被 b 包含"""
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return ax >= bx and ay >= by and ax + aw <= bx + bw and ay + ah <= by + bh
