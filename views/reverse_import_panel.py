"""检查模式 - 右侧导入 & 结果面板"""

import os
from typing import Optional, List, Dict, Tuple


from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QFrame, QScrollArea,
    QListWidget, QListWidgetItem, QSizePolicy, QGridLayout,
    QLineEdit, QProgressBar,
)
from PySide6.QtCore import Qt, Signal, QSize, QUrl, QTimer
from PySide6.QtGui import (
    QColor, QDragEnterEvent, QDropEvent, QFont, QPainter,
    QPixmap, QImage, QPen,
)
from PIL import Image as PILImage

from models.reverse_atlas_item import ReverseAtlasItem, SubRegion
from models.duplicate_result import DuplicateResult, DuplicateGroup
from services.image_service import ImageService
from utils.constants import (
    PANEL_BORDER_RADIUS,
    REVERSE_COLOR_PRIMARY,
    REVERSE_COLOR_BG_PANEL,
    REVERSE_COLOR_BG_CARD,
    REVERSE_COLOR_BORDER,
    REVERSE_COLOR_TEXT_PRIMARY,
    REVERSE_COLOR_TEXT_SECONDARY,
    REVERSE_COLOR_TEXT_DISABLED,
    REVERSE_COLOR_BG_BASE,
    DEFAULT_ATLAS_SUFFIX,
    SUPPORTED_IMAGE_FORMATS,
)


class ReverseImportPanel(QWidget):
    """检查模式 - 右侧导入区域 & 结果展示"""

    files_imported = Signal(list)               # list of file paths
    group_selected = Signal(int, str, str)      # group_id, atlas_id, region_id
    populate_progress = Signal(int, int)        # current, total — 分批渲染进度
    populate_finished = Signal()                # 分批渲染完成


    def __init__(self, parent=None):
        super().__init__(parent)
        self._atlas_suffix = DEFAULT_ATLAS_SUFFIX
        self._duplicate_result: Optional[DuplicateResult] = None
        self._atlas_items: List[ReverseAtlasItem] = []  # 缓存图集列表用于缩略图
        self._group_targets: Dict[int, Tuple[str, str]] = {}  # group_id -> (atlas_id, region_id)
        self.setMinimumWidth(260)

        self.setMaximumWidth(380)
        self.setAcceptDrops(True)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        container = QFrame()
        container.setObjectName("reverseImportContainer")
        container.setStyleSheet(f"""
            QFrame#reverseImportContainer {{
                background-color: {REVERSE_COLOR_BG_PANEL};
                border-radius: {PANEL_BORDER_RADIUS}px;
                border: 1px solid {REVERSE_COLOR_BORDER};
            }}
        """)
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(12, 12, 12, 12)
        c_layout.setSpacing(10)

        # ===== 导入区域 =====
        import_title = QLabel("导入图集")
        import_title.setStyleSheet(f"""
            font-size: 14px; font-weight: 600;
            color: {REVERSE_COLOR_PRIMARY};
            background: transparent;
        """)
        c_layout.addWidget(import_title)

        # 拖拽区域
        self._drop_zone = QFrame()
        self._drop_zone.setProperty("class", "drop-zone")
        self._drop_zone.setMinimumHeight(100)
        self._drop_zone.setStyleSheet(f"""
            QFrame {{
                background-color: #FAFAF5;
                border: 2px dashed {REVERSE_COLOR_BORDER};
                border-radius: 10px;
            }}
            QFrame:hover {{
                border-color: {REVERSE_COLOR_PRIMARY};
                background-color: #FFFDF5;
            }}
        """)
        drop_layout = QVBoxLayout(self._drop_zone)
        drop_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_label = QLabel("🖼️ 拖拽图集文件到此处")
        drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_label.setStyleSheet(f"""
            font-size: 12px; color: {REVERSE_COLOR_TEXT_SECONDARY};
            background: transparent; border: none;
        """)
        drop_layout.addWidget(drop_label)
        suffix_label = QLabel(f"仅识别 *{self._atlas_suffix}.* 文件")
        suffix_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        suffix_label.setStyleSheet(f"""
            font-size: 10px; color: {REVERSE_COLOR_TEXT_DISABLED};
            background: transparent; border: none;
        """)
        self._suffix_hint_label = suffix_label
        drop_layout.addWidget(suffix_label)
        c_layout.addWidget(self._drop_zone)

        # 导入按钮
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

        # ===== 分隔线 =====
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {REVERSE_COLOR_BORDER}; background: transparent;")
        c_layout.addWidget(sep)

        # ===== 分析结果 =====
        result_header = QHBoxLayout()
        result_title = QLabel("分析结果")
        result_title.setStyleSheet(f"""
            font-size: 14px; font-weight: 600;
            color: {REVERSE_COLOR_PRIMARY};
            background: transparent;
        """)
        result_header.addWidget(result_title)
        result_header.addStretch()

        self._result_count = QLabel("")
        self._result_count.setStyleSheet(f"""
            font-size: 11px; color: {REVERSE_COLOR_TEXT_DISABLED};
            background: transparent;
        """)
        result_header.addWidget(self._result_count)
        c_layout.addLayout(result_header)

        # 搜索框 —— 输入组号快速定位
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("输入组号快速定位，如 60")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: #FAFAF5;
                border: 1px solid {REVERSE_COLOR_BORDER};
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
                color: {REVERSE_COLOR_TEXT_PRIMARY};
            }}
            QLineEdit:focus {{
                border-color: {REVERSE_COLOR_PRIMARY};
                background-color: #FFFDF5;
            }}
        """)
        self._search_input.textChanged.connect(self._on_search_group)
        self._search_input.hide()  # 无结果时隐藏
        c_layout.addWidget(self._search_input)

        # 加载进度条 —— 分批渲染时显示
        self._load_progress = QProgressBar()
        self._load_progress.setFixedHeight(4)
        self._load_progress.setTextVisible(False)
        self._load_progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: {REVERSE_COLOR_BORDER};
                border: none; border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {REVERSE_COLOR_PRIMARY};
                border-radius: 2px;
            }}
        """)
        self._load_progress.hide()
        c_layout.addWidget(self._load_progress)

        # 结果列表
        self._result_list = QListWidget()
        self._result_list.setStyleSheet(f"""
            QListWidget {{
                background: transparent; border: none; outline: none;
            }}
            QListWidget::item {{
                background-color: {REVERSE_COLOR_BG_CARD};
                border-radius: 6px;
                padding: 4px; margin: 2px 0px;
                border: 1px solid #E8E8E3;
            }}
            QListWidget::item:hover {{
                background-color: #FAFAF5;
                border-color: {REVERSE_COLOR_BORDER};
            }}
            QListWidget::item:selected {{
                background-color: #FFFDF5;
                border: 2px solid {REVERSE_COLOR_PRIMARY};
            }}
        """)
        self._result_list.currentItemChanged.connect(self._on_result_selected)
        c_layout.addWidget(self._result_list, 1)

        # 无结果提示
        self._no_result_label = QLabel("导入图集并点击「开始分析」查看结果")
        self._no_result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_result_label.setWordWrap(True)
        self._no_result_label.setStyleSheet(f"""
            font-size: 11px; color: {REVERSE_COLOR_TEXT_DISABLED};
            background: transparent;
        """)
        c_layout.addWidget(self._no_result_label)

        layout.addWidget(container)

    # ---- 公共接口 ----
    def set_atlas_suffix(self, suffix: str):
        self._atlas_suffix = suffix
        self._suffix_hint_label.setText(f"仅识别 *{suffix}.* 文件")

    def set_atlas_items(self, items: List[ReverseAtlasItem]):
        """缓存图集列表，用于生成结果缩略图"""
        self._atlas_items = items

    def set_duplicate_result(self, result: Optional[DuplicateResult]):
        self._duplicate_result = result
        self._populate_results()

    def clear_results(self):
        self._duplicate_result = None
        self._atlas_items = []
        self._group_targets.clear()
        self._result_list.clear()
        self._result_count.setText("")
        self._no_result_label.show()
        self._search_input.hide()
        self._search_input.clear()
        self._load_progress.hide()
        # 停止正在进行的分批渲染
        if hasattr(self, '_batch_timer') and self._batch_timer is not None:
            self._batch_timer.stop()
            self._batch_timer = None


    # ---- Drag & Drop ----
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
                paths.extend(self._scan_atlas_files(local_path))
            elif os.path.isfile(local_path):
                if self._is_atlas_file(local_path):
                    paths.append(local_path)

        if paths:
            self.files_imported.emit(paths)
            event.acceptProposedAction()
        else:
            QMessageBox.information(
                self, "导入",
                f"未找到符合条件的图集文件（后缀: {self._atlas_suffix}）"
            )
            event.ignore()

    # ---- 导入 ----
    def _on_import_files(self):
        fmt_str = " ".join(f"*{ext}" for ext in SUPPORTED_IMAGE_FORMATS)
        paths, _ = QFileDialog.getOpenFileNames(
            self, "导入图集文件", "",
            f"图片文件 ({fmt_str});;所有文件 (*.*)"
        )
        if paths:
            atlas_paths = [p for p in paths if self._is_atlas_file(p)]
            if atlas_paths:
                self.files_imported.emit(atlas_paths)
            else:
                QMessageBox.information(
                    self, "导入",
                    f"所选文件不符合图集后缀规则（{self._atlas_suffix}）"
                )

    def _on_import_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择图集文件夹")
        if dir_path:
            paths = self._scan_atlas_files(dir_path)
            if paths:
                self.files_imported.emit(paths)
            else:
                QMessageBox.information(
                    self, "导入",
                    f"该文件夹中未找到符合条件的图集文件（后缀: {self._atlas_suffix}）"
                )

    def _is_atlas_file(self, file_path: str) -> bool:
        name, ext = os.path.splitext(os.path.basename(file_path))
        if ext.lower() not in SUPPORTED_IMAGE_FORMATS:
            return False
        return name.endswith(self._atlas_suffix)

    def _scan_atlas_files(self, dir_path: str) -> List[str]:
        result = []
        for root, _, files in os.walk(dir_path):
            for f in files:
                full_path = os.path.join(root, f)
                if self._is_atlas_file(full_path):
                    result.append(full_path)
        result.sort()
        return result

    # ---- 结果展示（分批渲染，避免卡顿） ----
    _BATCH_SIZE = 10  # 每批渲染的组数

    def _populate_results(self):
        self._result_list.clear()
        self._group_targets.clear()

        # 停止之前正在进行的分批渲染
        if hasattr(self, '_batch_timer') and self._batch_timer is not None:
            self._batch_timer.stop()
            self._batch_timer = None

        if not self._duplicate_result or not self._duplicate_result.groups:
            self._result_count.setText("")
            self._no_result_label.show()
            self._search_input.hide()
            self._search_input.clear()
            self._load_progress.hide()
            self._no_result_label.setText(
                "未检测到重复内容" if self._duplicate_result else
                "导入图集并点击「开始分析」查看结果"
            )
            return

        self._no_result_label.hide()
        result = self._duplicate_result

        # 构建 atlas_id -> ReverseAtlasItem 和 region_id -> (SubRegion, ReverseAtlasItem) 映射
        self._atlas_map: Dict[str, ReverseAtlasItem] = {}
        self._region_map: Dict[str, tuple] = {}
        for atlas in self._atlas_items:
            self._atlas_map[atlas.id] = atlas
            for region in atlas.sub_regions:
                self._region_map[region.region_id] = (region, atlas)

        self._result_count.setText(f"{result.group_count} 组重复")
        self._search_input.show()

        # 初始化分批渲染状态
        self._pending_groups = list(result.groups)
        self._batch_index = 0
        total = len(self._pending_groups)

        # 显示进度条
        self._load_progress.setMaximum(total)
        self._load_progress.setValue(0)
        self._load_progress.show()

        # 用于记录 group_id -> QListWidgetItem 索引，搜索用
        self._group_id_to_row: Dict[int, int] = {}

        # 启动分批渲染定时器
        self._batch_timer = QTimer(self)
        self._batch_timer.setInterval(0)  # 每次事件循环空闲时执行
        self._batch_timer.timeout.connect(self._render_next_batch)
        self._batch_timer.start()

    def _render_next_batch(self):
        """分批渲染结果卡片，每批 _BATCH_SIZE 个"""
        if self._batch_index >= len(self._pending_groups):
            # 全部渲染完毕
            if hasattr(self, '_batch_timer') and self._batch_timer:
                self._batch_timer.stop()
                self._batch_timer = None
            self._load_progress.hide()
            self.populate_finished.emit()
            return

        end = min(self._batch_index + self._BATCH_SIZE, len(self._pending_groups))
        for i in range(self._batch_index, end):
            group = self._pending_groups[i]
            widget = _ResultGroupWidget(group, self._atlas_map, self._region_map)
            widget.region_jump.connect(self._on_region_jump)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, group.group_id)

            atlas_id, region_id = self._resolve_group_target(group, self._region_map)
            self._group_targets[group.group_id] = (atlas_id, region_id)

            row_count = min(len(group.region_ids), 4)
            height = 36 + row_count * 56 + (8 if len(group.region_ids) > 4 else 0) + 8
            item.setSizeHint(QSize(0, height))
            self._result_list.addItem(item)
            self._result_list.setItemWidget(item, widget)

            # 记录 group_id -> row 映射
            self._group_id_to_row[group.group_id] = self._result_list.count() - 1

        self._batch_index = end
        self._load_progress.setValue(end)
        self.populate_progress.emit(end, len(self._pending_groups))

    # ---- 搜索定位 ----
    def _on_search_group(self, text: str):
        """输入组号快速定位到对应的组"""
        text = text.strip()
        if not text:
            return
        try:
            group_id = int(text)
        except ValueError:
            return

        row = self._group_id_to_row.get(group_id)
        if row is not None and row < self._result_list.count():
            item = self._result_list.item(row)
            self._result_list.setCurrentItem(item)
            self._result_list.scrollToItem(
                item, QListWidget.ScrollHint.PositionAtTop
            )

    def scroll_to_group(self, group_id: int):
        """外部调用：滚动到指定重复组并选中（用于视口点击联动）"""
        row = getattr(self, '_group_id_to_row', {}).get(group_id)
        if row is not None and row < self._result_list.count():
            item = self._result_list.item(row)
            # 阻断信号以避免循环跳转
            self._result_list.blockSignals(True)
            self._result_list.setCurrentItem(item)
            self._result_list.scrollToItem(
                item, QListWidget.ScrollHint.PositionAtCenter
            )
            self._result_list.blockSignals(False)

    @staticmethod
    def _resolve_group_target(
        group: DuplicateGroup,
        region_map: Dict[str, tuple],
    ) -> Tuple[str, str]:
        """返回当前分组默认跳转的图集和区域。"""
        for region_id in group.region_ids:
            region_data = region_map.get(region_id)
            if not region_data:
                continue
            region, atlas = region_data
            return atlas.id, region.region_id
        return "", ""

    def _on_result_selected(self, current, previous):
        if current:
            group_id = current.data(Qt.ItemDataRole.UserRole)
            atlas_id, region_id = self._group_targets.get(group_id, ("", ""))
            self.group_selected.emit(group_id, atlas_id, region_id)

    def _on_region_jump(self, group_id: int, atlas_id: str, region_id: str):
        """箭头按钮点击：跳转到指定图集并定位区域"""
        self.group_selected.emit(group_id, atlas_id, region_id)


    # ---- 样式 ----
    @staticmethod
    def _btn_style() -> str:
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {REVERSE_COLOR_TEXT_SECONDARY};
                border: 1px solid {REVERSE_COLOR_BORDER};
                border-radius: 6px;
                padding: 5px 12px; font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #FFFDF5;
                color: {REVERSE_COLOR_TEXT_PRIMARY};
                border-color: {REVERSE_COLOR_PRIMARY};
            }}
            QPushButton:pressed {{ background-color: #F5EDD5; }}
        """


class _ResultGroupWidget(QWidget):
    """结果分组卡片 - 展示重复区域缩略图与图集信息，支持箭头跳转"""

    # 信号：点击某个区域行的箭头时发出 (group_id, atlas_id, region_id)
    region_jump = Signal(int, str, str)

    def __init__(
        self,
        group: DuplicateGroup,
        atlas_map: Dict[str, ReverseAtlasItem],
        region_map: Dict[str, tuple],
        parent=None,
    ):
        super().__init__(parent)
        self._group = group
        self._atlas_map = atlas_map
        self._region_map = region_map
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # ===== 头部：颜色圆点 + 组号 + 匹配类型 =====
        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)

        # 颜色标记条（竖线）
        color_bar = QFrame()
        color_bar.setFixedSize(4, 20)
        color_bar.setStyleSheet(f"""
            background-color: {self._group.color};
            border-radius: 2px;
        """)
        header_layout.addWidget(color_bar)

        group_label = QLabel(f"组 #{self._group.group_id}")
        group_label.setStyleSheet(f"""
            font-size: 12px; font-weight: 600;
            color: {REVERSE_COLOR_TEXT_PRIMARY};
            background: transparent;
        """)
        header_layout.addWidget(group_label)

        # 区域尺寸标签（从第一个有效 region 获取）
        size_text = ""
        for rid in self._group.region_ids:
            rd = self._region_map.get(rid)
            if rd:
                region, _ = rd
                size_text = f"{region.width}×{region.height}"
                break
        if size_text:
            size_label = QLabel(size_text)
            size_label.setStyleSheet(f"""
                color: #4CAF50; font-weight: 500;
                font-size: 10px; background: transparent;
                padding: 1px 6px;
                border: 1px solid #4CAF50;
                border-radius: 3px;
            """)
            header_layout.addWidget(size_label)

        header_layout.addStretch()

        detail_label = QLabel(
            f"{self._group.atlas_count} 张图集"
        )
        detail_label.setStyleSheet(f"""
            font-size: 10px; color: {REVERSE_COLOR_TEXT_DISABLED};
            background: transparent;
        """)
        header_layout.addWidget(detail_label)

        layout.addLayout(header_layout)

        # ===== 区域缩略图列表 =====
        max_show = 4  # 最多展示4个区域
        shown = 0
        for region_id in self._group.region_ids:
            if shown >= max_show:
                break
            if region_id not in self._region_map:
                continue

            region, atlas = self._region_map[region_id]
            row_widget = self._create_region_row(region, atlas, region_id)
            layout.addWidget(row_widget)
            shown += 1

        remaining = len(self._group.region_ids) - shown
        if remaining > 0:
            more_label = QLabel(f"  ... 还有 {remaining} 个区域")
            more_label.setStyleSheet(f"""
                font-size: 10px; color: {REVERSE_COLOR_TEXT_DISABLED};
                background: transparent; padding: 0 0 0 4px;
            """)
            layout.addWidget(more_label)

    def _create_region_row(self, region: SubRegion, atlas: ReverseAtlasItem,
                           region_id: str) -> QWidget:
        """创建单个重复区域的展示行：缩略图 + 图集名 + 坐标信息 + 跳转箭头"""
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 2, 4, 2)
        row_layout.setSpacing(8)

        # 缩略图（从原图裁切）
        thumb_label = QLabel()
        thumb_label.setFixedSize(44, 44)
        thumb_label.setStyleSheet(f"""
            border: 2px solid {self._group.color};
            border-radius: 4px;
            background: #F5F5F0;
        """)
        pixmap = self._crop_region_thumbnail(region, atlas, 44)
        if pixmap:
            thumb_label.setPixmap(pixmap)
            thumb_label.setScaledContents(True)
        else:
            thumb_label.setText("?")
            thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row_layout.addWidget(thumb_label)

        # 文字信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(1)

        # 图集名称
        atlas_name = atlas.name
        if len(atlas_name) > 24:
            atlas_name = atlas_name[:22] + "..."
        name_label = QLabel(atlas_name)
        name_label.setToolTip(atlas.file_path)
        name_label.setStyleSheet(f"""
            font-size: 11px; font-weight: 500;
            color: {REVERSE_COLOR_TEXT_PRIMARY};
            background: transparent;
        """)
        info_layout.addWidget(name_label)

        # 坐标与尺寸
        coord_label = QLabel(f"({region.x}, {region.y})  {region.width}×{region.height}")
        coord_label.setStyleSheet(f"""
            font-size: 9px; color: {REVERSE_COLOR_TEXT_DISABLED};
            background: transparent;
        """)
        info_layout.addWidget(coord_label)

        row_layout.addLayout(info_layout, 1)

        # 跳转箭头按钮（紧凑型）
        jump_btn = QPushButton("⤴")
        jump_btn.setFixedSize(20, 20)
        jump_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        jump_btn.setToolTip(f"跳转到 {atlas.name}")
        jump_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {REVERSE_COLOR_TEXT_DISABLED};
                border: none;
                border-radius: 3px;
                font-size: 12px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {REVERSE_COLOR_PRIMARY};
                color: #FFFFFF;
            }}
            QPushButton:pressed {{
                background-color: #C08810;
                color: #FFFFFF;
            }}
        """)
        # 绑定跳转 - 捕获 atlas_id 和 region_id
        _atlas_id = atlas.id
        _region_id = region_id
        _group_id = self._group.group_id
        jump_btn.clicked.connect(
            lambda _, gid=_group_id, aid=_atlas_id, rid=_region_id:
                self.region_jump.emit(gid, aid, rid)
        )
        row_layout.addWidget(jump_btn)

        return row

    @staticmethod
    def _crop_region_thumbnail(
        region: SubRegion, atlas: ReverseAtlasItem, size: int
    ) -> Optional[QPixmap]:
        """从图集原图裁切指定区域并缩放为缩略图"""
        try:
            if not os.path.exists(atlas.file_path):
                return None
            with PILImage.open(atlas.file_path) as img:
                img = img.convert("RGBA")
                cropped = img.crop((
                    region.x, region.y,
                    region.x + region.width,
                    region.y + region.height,
                ))
                cropped.thumbnail((size, size), PILImage.Resampling.LANCZOS)
                # PIL -> QPixmap
                data = cropped.tobytes("raw", "RGBA")
                qimg = QImage(
                    data, cropped.width, cropped.height,
                    cropped.width * 4, QImage.Format.Format_RGBA8888
                )
                # 需要保持数据引用
                pixmap = QPixmap.fromImage(qimg.copy())
                return pixmap
        except Exception:
            return None
