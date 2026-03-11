"""全局常量定义"""

import sys
import os


def get_base_dir() -> str:
    """获取应用根目录（兼容 PyInstaller 打包和开发模式）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后，资源被解压到 sys._MEIPASS
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_runtime_dir() -> str:
    """获取运行时目录（exe 所在目录，用于存放用户生成文件如截图）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# 贴图尺寸约束
MIN_TEXTURE_SIZE = 16
GRID_UNIT = 16
SUPPORTED_ATLAS_SIZES = [1024, 2048, 4096]
DEFAULT_ATLAS_SIZE = 2048
VALID_TEXTURE_SIZES = [16, 32, 64, 128, 256, 512, 1024, 2048]

# 支持的图片格式
SUPPORTED_IMAGE_FORMATS = [".png", ".jpg", ".jpeg", ".tga", ".bmp", ".psd"]

# 动画时长 (ms)
ANIM_BOUNCE_IN = 300
ANIM_ELASTIC_SNAP = 250
ANIM_COLLISION = 350
ANIM_AUTO_LAYOUT = 500
ANIM_FADE_REMOVE = 250
ANIM_HOVER = 150
ANIM_BREATHING = 1500

# 项目文件
PROJECT_VERSION = "1.0"
PROJECT_FILE_EXTENSION = ".tatlas"
PROJECT_FILE_FILTER = "合图项目文件 (*.tatlas);;所有文件 (*.*)"
EXCEL_FILE_FILTER = "Excel 文件 (*.xlsx);;所有文件 (*.*)"

# UI 颜色
COLOR_PRIMARY = "#0078D4"
COLOR_PRIMARY_HOVER = "#106EBE"
COLOR_PRIMARY_PRESSED = "#005A9E"
COLOR_BG_DARKEST = "#1A1A1A"
COLOR_BG_DARK = "#1E1E1E"
COLOR_BG_PANEL = "#252526"
COLOR_BG_CARD = "#2D2D30"
COLOR_BG_INPUT = "#3C3C3C"
COLOR_BG_HOVER = "#383838"
COLOR_TEXT_PRIMARY = "#FFFFFF"
COLOR_TEXT_SECONDARY = "#CCCCCC"
COLOR_TEXT_DISABLED = "#888888"
COLOR_SUCCESS = "#4CAF50"
COLOR_ERROR = "#F44336"
COLOR_WARNING = "#FF9800"
COLOR_GRID_LINE = "#3C3C3C"
COLOR_GRID_MAJOR = "#555555"
COLOR_COLLISION = "#F44336"

# 缩略图
THUMBNAIL_SIZE = 80
THUMBNAIL_QUALITY_STANDARD = 80   # 标准清晰度缩略图尺寸
THUMBNAIL_QUALITY_HD = 200        # 高清缩略图尺寸
DEFAULT_THUMBNAIL_QUALITY = "standard"  # "standard" 或 "hd"

# 撤销/重做
DEFAULT_UNDO_STEPS = 100

# 默认快捷键
DEFAULT_SHORTCUTS = {
    "prev_atlas": "PgUp",
    "next_atlas": "PgDown",
    "auto_fill": "Ctrl+F",
    "save": "Ctrl+S",
    "undo": "Ctrl+Z",
    "redo": "Ctrl+Y",
    "new": "Ctrl+N",
    "open": "Ctrl+O",
    "save_as": "Ctrl+Shift+S",
    "screenshot": "Alt+D",
}

SHORTCUT_NAMES = {
    "prev_atlas": "上一张合图",
    "next_atlas": "下一张合图",
    "auto_fill": "自动整理",
    "save": "保存项目",
    "undo": "撤销",
    "redo": "重做",
    "new": "新建项目",
    "open": "打开项目",
    "save_as": "另存为",
    "screenshot": "截图添加贴图",
}

# 截图默认分辨率
SCREENSHOT_DEFAULT_WIDTH = 512
SCREENSHOT_DEFAULT_HEIGHT = 512
SCREENSHOT_RESOLUTIONS = [2048, 1024, 512, 256, 128, 64, 32, 16]
SCREENSHOT_DIR_NAME = "ScreenShot"

# 面板圆角
PANEL_BORDER_RADIUS = 10

# 自动映射压缩 - 宽度默认映射
DEFAULT_WIDTH_COMPRESS_MAP = {
    2048: 512,
    1024: 256,
    512: 128,
    256: 64,
    128: 32,
    64: 16,
    32: 16,
    16: 16,
}

# 高度默认映射（None 表示等比例）
DEFAULT_HEIGHT_COMPRESS_MAP = None  # None = 等比例跟随宽度

# 自动映射压缩开关默认开启
DEFAULT_AUTO_COMPRESS = True

# 导入时默认排除的后缀
DEFAULT_EXCLUDE_SUFFIXES = ["_NS", "_AM"]

# 宽度压缩配色映射（用于列表和缩略图底色区分）
DEFAULT_WIDTH_COLOR_MAP = {
    512: "#2E6B2E",   # 绿色
    256: "#2E5470",   # 青蓝色
    128: "#6B5A2E",   # 橙棕色
    64:  "#5A2E6B",   # 紫色
    32:  "#6B2E2E",   # 红色
    16:  "#2E2E6B",   # 蓝色
}

# ========== 检查模式常量 ==========

# 检查模式 - 浅色主题色
REVERSE_COLOR_PRIMARY = "#E8A820"          # 暖黄主色
REVERSE_COLOR_PRIMARY_HOVER = "#D49818"    # 暖黄悬停
REVERSE_COLOR_PRIMARY_PRESSED = "#C08810"  # 暖黄按下
REVERSE_COLOR_BG_BASE = "#F5F5F0"         # 米白底色
REVERSE_COLOR_BG_PANEL = "#EAEAE5"        # 面板灰
REVERSE_COLOR_BG_CARD = "#FFFFFF"         # 卡片白
REVERSE_COLOR_BG_INPUT = "#F0F0EB"        # 输入框底
REVERSE_COLOR_BG_HOVER = "#E5E5E0"        # 悬停底
REVERSE_COLOR_BORDER = "#D0D0CC"          # 边框线
REVERSE_COLOR_TEXT_PRIMARY = "#333333"     # 主文字
REVERSE_COLOR_TEXT_SECONDARY = "#666666"   # 辅文字
REVERSE_COLOR_TEXT_DISABLED = "#999999"    # 禁用文字

# 检查模式 - 图集后缀过滤
DEFAULT_ATLAS_SUFFIX = "_MainTex"

# 检查模式 - 重复检测参数
DEFAULT_FUZZY_THRESHOLD = 8         # 已废弃，保留兼容
DEFAULT_MIN_TIER_SIZE = 64          # 默认最低检测档位 64×64
DEFAULT_HASH_SIZE = 16              # 感知哈希尺寸
DEFAULT_NORMALIZE_SIZE = 64         # 统一缩放的对比尺寸（用于 SSIM 比较）
# 以下旧常量保留兼容但不再使用
MIN_REGION_SIDE = 16
MIN_REGION_AREA = MIN_REGION_SIDE * MIN_REGION_SIDE
REGION_MERGE_GAP = 2

# 相似度阈值（0.0 ~ 1.0）
EXACT_SIMILARITY_THRESHOLD = 0.99   # 精确判定：SSIM >= 99% 判为一致
FUZZY_SIMILARITY_THRESHOLD = 0.85   # 模糊判定：SSIM >= 85% 判为雷同
PHASH_PRE_FILTER_THRESHOLD = 24     # pHash 粗筛阈值：汉明距离 <= 此值才进入 SSIM 精确验证


# 检查模式 - 标记颜色调色板（20色循环）
DUPLICATE_MARK_COLORS = [
    "#E74C3C",  # 红
    "#3498DB",  # 蓝
    "#2ECC71",  # 绿
    "#F39C12",  # 橙
    "#9B59B6",  # 紫
    "#1ABC9C",  # 青
    "#E67E22",  # 深橙
    "#E84393",  # 粉
    "#00B894",  # 薄荷绿
    "#6C5CE7",  # 靛蓝
    "#FDCB6E",  # 浅黄
    "#74B9FF",  # 浅蓝
    "#A29BFE",  # 薰衣草
    "#FD79A8",  # 浅粉
    "#55E6C1",  # 青绿
    "#FF6348",  # 番茄红
    "#786FA6",  # 灰紫
    "#F8A5C2",  # 玫瑰粉
    "#63CDDA",  # 天蓝
    "#CF6A87",  # 暗粉
]

# 检查模式 - 项目版本
REVERSE_MODE_VERSION = "1.0"
REVERSE_FILE_EXTENSION = ".tcheck"
REVERSE_FILE_FILTER = "检查模式存档 (*.tcheck);;所有文件 (*.*)"
APP_VERSION = "1.5"  # 新增自动更新功能

# GitHub 仓库信息（用于检查更新）
GITHUB_OWNER = "994706314-cmyk"
GITHUB_REPO = "GameTexturesAtlasView"
