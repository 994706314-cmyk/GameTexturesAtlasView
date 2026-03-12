"""右侧素材库面板 - 支持拖拽导入、多选、双视图、排序、合图使用标记"""

import os
import json
import subprocess
import platform
from typing import Optional, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QFileDialog,
    QMessageBox, QAbstractItemView, QToolButton, QFrame,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QStackedWidget,
    QComboBox,
)
from PySide6.QtCore import (
    Qt, QSize, Signal, QMimeData, QPoint, QByteArray, QUrl,
)
from PySide6.QtGui import (
    QIcon, QPixmap, QDrag, QColor, QPainter, QImage, QFont,
    QDragEnterEvent, QDropEvent, QBrush, QPen,
)

from models.project_model import ProjectModel
from models.texture_item import TextureItem
from services.image_service import ImageService, ThumbnailWorker
from utils.constants import (
    SUPPORTED_IMAGE_FORMATS, VALID_TEXTURE_SIZES, COLOR_PRIMARY, THUMBNAIL_SIZE,
    PANEL_BORDER_RADIUS, DEFAULT_EXCLUDE_SUFFIXES, DEFAULT_WIDTH_COLOR_MAP,
    THUMBNAIL_QUALITY_HD, DEFAULT_THUMBNAIL_QUALITY,
    SCREENSHOT_DEFAULT_WIDTH, SCREENSHOT_DEFAULT_HEIGHT, SCREENSHOT_RESOLUTIONS,
)
from .size_edit_dialog import SizeEditDialog


# 圆圈数字字符映射
_CIRCLED_NUMBERS = {
    1: "\u2460", 2: "\u2461", 3: "\u2462", 4: "\u2463",
    5: "\u2464", 6: "\u2465", 7: "\u2466", 8: "\u2467",
    9: "\u2468", 10: "\u2469", 11: "\u246A", 12: "\u246B",
    13: "\u246C", 14: "\u246D", 15: "\u246E", 16: "\u246F",
    17: "\u2470", 18: "\u2471", 19: "\u2472", 20: "\u2473",
}


def _get_width_color(display_w: int) -> Optional[QColor]:
    """根据压缩宽度返回底色"""
    color_map = DEFAULT_WIDTH_COLOR_MAP
    hex_color = color_map.get(display_w)
    if hex_color:
        return QColor(hex_color)
    return None


class LibraryPanel(QWidget):
    """右侧素材库面板"""

    project_changed = Signal()
    jump_to_atlas = Signal(str)  # atlas_id - 跳转到对应合图

    def __init__(self, project: ProjectModel, parent=None):
        super().__init__(parent)
        self._project = project
        self._thumb_worker: Optional[ThumbnailWorker] = None
        self._drag_start_pos: Optional[QPoint] = None
        self._view_mode = "grid"  # "grid" or "list"
        self._sort_mode = "name"  # "name", "planned_size", "original_size"
        self._sort_ascending = True
        self._skip_external_refresh = False  # 防止内部操作触发二次刷新
        self.setMinimumWidth(200)
        self.setAcceptDrops(True)
        self._init_ui()

    def _get_width_color_for_tex(self, display_w: int) -> Optional[QColor]:
        """从设置中获取宽度配色"""
        main_win = self.window()
        color_map = DEFAULT_WIDTH_COLOR_MAP
        if hasattr(main_win, '_settings'):
            color_map = main_win._settings.get("width_color_map", DEFAULT_WIDTH_COLOR_MAP)
        # JSON 反序列化后 key 可能变成字符串，兼容 int 和 str
        hex_color = color_map.get(display_w) or color_map.get(str(display_w))
        if hex_color:
            return QColor(hex_color)
        return None

    def _get_thumbnail_quality(self) -> str:
        """获取缩略图清晰度设置"""
        main_win = self.window()
        if hasattr(main_win, '_settings'):
            return main_win._settings.get("thumbnail_quality", DEFAULT_THUMBNAIL_QUALITY)
        return DEFAULT_THUMBNAIL_QUALITY

    def _get_thumbnail_size(self) -> int:
        """根据清晰度设置返回缩略图尺寸"""
        quality = self._get_thumbnail_quality()
        if quality == "hd":
            return THUMBNAIL_QUALITY_HD
        return THUMBNAIL_SIZE

    def _generate_thumbnail(self, image_path: str) -> Optional[str]:
        """根据当前清晰度设置生成缩略图"""
        thumb_size = self._get_thumbnail_size()
        return ImageService.generate_thumbnail(image_path, size=thumb_size)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 内容容器 - 圆角气泡
        container = QFrame()
        container.setObjectName("libraryContainer")
        container.setStyleSheet(f"""
            QFrame#libraryContainer {{
                background-color: #252526;
                border-radius: {PANEL_BORDER_RADIUS}px;
                border: 1px solid #3C3C3C;
            }}
        """)
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(12, 12, 12, 12)
        c_layout.setSpacing(8)

        # 头部
        header = QHBoxLayout()
        title = QLabel("素材库")
        title.setStyleSheet("font-size: 14px; font-weight: 600; color: #FFFFFF; background: transparent;")
        header.addWidget(title)
        header.addStretch()

        self._count_label = QLabel("0 项")
        self._count_label.setStyleSheet("font-size: 11px; color: #888888; background: transparent;")
        header.addWidget(self._count_label)

        # 刷新按钮
        self._refresh_btn = QToolButton()
        self._refresh_btn.setText("⟳")
        self._refresh_btn.setToolTip("刷新素材库（重新检测图片变更）")
        self._refresh_btn.setFixedSize(24, 24)
        self._refresh_btn.setStyleSheet("""
            QToolButton {
                background-color: transparent; color: #888888;
                border: 1px solid #555555; border-radius: 4px;
                font-size: 14px; font-weight: bold;
            }
            QToolButton:hover {
                background-color: #3C3C3C; color: #FFFFFF; border-color: #888888;
            }
            QToolButton:pressed { background-color: #333333; }
        """)
        self._refresh_btn.clicked.connect(self._on_refresh_library)
        header.addWidget(self._refresh_btn)

        c_layout.addLayout(header)

        # 按钮行
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self._import_file_btn = QPushButton("导入文件")
        self._import_file_btn.setStyleSheet(self._btn_style())
        self._import_file_btn.clicked.connect(self._on_import_files)
        btn_layout.addWidget(self._import_file_btn)

        self._import_folder_btn = QPushButton("导入文件夹")
        self._import_folder_btn.setStyleSheet(self._btn_style())
        self._import_folder_btn.clicked.connect(self._on_import_folder)
        btn_layout.addWidget(self._import_folder_btn)

        c_layout.addLayout(btn_layout)

        # 截图按钮行
        screenshot_layout = QHBoxLayout()
        screenshot_layout.setSpacing(4)

        self._screenshot_btn = QPushButton("📷 添加截图贴图 (Alt+D)")
        self._screenshot_btn.setToolTip("截取屏幕区域作为贴图添加到素材库 (Alt+D)")
        self._screenshot_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent; color: #CCCCCC;
                border: 1px solid #555555; border-radius: 6px;
                padding: 5px 8px; font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #3C3C3C; color: #FFFFFF; border-color: #666666;
            }}
            QPushButton:pressed {{ background-color: #333333; }}
        """)
        self._screenshot_btn.clicked.connect(self._on_screenshot)
        screenshot_layout.addWidget(self._screenshot_btn, 1)

        # 宽度分辨率选择
        self._ss_width_combo = QComboBox()
        self._ss_width_combo.setToolTip("截图贴图的规划宽度")
        self._ss_width_combo.setFixedWidth(78)
        self._ss_width_combo.setStyleSheet("QComboBox { font-size: 10px; padding-right: 14px; }")
        for s in SCREENSHOT_RESOLUTIONS:
            self._ss_width_combo.addItem(str(s), s)
        idx = self._ss_width_combo.findData(SCREENSHOT_DEFAULT_WIDTH)
        if idx >= 0:
            self._ss_width_combo.setCurrentIndex(idx)
        screenshot_layout.addWidget(self._ss_width_combo)

        x_label = QLabel("×")
        x_label.setStyleSheet("color: #888; font-size: 10px; background: transparent;")
        x_label.setFixedWidth(12)
        x_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        screenshot_layout.addWidget(x_label)

        # 高度分辨率选择（含"等比"选项）
        self._ss_height_combo = QComboBox()
        self._ss_height_combo.setToolTip("截图贴图的规划高度（等比=根据宽度和截图比例自动计算）")
        self._ss_height_combo.setFixedWidth(78)
        self._ss_height_combo.setStyleSheet("QComboBox { font-size: 10px; padding-right: 14px; }")
        self._ss_height_combo.addItem("等比", -1)  # -1 表示等比
        for s in SCREENSHOT_RESOLUTIONS:
            self._ss_height_combo.addItem(str(s), s)
        # 默认选中"等比"
        self._ss_height_combo.setCurrentIndex(0)
        screenshot_layout.addWidget(self._ss_height_combo)

        c_layout.addLayout(screenshot_layout)

        # 搜索 + 排序 + 视图切换
        search_row = QHBoxLayout()
        search_row.setSpacing(4)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索素材...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setMaximumWidth(160)
        self._search_input.textChanged.connect(self._on_search)
        search_row.addWidget(self._search_input)

        # 排序按钮 - 使用文字而非图标
        self._sort_name_btn = QToolButton()
        self._sort_name_btn.setText("名称↓")
        self._sort_name_btn.setToolTip("按名称排序")
        self._sort_name_btn.setFixedSize(48, 24)
        self._sort_name_btn.setStyleSheet(self._sort_btn_style(True))
        self._sort_name_btn.clicked.connect(lambda: self._set_sort_mode("name"))
        search_row.addWidget(self._sort_name_btn)

        self._sort_planned_btn = QToolButton()
        self._sort_planned_btn.setText("规划")
        self._sort_planned_btn.setToolTip("按规划尺寸排序")
        self._sort_planned_btn.setFixedSize(42, 24)
        self._sort_planned_btn.setStyleSheet(self._sort_btn_style(False))
        self._sort_planned_btn.clicked.connect(lambda: self._set_sort_mode("planned_size"))
        search_row.addWidget(self._sort_planned_btn)

        self._sort_orig_btn = QToolButton()
        self._sort_orig_btn.setText("原始")
        self._sort_orig_btn.setToolTip("按原始尺寸排序")
        self._sort_orig_btn.setFixedSize(42, 24)
        self._sort_orig_btn.setStyleSheet(self._sort_btn_style(False))
        self._sort_orig_btn.clicked.connect(lambda: self._set_sort_mode("original_size"))
        search_row.addWidget(self._sort_orig_btn)

        self._sort_tag_btn = QToolButton()
        self._sort_tag_btn.setText("标记")
        self._sort_tag_btn.setToolTip("按标记种类排序（E/A/M/C1/C2/C3）")
        self._sort_tag_btn.setFixedSize(42, 24)
        self._sort_tag_btn.setStyleSheet(self._sort_btn_style(False))
        self._sort_tag_btn.clicked.connect(lambda: self._set_sort_mode("tag"))
        search_row.addWidget(self._sort_tag_btn)

        self._sort_atlas_btn = QToolButton()
        self._sort_atlas_btn.setText("图集")
        self._sort_atlas_btn.setToolTip("按所在图集排序")
        self._sort_atlas_btn.setFixedSize(42, 24)
        self._sort_atlas_btn.setStyleSheet(self._sort_btn_style(False))
        self._sort_atlas_btn.clicked.connect(lambda: self._set_sort_mode("atlas"))
        search_row.addWidget(self._sort_atlas_btn)

        # 分隔
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(20)
        sep.setStyleSheet("color: #3C3C3C; background: transparent;")
        search_row.addWidget(sep)

        self._grid_view_btn = QToolButton()
        self._grid_view_btn.setText("▦")
        self._grid_view_btn.setToolTip("缩略图视图")
        self._grid_view_btn.setFixedSize(24, 24)
        self._grid_view_btn.setCheckable(True)
        self._grid_view_btn.setChecked(True)
        self._grid_view_btn.setStyleSheet(self._view_toggle_style(True))
        self._grid_view_btn.clicked.connect(lambda: self._set_view_mode("grid"))
        search_row.addWidget(self._grid_view_btn)

        self._list_view_btn = QToolButton()
        self._list_view_btn.setText("≡")
        self._list_view_btn.setToolTip("列表视图")
        self._list_view_btn.setFixedSize(24, 24)
        self._list_view_btn.setCheckable(True)
        self._list_view_btn.setStyleSheet(self._view_toggle_style(False))
        self._list_view_btn.clicked.connect(lambda: self._set_view_mode("list"))
        search_row.addWidget(self._list_view_btn)

        c_layout.addLayout(search_row)

        # 视图栈
        self._view_stack = QStackedWidget()

        # 缩略图视图
        self._grid_list = QListWidget()
        self._grid_list.setViewMode(QListWidget.ViewMode.IconMode)
        self._grid_list.setIconSize(QSize(THUMBNAIL_SIZE + 16, THUMBNAIL_SIZE + 16))
        self._grid_list.setGridSize(QSize(THUMBNAIL_SIZE + 28, THUMBNAIL_SIZE + 44))
        self._grid_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._grid_list.setWrapping(True)
        self._grid_list.setSpacing(2)
        self._grid_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._grid_list.setDragEnabled(True)
        self._grid_list.setStyleSheet(self._list_style())
        self._grid_list.doubleClicked.connect(self._on_double_click_grid)
        self._grid_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._grid_list.customContextMenuRequested.connect(self._on_context_menu_grid)
        self._grid_list.mousePressEvent = self._grid_mouse_press
        self._grid_list.mouseMoveEvent = self._grid_mouse_move
        self._view_stack.addWidget(self._grid_list)

        # 列表视图
        self._tree_list = QTreeWidget()
        self._tree_list.setHeaderLabels(["名称", "规划尺寸", "原始尺寸", "合图"])
        self._tree_list.setColumnCount(4)
        self._tree_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree_list.setRootIsDecorated(False)
        self._tree_list.setAlternatingRowColors(False)  # 用自定义底色
        self._tree_list.setStyleSheet("""
            QTreeWidget {
                background: transparent; border: none;
            }
            QTreeWidget::item {
                padding: 4px; color: #CCCCCC; border-radius: 3px;
            }
            QTreeWidget::item:hover { background-color: rgba(56, 56, 56, 180); }
            QTreeWidget::item:selected {
                background-color: transparent;
                border: 2px solid #0078D4;
            }
            QHeaderView::section {
                background-color: #2D2D30; color: #888888;
                border: none; padding: 4px 8px; font-size: 11px;
                border-bottom: 1px solid #3C3C3C;
            }
        """)
        self._tree_list.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self._tree_list.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tree_list.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._tree_list.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._tree_list.header().setDefaultSectionSize(300)
        self._tree_list.setColumnWidth(0, 300)
        self._tree_list.setIconSize(QSize(50, 32))
        self._tree_list.doubleClicked.connect(self._on_double_click_tree)
        self._tree_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree_list.customContextMenuRequested.connect(self._on_context_menu_tree)
        self._tree_list.setDragEnabled(True)
        self._tree_list.mousePressEvent = self._tree_mouse_press
        self._tree_list.mouseMoveEvent = self._tree_mouse_move
        self._tree_list.header().sectionClicked.connect(self._on_header_clicked)
        self._tree_list.itemClicked.connect(self._on_tree_item_clicked)
        self._view_stack.addWidget(self._tree_list)

        c_layout.addWidget(self._view_stack, 1)

        # 提示
        hint = QLabel("拖拽文件/文件夹到此处可导入")
        hint.setStyleSheet("font-size: 10px; color: #555555; background: transparent;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_layout.addWidget(hint)

        layout.addWidget(container)

    def set_project(self, project: ProjectModel):
        self._project = project
        self.refresh()

    def refresh(self):
        self._populate_views()
        self._update_count()

    def select_texture_by_id(self, texture_id: str):
        """根据 texture_id 在当前视图中选中并滚动到对应项"""
        if self._view_mode == "grid":
            for i in range(self._grid_list.count()):
                item = self._grid_list.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == texture_id:
                    self._grid_list.clearSelection()
                    item.setSelected(True)
                    self._grid_list.scrollToItem(
                        item, QAbstractItemView.ScrollHint.PositionAtCenter
                    )
                    return
        else:
            for i in range(self._tree_list.topLevelItemCount()):
                item = self._tree_list.topLevelItem(i)
                if item and item.data(0, Qt.ItemDataRole.UserRole) == texture_id:
                    self._tree_list.clearSelection()
                    item.setSelected(True)
                    self._tree_list.scrollToItem(
                        item, QAbstractItemView.ScrollHint.PositionAtCenter
                    )
                    return

    def _populate_views(self):
        """根据当前排序重新填充双视图，保持滚动位置（批量刷新优化）"""
        # 保存滚动位置
        grid_scroll_val = self._grid_list.verticalScrollBar().value() if self._grid_list.verticalScrollBar() else 0
        tree_scroll_val = self._tree_list.verticalScrollBar().value() if self._tree_list.verticalScrollBar() else 0

        sorted_lib = self._get_sorted_library()

        # 暂停更新以提升批量添加性能
        self._grid_list.setUpdatesEnabled(False)
        self._tree_list.setUpdatesEnabled(False)

        self._grid_list.clear()
        self._tree_list.clear()

        # 构建合图使用映射
        usage_map = self._build_usage_map()

        for tex in sorted_lib:
            atlas_indices = usage_map.get(tex.id, [])
            self._add_to_grid(tex, atlas_indices)
            self._add_to_tree(tex, atlas_indices)

        # 恢复更新
        self._grid_list.setUpdatesEnabled(True)
        self._tree_list.setUpdatesEnabled(True)

        # 恢复滚动位置
        from PySide6.QtCore import QTimer
        def _restore_scroll():
            if self._grid_list.verticalScrollBar():
                self._grid_list.verticalScrollBar().setValue(grid_scroll_val)
            if self._tree_list.verticalScrollBar():
                self._tree_list.verticalScrollBar().setValue(tree_scroll_val)
        QTimer.singleShot(0, _restore_scroll)

    def _build_usage_map(self) -> dict:
        """返回 {texture_id: [atlas_index_1based, ...]}"""
        usage = {}
        for i, atlas in enumerate(self._project.atlas_list):
            for pt in atlas.placed_textures:
                tid = pt.texture.id
                if tid not in usage:
                    usage[tid] = []
                idx = i + 1
                if idx not in usage[tid]:
                    usage[tid].append(idx)
        return usage

    def _build_usage_id_map(self) -> dict:
        """返回 {texture_id: [(atlas_index_1based, atlas_id), ...]}"""
        usage = {}
        for i, atlas in enumerate(self._project.atlas_list):
            for pt in atlas.placed_textures:
                tid = pt.texture.id
                if tid not in usage:
                    usage[tid] = []
                idx = i + 1
                entry = (idx, atlas.id)
                if entry not in usage[tid]:
                    usage[tid].append(entry)
        return usage

    def _get_sorted_library(self) -> List[TextureItem]:
        lib = list(self._project.library)
        rev = not self._sort_ascending
        if self._sort_mode == "name":
            lib.sort(key=lambda t: t.name.lower(), reverse=rev)
        elif self._sort_mode == "planned_size":
            lib.sort(key=lambda t: t.display_width * t.display_height, reverse=rev)
        elif self._sort_mode == "original_size":
            lib.sort(key=lambda t: t.original_size[0] * t.original_size[1], reverse=rev)
        elif self._sort_mode == "tag":
            # 按标记种类排序：无标记→E→A→M→C1→C2→C3
            tag_order = {"": 0, "E": 1, "A": 2, "M": 3, "C1": 4, "C2": 5, "C3": 6}
            lib.sort(key=lambda t: (tag_order.get(t.tag, 99), t.name.lower()), reverse=rev)
        elif self._sort_mode == "atlas":
            # 按所在图集排序：按第一个图集的序号排，未在图集中的排最后
            atlas_order = {}
            for i, atlas in enumerate(self._project.atlas_list):
                for pt in atlas.placed_textures:
                    if pt.texture.id not in atlas_order:
                        atlas_order[pt.texture.id] = i
            max_idx = len(self._project.atlas_list)
            lib.sort(key=lambda t: (atlas_order.get(t.id, max_idx), t.name.lower()), reverse=rev)
        return lib

    def _add_to_grid(self, tex: TextureItem, atlas_indices: List[int]):
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, tex.id)

        # 标签：名称 + 规划尺寸
        label = f"{tex.name}\n{tex.display_width}x{tex.display_height}"
        item.setText(label)
        source_info = "截图贴图（无源文件）" if tex.is_screenshot else tex.original_path
        item.setToolTip(
            f"名称: {tex.name}\n"
            f"原始尺寸: {tex.original_size[0]}x{tex.original_size[1]}\n"
            f"规划尺寸: {tex.display_width}x{tex.display_height}\n"
            f"来源: {source_info}"
        )
        icon = self._make_icon_with_badge(tex, atlas_indices)
        item.setIcon(icon)
        item.setSizeHint(QSize(THUMBNAIL_SIZE + 24, THUMBNAIL_SIZE + 40))

        # 不再设置背景色，颜色边框已在 icon 中绘制

        self._grid_list.addItem(item)

    def _add_to_tree(self, tex: TextureItem, atlas_indices: List[int]):
        item = QTreeWidgetItem()
        item.setText(0, tex.name)
        item.setText(1, f"{tex.display_width}x{tex.display_height}")
        item.setText(2, f"{tex.original_size[0]}x{tex.original_size[1]}")
        # 合图使用列 - 用圆圈数字
        if atlas_indices:
            badge_text = " ".join(
                _CIRCLED_NUMBERS.get(i, str(i)) for i in sorted(atlas_indices)
            )
            item.setText(3, badge_text)
        else:
            item.setText(3, "-")
        item.setData(0, Qt.ItemDataRole.UserRole, tex.id)
        item.setToolTip(0, tex.original_path)

        # 生成带色彩小圆点的图标
        bg_color = self._get_width_color_for_tex(tex.display_width)
        icon = self._make_tree_icon_with_dot(tex, bg_color)
        item.setIcon(0, icon)

        self._tree_list.addTopLevelItem(item)

    def _make_icon(self, tex: TextureItem) -> QIcon:
        if tex.thumbnail_path and os.path.exists(tex.thumbnail_path):
            return QIcon(QPixmap(tex.thumbnail_path))

        if os.path.exists(tex.original_path):
            thumb = self._generate_thumbnail(tex.original_path)
            if thumb:
                tex.thumbnail_path = thumb
                return QIcon(QPixmap(thumb))

        img = QImage(THUMBNAIL_SIZE, THUMBNAIL_SIZE, QImage.Format.Format_ARGB32)
        img.fill(QColor(60, 60, 60))
        painter = QPainter(img)
        painter.setPen(QColor(200, 80, 80))
        painter.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, "缺失")
        painter.end()
        return QIcon(QPixmap.fromImage(img))

    def _make_tree_icon_with_dot(self, tex: TextureItem, color: Optional[QColor]) -> QIcon:
        """生成列表视图图标：缩略图左侧带色彩倒角矩形"""
        icon_size = 32
        dot_w = 14
        dot_h = 14
        dot_radius = 3
        dot_margin = 4
        # 总宽度 = 矩形 + 间距 + 图标
        total_w = dot_w + dot_margin + icon_size
        total_h = icon_size

        img = QImage(total_w, total_h, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))

        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制色彩倒角矩形
        if color:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            dot_y = (total_h - dot_h) // 2
            painter.drawRoundedRect(0, dot_y, dot_w, dot_h, dot_radius, dot_radius)

        # 绘制缩略图
        thumb_x = dot_w + dot_margin
        thumb_pixmap = None
        if tex.thumbnail_path and os.path.exists(tex.thumbnail_path):
            thumb_pixmap = QPixmap(tex.thumbnail_path)
        elif os.path.exists(tex.original_path):
            thumb = self._generate_thumbnail(tex.original_path)
            if thumb:
                tex.thumbnail_path = thumb
                thumb_pixmap = QPixmap(thumb)

        if thumb_pixmap:
            scaled = thumb_pixmap.scaled(
                icon_size, icon_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            px = thumb_x + (icon_size - scaled.width()) // 2
            py = (icon_size - scaled.height()) // 2
            painter.drawPixmap(px, py, scaled)
        else:
            painter.fillRect(thumb_x, 0, icon_size, icon_size, QColor(60, 60, 60))
            painter.setPen(QColor(200, 80, 80))
            font = QFont("Microsoft YaHei UI", 7)
            painter.setFont(font)
            painter.drawText(thumb_x, 0, icon_size, icon_size,
                             Qt.AlignmentFlag.AlignCenter, "缺失")

        painter.end()
        return QIcon(QPixmap.fromImage(img))

    def _make_icon_with_badge(self, tex: TextureItem, atlas_indices: List[int]) -> QIcon:
        """生成带合图使用圆圈标记和规划尺寸的缩略图图标"""
        size = THUMBNAIL_SIZE + 16
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))

        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 宽度配色底色
        bg_color = self._get_width_color_for_tex(tex.display_width)

        # 绘制缩略图
        thumb_pixmap = None
        if tex.thumbnail_path and os.path.exists(tex.thumbnail_path):
            thumb_pixmap = QPixmap(tex.thumbnail_path)
        elif os.path.exists(tex.original_path):
            thumb = self._generate_thumbnail(tex.original_path)
            if thumb:
                tex.thumbnail_path = thumb
                thumb_pixmap = QPixmap(thumb)

        thumb_rect_size = THUMBNAIL_SIZE + 8
        tx = (size - thumb_rect_size) // 2
        ty = 0

        if thumb_pixmap:
            scaled = thumb_pixmap.scaled(
                thumb_rect_size, thumb_rect_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            px = tx + (thumb_rect_size - scaled.width()) // 2
            py = ty + (thumb_rect_size - scaled.height()) // 2
            painter.drawPixmap(px, py, scaled)
        else:
            painter.fillRect(tx, ty, thumb_rect_size, thumb_rect_size, QColor(60, 60, 60))
            painter.setPen(QColor(200, 80, 80))
            font = QFont("Microsoft YaHei UI", 8)
            painter.setFont(font)
            painter.drawText(tx, ty, thumb_rect_size, thumb_rect_size,
                             Qt.AlignmentFlag.AlignCenter, "缺失")

        # 根据宽度配色绘制边框（不覆盖图片内容）
        if bg_color:
            border_pen = QPen(bg_color, 3)
            painter.setPen(border_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(tx + 1, ty + 1, thumb_rect_size - 2, thumb_rect_size - 2)

        # 在右上角绘制独立的合图使用圆圈标记（每个数字一个圆圈）
        if atlas_indices:
            circle_size = 16
            badge_font = QFont("Microsoft YaHei UI", 8, QFont.Weight.Bold)
            painter.setFont(badge_font)
            sorted_indices = sorted(atlas_indices)
            # 从右上角开始，每个圆圈独立排列
            start_x = size - circle_size - 1
            for k, idx in enumerate(sorted_indices):
                bx = start_x - k * (circle_size + 2)
                by = 1
                if bx < 0:
                    break
                # 圆圈背景
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(COLOR_PRIMARY))
                painter.drawEllipse(bx, by, circle_size, circle_size)
                # 数字
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(bx, by, circle_size, circle_size,
                                 Qt.AlignmentFlag.AlignCenter, str(idx))

        # 底部显示规划尺寸
        size_text = f"{tex.display_width}x{tex.display_height}"
        size_font = QFont("Microsoft YaHei UI", 7)
        painter.setFont(size_font)
        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(size_text) + 6
        text_h = fm.height() + 2
        sx = tx + (thumb_rect_size - text_w) // 2
        sy = ty + thumb_rect_size - text_h - 1
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 180))
        painter.drawRoundedRect(sx, sy, text_w, text_h, 3, 3)
        painter.setPen(QColor(200, 220, 255))
        painter.drawText(sx, sy, text_w, text_h, Qt.AlignmentFlag.AlignCenter, size_text)

        # 截图贴图角标（左上角紫色标记）
        if tex.is_screenshot:
            badge_size = 18
            bx_sc = tx + 1
            by_sc = ty + 1
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(156, 39, 176, 220))  # 紫色
            painter.drawRoundedRect(bx_sc, by_sc, badge_size, badge_size, 3, 3)
            painter.setPen(QColor(255, 255, 255))
            sc_font = QFont("Microsoft YaHei UI", 9)
            painter.setFont(sc_font)
            painter.drawText(bx_sc, by_sc, badge_size, badge_size,
                             Qt.AlignmentFlag.AlignCenter, "✂")

        # 贴图标记角标（E/A/C1/C2/C3 — 左上角，截图角标下方）
        if tex.tag:
            tag_colors = {
                "E": ("#FF6B00", "#FFFFFF"),   # 橙色底 - 自发光 Emissive
                "A": ("#00AAFF", "#FFFFFF"),   # 蓝色底 - 半透明 Alpha
                "M": ("#8BC34A", "#FFFFFF"),   # 黄绿底 - Mask
                "C1": ("#9C27B0", "#FFFFFF"),  # 紫色底 - Custom1
                "C2": ("#00897B", "#FFFFFF"),  # 青色底 - Custom2
                "C3": ("#E91E63", "#FFFFFF"),  # 粉色底 - Custom3
            }
            tag_bg, tag_fg = tag_colors.get(tex.tag, ("#666666", "#FFFFFF"))
            tag_text = tex.tag if len(tex.tag) <= 2 else tex.tag
            tag_font = QFont("Microsoft YaHei UI", 7, QFont.Weight.Bold)
            painter.setFont(tag_font)
            fm_tag = painter.fontMetrics()
            tag_w = max(18, fm_tag.horizontalAdvance(tag_text) + 6)
            tag_h = 14
            tag_x = tx + 1
            tag_y = ty + 1 + (20 if tex.is_screenshot else 0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tag_bg))
            painter.drawRoundedRect(tag_x, tag_y, tag_w, tag_h, 3, 3)
            painter.setPen(QColor(tag_fg))
            painter.drawText(tag_x, tag_y, tag_w, tag_h,
                             Qt.AlignmentFlag.AlignCenter, tag_text)

        painter.end()
        return QIcon(QPixmap.fromImage(img))

    def _update_count(self):
        self._count_label.setText(f"{len(self._project.library)} 项")

    # ---- Sort ----
    def _set_sort_mode(self, mode: str):
        if self._sort_mode == mode:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_mode = mode
            self._sort_ascending = True

        arrow = "↓" if self._sort_ascending else "↑"
        self._sort_name_btn.setText(f"名称{arrow}" if mode == "name" else "名称")
        self._sort_planned_btn.setText(f"规划{arrow}" if mode == "planned_size" else "规划")
        self._sort_orig_btn.setText(f"原始{arrow}" if mode == "original_size" else "原始")
        self._sort_tag_btn.setText(f"标记{arrow}" if mode == "tag" else "标记")
        self._sort_atlas_btn.setText(f"图集{arrow}" if mode == "atlas" else "图集")

        self._sort_name_btn.setStyleSheet(self._sort_btn_style(mode == "name"))
        self._sort_planned_btn.setStyleSheet(self._sort_btn_style(mode == "planned_size"))
        self._sort_orig_btn.setStyleSheet(self._sort_btn_style(mode == "original_size"))
        self._sort_tag_btn.setStyleSheet(self._sort_btn_style(mode == "tag"))
        self._sort_atlas_btn.setStyleSheet(self._sort_btn_style(mode == "atlas"))

        self._populate_views()

    def _on_header_clicked(self, section: int):
        if section == 0:
            self._set_sort_mode("name")
        elif section == 1:
            self._set_sort_mode("planned_size")
        elif section == 2:
            self._set_sort_mode("original_size")

    # ---- Tree item click - check if clicking atlas column to jump ----
    def _on_tree_item_clicked(self, item: QTreeWidgetItem, column: int):
        """点击合图列中的圆圈数字可以跳转到对应合图"""
        if column != 3:
            return
        text = item.text(3).strip()
        if text == "-":
            return
        tid = item.data(0, Qt.ItemDataRole.UserRole)
        usage_id_map = self._build_usage_id_map()
        entries = usage_id_map.get(tid, [])
        if not entries:
            return
        # 如果只有一个合图使用，直接跳转
        if len(entries) == 1:
            self.jump_to_atlas.emit(entries[0][1])
        else:
            # 多个合图，弹出简单选择菜单
            from PySide6.QtWidgets import QMenu
            menu = QMenu(self)
            menu.setStyleSheet("""
                QMenu {
                    background-color: #2D2D30; border: 1px solid #3C3C3C;
                    border-radius: 6px; padding: 4px;
                }
                QMenu::item {
                    padding: 6px 24px; color: #CCCCCC; border-radius: 4px; margin: 2px;
                }
                QMenu::item:selected { background-color: #3C3C3C; color: #FFFFFF; }
            """)
            for idx, atlas_id in entries:
                atlas = self._project.find_atlas(atlas_id)
                name = atlas.name if atlas else f"合图 {idx}"
                action = menu.addAction(f"{_CIRCLED_NUMBERS.get(idx, str(idx))} {name}")
                action.setData(atlas_id)
            chosen = menu.exec(self._tree_list.mapToGlobal(
                self._tree_list.visualItemRect(item).center()
            ))
            if chosen:
                self.jump_to_atlas.emit(chosen.data())

    # ---- View mode ----
    def _set_view_mode(self, mode: str):
        self._view_mode = mode
        if mode == "grid":
            self._view_stack.setCurrentIndex(0)
            self._grid_view_btn.setChecked(True)
            self._list_view_btn.setChecked(False)
            self._grid_view_btn.setStyleSheet(self._view_toggle_style(True))
            self._list_view_btn.setStyleSheet(self._view_toggle_style(False))
        else:
            self._view_stack.setCurrentIndex(1)
            self._grid_view_btn.setChecked(False)
            self._list_view_btn.setChecked(True)
            self._grid_view_btn.setStyleSheet(self._view_toggle_style(False))
            self._list_view_btn.setStyleSheet(self._view_toggle_style(True))

    # ---- Drag & Drop import (external files) ----
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        if not event.mimeData().hasUrls():
            event.ignore()
            return

        paths = []
        for url in event.mimeData().urls():
            local_path = url.toLocalFile()
            if not local_path:
                continue
            if os.path.isdir(local_path):
                paths.extend(ImageService.scan_directory(local_path))
            elif os.path.isfile(local_path):
                if ImageService.is_supported_format(local_path):
                    paths.append(local_path)

        if paths:
            self._import_images(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    # ---- Import ----
    def _on_import_files(self):
        fmt_str = " ".join(f"*{ext}" for ext in SUPPORTED_IMAGE_FORMATS)
        paths, _ = QFileDialog.getOpenFileNames(
            self, "导入图片", "", f"图片文件 ({fmt_str});;所有文件 (*.*)"
        )
        if paths:
            self._import_images(paths)

    def _on_import_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择图片文件夹")
        if dir_path:
            paths = ImageService.scan_directory(dir_path)
            if paths:
                self._import_images(paths)
            else:
                QMessageBox.information(self, "导入", "该文件夹中没有找到支持的图片文件")

    # ---- Screenshot capture ----
    def update_screenshot_shortcut_label(self, shortcut_str: str):
        """更新截图按钮上显示的快捷键文字"""
        self._screenshot_btn.setText(f"📷 添加截图贴图 ({shortcut_str})")
        self._screenshot_btn.setToolTip(f"截取屏幕区域作为贴图添加到素材库 ({shortcut_str})")

    def _on_screenshot(self):
        """启动截图添加贴图流程"""
        from .screenshot_overlay import ScreenshotOverlay
        self._screenshot_overlay = ScreenshotOverlay()
        self._screenshot_overlay.screenshot_taken.connect(self._on_screenshot_captured)
        self._screenshot_overlay.cancelled.connect(self._on_screenshot_cancelled)
        # 先最小化主窗口，再进入截图
        main_win = self.window()
        if main_win:
            self._main_was_maximized = main_win.isMaximized()
            main_win.showMinimized()
        # 延迟启动让窗口最小化完成
        from PySide6.QtCore import QTimer
        QTimer.singleShot(300, self._screenshot_overlay.start)

    def _on_screenshot_captured(self, pixmap):
        """截图完成回调"""
        from services.screenshot_service import ScreenshotService

        # 恢复主窗口
        main_win = self.window()
        if main_win:
            if getattr(self, '_main_was_maximized', False):
                main_win.showMaximized()
            else:
                main_win.showNormal()
            main_win.activateWindow()

        # 保存截图到 ScreenShot 文件夹
        saved_path = ScreenshotService.save_screenshot(pixmap)
        if not saved_path:
            QMessageBox.warning(self, "截图", "截图保存失败。")
            return

        # 获取用户设定的规划分辨率
        plan_w = self._ss_width_combo.currentData()
        plan_h = self._ss_height_combo.currentData()

        # 获取截图实际尺寸
        actual_w = pixmap.width()
        actual_h = pixmap.height()

        # 等比模式：根据截图宽高比和规划宽度计算高度，对齐到最近的合法贴图尺寸
        if plan_h == -1:
            if actual_w > 0 and actual_h > 0:
                ratio = actual_h / actual_w
                raw_h = plan_w * ratio
                # 对齐到最近的合法贴图尺寸（VALID_TEXTURE_SIZES 中最接近的）
                from utils.constants import VALID_TEXTURE_SIZES
                plan_h = min(VALID_TEXTURE_SIZES, key=lambda s: abs(s - raw_h))
            else:
                plan_h = plan_w  # fallback

        # 生成缩略图
        thumb = self._generate_thumbnail(saved_path)

        # 创建贴图项（标记为截图）
        name = os.path.splitext(os.path.basename(saved_path))[0]
        tex = TextureItem(
            original_path=saved_path,
            original_size=(actual_w, actual_h),
            display_size=(plan_w, plan_h),
            name=name,
            thumbnail_path=thumb,
            is_screenshot=True,
        )
        self._project.add_texture(tex)

        self.refresh()
        self._skip_external_refresh = True
        self.project_changed.emit()
        self._skip_external_refresh = False

    def _on_screenshot_cancelled(self):
        """截图取消回调"""
        main_win = self.window()
        if main_win:
            if getattr(self, '_main_was_maximized', False):
                main_win.showMaximized()
            else:
                main_win.showNormal()
            main_win.activateWindow()

    def get_screenshot_resolution(self) -> tuple:
        """获取当前截图分辨率设置"""
        return (self._ss_width_combo.currentData(), self._ss_height_combo.currentData())

    def _get_exclude_suffixes(self) -> List[str]:
        """获取排除后缀列表"""
        main_win = self.window()
        if hasattr(main_win, '_settings'):
            return main_win._settings.get("exclude_suffixes", DEFAULT_EXCLUDE_SUFFIXES)
        return DEFAULT_EXCLUDE_SUFFIXES

    def _should_exclude(self, name: str) -> bool:
        """检查文件名是否需要排除"""
        suffixes = self._get_exclude_suffixes()
        name_no_ext = os.path.splitext(name)[0]
        for suffix in suffixes:
            if name_no_ext.endswith(suffix):
                return True
        return False

    def _import_images(self, paths: list):
        # 剔除后缀排除
        exclude_suffixes = self._get_exclude_suffixes()
        filtered_paths = []
        excluded_count = 0
        for p in paths:
            basename = os.path.basename(p)
            if self._should_exclude(basename):
                excluded_count += 1
            else:
                filtered_paths.append(p)

        # 剔重：已存在的路径不导入
        existing_paths = {t.original_path for t in self._project.library}
        new_paths = [p for p in filtered_paths if p not in existing_paths]

        dup_count = len(filtered_paths) - len(new_paths)

        if not new_paths:
            msg = "没有新的图片可导入。"
            if dup_count > 0:
                msg += f"\n{dup_count} 张图片已存在于素材库中。"
            if excluded_count > 0:
                msg += f"\n{excluded_count} 张图片因后缀被排除。"
            QMessageBox.information(self, "导入", msg)
            return

        # 获取自动压缩设置
        auto_compress = self._get_auto_compress_settings()

        # 创建进度对话框
        from PySide6.QtWidgets import QProgressDialog
        progress = QProgressDialog("正在导入图片...", "取消", 0, len(new_paths), self)
        progress.setWindowTitle("导入图片")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setMinimumWidth(360)

        imported_count = 0
        from PySide6.QtWidgets import QApplication

        for i, path in enumerate(new_paths):
            if progress.wasCanceled():
                break

            name = os.path.splitext(os.path.basename(path))[0]
            progress.setLabelText(f"正在导入: {name} ({i + 1}/{len(new_paths)})")
            progress.setValue(i)

            original_size = ImageService.get_image_size(path)
            if not original_size:
                continue

            if auto_compress:
                display_w, display_h = self._apply_auto_compress(
                    original_size[0], original_size[1], auto_compress
                )
            else:
                display_w = self._snap_to_power_of_two(original_size[0])
                display_h = self._snap_to_power_of_two(original_size[1])

            thumb = self._generate_thumbnail(path)

            tex = TextureItem(
                original_path=path,
                original_size=original_size,
                display_size=(display_w, display_h),
                name=name,
                thumbnail_path=thumb,
            )
            self._project.add_texture(tex)
            imported_count += 1

            # 每导入一张就追加到视图（逐个出现效果）
            usage_map = self._build_usage_map()
            atlas_indices = usage_map.get(tex.id, [])
            self._add_to_grid(tex, atlas_indices)
            self._add_to_tree(tex, atlas_indices)
            self._update_count()

            # 让 UI 刷新，显示逐个出现效果
            QApplication.processEvents()

        progress.setValue(len(new_paths))
        progress.close()

        # 最终全量刷新一次确保排序和状态正确
        self.refresh()
        self._skip_external_refresh = True
        self.project_changed.emit()
        self._skip_external_refresh = False

        # 提示信息（状态栏，不弹窗打断用户）
        info_parts = [f"成功导入 {imported_count} 张图片。"]
        if dup_count > 0:
            info_parts.append(f"{dup_count} 张重复已跳过。")
        if excluded_count > 0:
            info_parts.append(f"{excluded_count} 张因后缀排除。")
        main_win = self.window()
        if hasattr(main_win, 'statusBar'):
            main_win.statusBar().showMessage(" ".join(info_parts), 5000)

    def _get_auto_compress_settings(self) -> Optional[dict]:
        main_win = self.window()
        if hasattr(main_win, '_settings'):
            settings = main_win._settings
            if settings.get("auto_compress", True):
                return {
                    "width_map": settings.get("width_compress_map", None),
                    "height_mode": settings.get("height_compress_mode", "proportional"),
                    "height_map": settings.get("height_compress_map", None),
                }
        return None

    def _apply_auto_compress(self, orig_w: int, orig_h: int, compress_cfg: dict) -> tuple:
        from utils.constants import DEFAULT_WIDTH_COMPRESS_MAP

        width_map = compress_cfg.get("width_map") or DEFAULT_WIDTH_COMPRESS_MAP
        height_mode = compress_cfg.get("height_mode", "proportional")
        height_map = compress_cfg.get("height_map")

        new_w = self._map_compress_value(orig_w, width_map)

        if height_mode == "proportional" or height_map is None:
            ratio = new_w / orig_w if orig_w > 0 else 1
            new_h = max(VALID_TEXTURE_SIZES[0], int(orig_h * ratio))
            new_h = self._snap_to_power_of_two(new_h)
        else:
            new_h = self._map_compress_value(orig_h, height_map)

        return (new_w, new_h)

    def _map_compress_value(self, value: int, compress_map: dict) -> int:
        if value in compress_map:
            return compress_map[value]
        keys = sorted(compress_map.keys(), reverse=True)
        for k in keys:
            if value >= k:
                return compress_map[k]
        return min(compress_map.values()) if compress_map else self._snap_to_power_of_two(value)

    def _snap_to_power_of_two(self, value: int) -> int:
        for s in VALID_TEXTURE_SIZES:
            if s >= value:
                return s
        return VALID_TEXTURE_SIZES[-1]

    # ---- Search ----
    def _on_search(self, text: str):
        text = text.lower().strip()
        for i in range(self._grid_list.count()):
            item = self._grid_list.item(i)
            tid = item.data(Qt.ItemDataRole.UserRole)
            tex = self._project.find_texture(tid)
            if tex:
                visible = text == "" or text in tex.name.lower()
                item.setHidden(not visible)

        for i in range(self._tree_list.topLevelItemCount()):
            item = self._tree_list.topLevelItem(i)
            tid = item.data(0, Qt.ItemDataRole.UserRole)
            tex = self._project.find_texture(tid)
            if tex:
                visible = text == "" or text in tex.name.lower()
                item.setHidden(not visible)

    # ---- Refresh library ----
    def _on_refresh_library(self):
        """刷新素材库：清除缩略图缓存并重新生成，检测图片变更"""
        if not self._project.library:
            QMessageBox.information(self, "刷新", "素材库中没有素材。")
            return

        from PySide6.QtWidgets import QApplication

        # 清除所有缩略图缓存
        ImageService.clear_thumbnail_cache()

        missing_count = 0
        updated_count = 0

        for tex in self._project.library:
            # 清除缩略图缓存路径
            tex.thumbnail_path = None

            if os.path.exists(tex.original_path):
                # 重新获取尺寸（检测图片是否更改）
                new_size = ImageService.get_image_size(tex.original_path)
                if new_size and new_size != tex.original_size:
                    tex.original_size = new_size
                    updated_count += 1
                # 重新生成缩略图
                thumb = self._generate_thumbnail(tex.original_path)
                if thumb:
                    tex.thumbnail_path = thumb
            else:
                missing_count += 1

        QApplication.processEvents()
        self.refresh()
        self._skip_external_refresh = True
        self.project_changed.emit()
        self._skip_external_refresh = False

        # 提示信息
        msg_parts = ["素材库刷新完成。"]
        if updated_count > 0:
            msg_parts.append(f"{updated_count} 张图片尺寸已更新。")
        if missing_count > 0:
            msg_parts.append(f"{missing_count} 张图片文件缺失。")
        if updated_count == 0 and missing_count == 0:
            msg_parts.append("所有素材状态正常。")

    # ---- Size edit ----
    def _on_double_click_grid(self, index):
        item = self._grid_list.currentItem()
        if not item:
            return
        tid = item.data(Qt.ItemDataRole.UserRole)
        self._edit_texture_size([tid])

    def _on_double_click_tree(self, index):
        item = self._tree_list.currentItem()
        if not item:
            return
        tid = item.data(0, Qt.ItemDataRole.UserRole)
        self._edit_texture_size([tid])

    def _edit_texture_size(self, texture_ids: List[str]):
        if not texture_ids:
            return

        first_tex = self._project.find_texture(texture_ids[0])
        if not first_tex:
            return

        is_batch = len(texture_ids) > 1
        title = f"{len(texture_ids)} 张素材" if is_batch else first_tex.name

        dlg = SizeEditDialog(
            title, first_tex.original_size, first_tex.display_size, self
        )
        if dlg.exec() == SizeEditDialog.DialogCode.Accepted:
            new_size = dlg.get_size()
            for tid in texture_ids:
                tex = self._project.find_texture(tid)
                if tex:
                    tex.display_size = new_size
            self.refresh()
            self._skip_external_refresh = True
            self.project_changed.emit()
            self._skip_external_refresh = False

    def _get_selected_texture_ids(self) -> List[str]:
        if self._view_mode == "grid":
            return [
                item.data(Qt.ItemDataRole.UserRole)
                for item in self._grid_list.selectedItems()
            ]
        else:
            return [
                item.data(0, Qt.ItemDataRole.UserRole)
                for item in self._tree_list.selectedItems()
            ]

    # ---- Context menu (Grid) ----
    def _on_context_menu_grid(self, pos):
        item = self._grid_list.itemAt(pos)
        if not item:
            return
        self._show_context_menu(pos, self._grid_list)

    def _on_context_menu_tree(self, pos):
        item = self._tree_list.itemAt(pos)
        if not item:
            return
        self._show_context_menu(pos, self._tree_list)

    def _show_context_menu(self, pos, widget):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2D2D30; border: 1px solid #3C3C3C;
                border-radius: 6px; padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px; color: #CCCCCC; border-radius: 4px; margin: 2px;
            }
            QMenu::item:selected { background-color: #3C3C3C; color: #FFFFFF; }
        """)

        ids = self._get_selected_texture_ids()
        count = len(ids)

        edit_action = menu.addAction(f"设置分辨率 ({count} 张)" if count > 1 else "设置分辨率")

        # 标记子菜单
        tag_menu = menu.addMenu(f"标记类型 ({count} 张)" if count > 1 else "标记类型")
        tag_menu.setStyleSheet(menu.styleSheet())
        tag_options = [
            ("E — 自发光 (Emissive)", "E"),
            ("A — 半透明 (Alpha)", "A"),
            ("M — 遮罩 (Mask)", "M"),
            ("C1 — 自定义1", "C1"),
            ("C2 — 自定义2", "C2"),
            ("C3 — 自定义3", "C3"),
        ]
        tag_actions = {}
        for label, tag_val in tag_options:
            act = tag_menu.addAction(label)
            tag_actions[act] = tag_val
        tag_menu.addSeparator()
        clear_tag_action = tag_menu.addAction("✕ 清除标记")

        open_loc_action = menu.addAction("在资源管理器中显示")
        menu.addSeparator()
        remove_action = menu.addAction(f"从素材库移除 ({count} 张)" if count > 1 else "从素材库移除")

        action = menu.exec(widget.mapToGlobal(pos))
        if action == edit_action:
            self._edit_texture_size(ids)
        elif action in tag_actions:
            tag_val = tag_actions[action]
            for tid in ids:
                tex = self._project.find_texture(tid)
                if tex:
                    tex.tag = tag_val
            self.refresh()
            self._skip_external_refresh = True
            self.project_changed.emit()
            self._skip_external_refresh = False
        elif action == clear_tag_action:
            for tid in ids:
                tex = self._project.find_texture(tid)
                if tex:
                    tex.tag = ""
            self.refresh()
            self._skip_external_refresh = True
            self.project_changed.emit()
            self._skip_external_refresh = False
        elif action == open_loc_action:
            if ids:
                tex = self._project.find_texture(ids[0])
                if tex and os.path.exists(tex.original_path):
                    self._open_in_explorer(tex.original_path)
        elif action == remove_action:
            # 从所有合图中也移除这些贴图
            for atlas in self._project.atlas_list:
                for tid in ids:
                    atlas.remove(tid)
            for tid in ids:
                self._project.remove_texture(tid)
            self.refresh()
            self._skip_external_refresh = True
            self.project_changed.emit()
            self._skip_external_refresh = False

    def _open_in_explorer(self, file_path: str):
        file_path = os.path.normpath(file_path)
        if platform.system() == "Windows":
            subprocess.run(["explorer", "/select,", file_path])
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-R", file_path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(file_path)])

    # ---- Drag out (grid) ----
    def _grid_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        QListWidget.mousePressEvent(self._grid_list, event)

    def _grid_mouse_move(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton) or self._drag_start_pos is None:
            QListWidget.mouseMoveEvent(self._grid_list, event)
            return

        distance = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
        if distance < 10:
            QListWidget.mouseMoveEvent(self._grid_list, event)
            return

        ids = self._get_selected_texture_ids()
        if not ids:
            return

        self._start_drag(ids)

    # ---- Drag out (tree) ----
    def _tree_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        QTreeWidget.mousePressEvent(self._tree_list, event)

    def _tree_mouse_move(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton) or self._drag_start_pos is None:
            QTreeWidget.mouseMoveEvent(self._tree_list, event)
            return

        distance = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
        if distance < 10:
            QTreeWidget.mouseMoveEvent(self._tree_list, event)
            return

        ids = self._get_selected_texture_ids()
        if not ids:
            return

        self._start_drag(ids)

    def _start_drag(self, texture_ids: List[str]):
        mime = QMimeData()

        if len(texture_ids) == 1:
            payload = json.dumps({"texture_id": texture_ids[0]}).encode()
            mime.setData("application/x-texture-item", QByteArray(payload))
        else:
            payload = json.dumps({"texture_ids": texture_ids}).encode()
            mime.setData("application/x-texture-items", QByteArray(payload))

        drag = QDrag(self)
        drag.setMimeData(mime)

        tex = self._project.find_texture(texture_ids[0])
        if tex and tex.thumbnail_path and os.path.exists(tex.thumbnail_path):
            pixmap = QPixmap(tex.thumbnail_path).scaled(
                48, 48, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            drag.setPixmap(pixmap)
            drag.setHotSpot(QPoint(24, 24))

        drag.exec(Qt.DropAction.CopyAction)

    # ---- Styles ----
    @staticmethod
    def _btn_style() -> str:
        return """
            QPushButton {
                background-color: transparent; color: #CCCCCC;
                border: 1px solid #555555; border-radius: 6px;
                padding: 5px 12px; font-size: 11px;
            }
            QPushButton:hover {
                background-color: #3C3C3C; color: #FFFFFF; border-color: #666666;
            }
            QPushButton:pressed { background-color: #333333; }
        """

    @staticmethod
    def _list_style() -> str:
        return """
            QListWidget { background: transparent; border: none; }
            QListWidget::item {
                border-radius: 6px;
                padding: 4px; color: #CCCCCC;
            }
            QListWidget::item:hover { background-color: rgba(56, 56, 56, 180); }
            QListWidget::item:selected {
                background-color: transparent;
                border: 2px solid #0078D4;
            }
        """

    @staticmethod
    def _view_toggle_style(active: bool) -> str:
        if active:
            return f"""
                QToolButton {{
                    background-color: {COLOR_PRIMARY}; color: #FFFFFF;
                    border: none; border-radius: 4px; font-size: 14px;
                }}
            """
        return """
            QToolButton {
                background-color: #3C3C3C; color: #888888;
                border: none; border-radius: 4px; font-size: 14px;
            }
            QToolButton:hover { background-color: #4A4A4A; color: #CCCCCC; }
        """

    @staticmethod
    def _sort_btn_style(active: bool) -> str:
        if active:
            return f"""
                QToolButton {{
                    background-color: {COLOR_PRIMARY}; color: #FFFFFF;
                    border: none; border-radius: 3px; font-size: 10px;
                    font-weight: bold;
                }}
            """
        return """
            QToolButton {
                background-color: #3C3C3C; color: #888888;
                border: none; border-radius: 3px; font-size: 10px;
            }
            QToolButton:hover { background-color: #4A4A4A; color: #CCCCCC; }
        """
