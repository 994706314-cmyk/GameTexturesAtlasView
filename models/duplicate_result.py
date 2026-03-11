"""检查模式 - 重复检测结果数据模型"""

from dataclasses import dataclass, field
from typing import List

from utils.constants import DUPLICATE_MARK_COLORS


@dataclass
class DuplicateGroup:
    """一组重复内容"""
    group_id: int = 0                    # 分组编号（从1开始）
    match_type: str = "exact"            # 匹配类型: "exact" 精确 | "fuzzy" 模糊
    color: str = "#E74C3C"              # 标记颜色 hex
    region_ids: List[str] = field(default_factory=list)  # 属于该组的子区域 region_id 列表
    atlas_ids: List[str] = field(default_factory=list)   # 涉及的图集 ID 列表（去重）
    hamming_distance: int = 0            # 汉明距离（仅模糊匹配时有意义）
    tier_size: int = 0                   # 检测时的网格尺寸（如 1024, 512, 64 等）
    
    @property
    def region_count(self) -> int:
        """该组包含的区域数量"""
        return len(self.region_ids)
    
    @property
    def atlas_count(self) -> int:
        """涉及的图集数量"""
        return len(set(self.atlas_ids))
    
    @property
    def match_type_label(self) -> str:
        """匹配类型中文标签"""
        return "精确匹配" if self.match_type == "exact" else "模糊匹配"
    
    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "group_id": self.group_id,
            "match_type": self.match_type,
            "color": self.color,
            "region_ids": self.region_ids.copy(),
            "atlas_ids": list(set(self.atlas_ids)),
            "hamming_distance": self.hamming_distance,
            "tier_size": self.tier_size,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "DuplicateGroup":
        """从字典反序列化"""
        return cls(
            group_id=data.get("group_id", 0),
            match_type=data.get("match_type", "exact"),
            color=data.get("color", "#E74C3C"),
            region_ids=data.get("region_ids", []),
            atlas_ids=data.get("atlas_ids", []),
            hamming_distance=data.get("hamming_distance", 0),
            tier_size=data.get("tier_size", 0),
        )


@dataclass
class DuplicateResult:
    """完整的重复检测结果"""
    groups: List[DuplicateGroup] = field(default_factory=list)
    total_regions_scanned: int = 0       # 扫描的总子区域数
    total_atlases: int = 0               # 参与分析的图集数
    analysis_mode: str = "exact"         # 分析模式
    
    @property
    def group_count(self) -> int:
        """重复组数量"""
        return len(self.groups)
    
    @property
    def duplicate_region_count(self) -> int:
        """涉及重复的区域总数"""
        return sum(g.region_count for g in self.groups)
    
    def add_group(self, region_ids: List[str], atlas_ids: List[str],
                  match_type: str = "exact", hamming_distance: int = 0,
                  tier_size: int = 0) -> DuplicateGroup:
        """添加一个重复分组"""
        group_id = len(self.groups) + 1
        color_idx = (group_id - 1) % len(DUPLICATE_MARK_COLORS)
        color = DUPLICATE_MARK_COLORS[color_idx]
        
        group = DuplicateGroup(
            group_id=group_id,
            match_type=match_type,
            color=color,
            region_ids=region_ids,
            atlas_ids=atlas_ids,
            hamming_distance=hamming_distance,
            tier_size=tier_size,
        )
        self.groups.append(group)
        return group
    
    def clear(self):
        """清空所有结果"""
        self.groups.clear()
        self.total_regions_scanned = 0
        self.total_atlases = 0
    
    def get_group_for_region(self, region_id: str) -> DuplicateGroup:
        """查找某个区域所属的重复组"""
        for group in self.groups:
            if region_id in group.region_ids:
                return group
        return None
    
    def get_groups_for_atlas(self, atlas_id: str) -> List[DuplicateGroup]:
        """获取某个图集涉及的所有重复组"""
        return [g for g in self.groups if atlas_id in g.atlas_ids]
    
    def to_dict(self) -> dict:
        """序列化"""
        return {
            "groups": [g.to_dict() for g in self.groups],
            "total_regions_scanned": self.total_regions_scanned,
            "total_atlases": self.total_atlases,
            "analysis_mode": self.analysis_mode,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "DuplicateResult":
        """反序列化"""
        result = cls(
            total_regions_scanned=data.get("total_regions_scanned", 0),
            total_atlases=data.get("total_atlases", 0),
            analysis_mode=data.get("analysis_mode", "exact"),
        )
        for g_data in data.get("groups", []):
            result.groups.append(DuplicateGroup.from_dict(g_data))
        return result
