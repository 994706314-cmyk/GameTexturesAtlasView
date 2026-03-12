"""左侧合图大纲面板"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QComboBox, QInputDialog,
    QMessageBox, QProgressBar, QFrame,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter, QImage

from models.project_model import ProjectModel
from models.atlas_model import AtlasModel
from utils.constants import (
    SUPPORTED_ATLAS_SIZES, DEFAULT_ATLAS_SIZE, COLOR_PRIMARY,
    PANEL_BORDER_RADIUS,
)


class AtlasOutlinePanel(QWidget):
    """左侧合图大纲面板"""

    atlas_selected = Signal(str)    # atlas_id
    project_changed = Signal()

    def __init__(self, project: ProjectModel, parent=None):
        super().__init__(parent)
        self._project = project
        self._current_atlas_id = None
        self.setMinimumWidth(200)
        self.setMaximumWidth(300)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        container = QFrame()
        container.setObjectName("outlineContainer")
        container.setStyleSheet(f"""
            QFrame#outlineContainer {{
                background-color: #252526;
                border-radius: {PANEL_BORDER_RADIUS}px;
                border: 1px solid #3C3C3C;
            }}
        """)
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(12, 12, 12, 12)
        c_layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("图集列表")
        title.setStyleSheet("font-size: 14px; font-weight: 600; color: #FFFFFF; background: transparent;")
        header.addWidget(title)
        header.addStretch()

        # 清理空合图按钮
        self._clean_btn = QPushButton("🧹")
        self._clean_btn.setFixedSize(32, 32)
        self._clean_btn.setToolTip("清理空的合图并重新排序")
        self._clean_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent; color: #CCCCCC;
                border: 1px solid #555555; border-radius: 16px;
                font-size: 16px; padding: 0px;
            }
            QPushButton:hover {
                background-color: #3C3C3C; color: #FFFFFF; border-color: #888888;
            }
            QPushButton:pressed { background-color: #333333; }
        """)
        self._clean_btn.clicked.connect(self._on_clean_empty)
        header.addWidget(self._clean_btn)

        self._add_btn = QPushButton("+")
        self._add_btn.setFixedSize(32, 32)
        self._add_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent; color: {COLOR_PRIMARY};
                border: 2px solid {COLOR_PRIMARY}; border-radius: 16px;
                font-size: 20px; font-weight: 700;
                padding: 0px; padding-bottom: 2px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_PRIMARY}; color: #FFFFFF;
            }}
            QPushButton:pressed {{ background-color: #005A9E; color: #FFFFFF; border-color: #005A9E; }}
        """)
        self._add_btn.setToolTip("添加新合图")
        self._add_btn.clicked.connect(self._on_add_atlas)
        header.addWidget(self._add_btn)

        c_layout.addLayout(header)

        self._list = QListWidget()
        self._list.setStyleSheet("""
            QListWidget { background: transparent; border: none; outline: none; }
            QListWidget::item {
                background-color: #2D2D30; border-radius: 8px;
                padding: 0px; margin: 3px 0px;
            }
            QListWidget::item:hover { background-color: #383838; }
            QListWidget::item:selected {
                background-color: #2D2D30;
                border-left: 3px solid #0078D4;
            }
        """)
        self._list.currentItemChanged.connect(self._on_item_selected)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        c_layout.addWidget(self._list, 1)

        layout.addWidget(container)

    def set_project(self, project: ProjectModel):
        self._project = project
        self._current_atlas_id = None
        self.refresh()

    def get_current_atlas_id(self) -> str:
        return self._current_atlas_id

    def select_atlas(self, atlas_id: str):
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == atlas_id:
                self._list.setCurrentItem(item)
                break

    def select_prev_atlas(self):
        current_row = self._list.currentRow()
        if current_row > 0:
            self._list.setCurrentRow(current_row - 1)

    def select_next_atlas(self):
        current_row = self._list.currentRow()
        if current_row < self._list.count() - 1:
            self._list.setCurrentRow(current_row + 1)

    def refresh(self):
        self._list.blockSignals(True)
        self._list.setUpdatesEnabled(False)
        self._list.clear()
        for i, atlas in enumerate(self._project.atlas_list):
            self._add_list_item(atlas, i + 1)
        self._list.setUpdatesEnabled(True)
        self._list.blockSignals(False)

        if self._current_atlas_id:
            self.select_atlas(self._current_atlas_id)

    def _add_list_item(self, atlas: AtlasModel, index: int = 0):
        widget = AtlasCardWidget(atlas, index)
        widget.rename_requested.connect(self._on_rename)
        widget.size_changed.connect(self._on_size_changed)

        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, atlas.id)
        item.setSizeHint(QSize(0, 80))

        self._list.addItem(item)
        self._list.setItemWidget(item, widget)

    def _on_item_selected(self, current, previous):
        if current:
            atlas_id = current.data(Qt.ItemDataRole.UserRole)
            self._current_atlas_id = atlas_id
            self.atlas_selected.emit(atlas_id)

    def _on_add_atlas(self):
        count = len(self._project.atlas_list)
        atlas = AtlasModel(name=f"合图 {count + 1}", size=DEFAULT_ATLAS_SIZE)
        self._project.add_atlas(atlas)
        self._add_list_item(atlas, count + 1)
        self._list.setCurrentRow(self._list.count() - 1)
        self.project_changed.emit()

    def _on_clean_empty(self):
        """清理所有空合图，并重新排序命名"""
        empty_count = sum(1 for a in self._project.atlas_list if not a.placed_textures)
        if empty_count == 0:
            QMessageBox.information(self, "清理", "没有空的合图需要清理。")
            return

        ret = QMessageBox.question(
            self, "清理空合图",
            f"发现 {empty_count} 张空合图。\n"
            f"清理后将删除所有空合图，并将剩余合图重新按 1, 2, 3... 排序命名。\n\n"
            f"确定要继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        # 过滤掉空合图
        non_empty = [a for a in self._project.atlas_list if a.placed_textures]

        # 重新命名
        for i, atlas in enumerate(non_empty):
            atlas.name = f"合图 {i + 1}"

        self._project.atlas_list = non_empty

        # 刷新所有面板
        self._current_atlas_id = None
        self.refresh()
        self.project_changed.emit()

        # 选中第一个合图
        if non_empty:
            self.select_atlas(non_empty[0].id)
            self.atlas_selected.emit(non_empty[0].id)

    def _on_rename(self, atlas_id: str):
        atlas = self._project.find_atlas(atlas_id)
        if not atlas:
            return
        name, ok = QInputDialog.getText(
            self, "重命名合图", "输入新名称:", text=atlas.name
        )
        if ok and name.strip():
            atlas.name = name.strip()
            self.refresh()
            self.project_changed.emit()

    def _on_size_changed(self, atlas_id: str, new_size: int):
        atlas = self._project.find_atlas(atlas_id)
        if not atlas:
            return

        if atlas.placed_textures:
            for pt in atlas.placed_textures:
                max_grid = new_size // 16
                if (pt.grid_x + pt.texture.grid_width > max_grid or
                        pt.grid_y + pt.texture.grid_height > max_grid):
                    QMessageBox.warning(
                        self, "尺寸变更",
                        f"缩小合图尺寸会导致部分贴图越界，请先移除越界的贴图。"
                    )
                    self.refresh()
                    return

        atlas.set_size(new_size)
        self.refresh()
        self.project_changed.emit()

        if atlas.id == self._current_atlas_id:
            self.atlas_selected.emit(atlas.id)

    def _on_context_menu(self, pos):
        item = self._list.itemAt(pos)
        if not item:
            return

        atlas_id = item.data(Qt.ItemDataRole.UserRole)

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

        rename_action = menu.addAction("重命名")
        delete_action = menu.addAction("删除")

        action = menu.exec(self._list.mapToGlobal(pos))
        if action == rename_action:
            self._on_rename(atlas_id)
        elif action == delete_action:
            ret = QMessageBox.question(
                self, "删除合图",
                f"确定要删除该合图吗？此操作不可撤销。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if ret == QMessageBox.StandardButton.Yes:
                self._project.remove_atlas(atlas_id)
                self.refresh()
                self.project_changed.emit()


class AtlasCardWidget(QWidget):
    """合图卡片组件"""

    # 标记类型配色（与素材库一致）
    TAG_COLORS = {
        "E": ("#FF6B00", "#FFFFFF"),   # 橙底 - 自发光
        "A": ("#00AAFF", "#FFFFFF"),   # 蓝底 - 半透明
        "M": ("#8BC34A", "#FFFFFF"),   # 黄绿底 - Mask
        "C1": ("#9C27B0", "#FFFFFF"),  # 紫底 - 自定义1
        "C2": ("#00897B", "#FFFFFF"),  # 青底 - 自定义2
        "C3": ("#E91E63", "#FFFFFF"),  # 粉底 - 自定义3
    }

    rename_requested = Signal(str)
    size_changed = Signal(str, int)  # atlas_id, new_size

    def __init__(self, atlas: AtlasModel, index: int = 0, parent=None):
        super().__init__(parent)
        self._atlas = atlas
        self._index = index  # 1-based 序号
        self._init_ui()

    @staticmethod
    def _detect_tag(atlas: AtlasModel) -> str:
        """从图集名称或已放置贴图推断标记类型"""
        name = atlas.name
        # 尝试从名称匹配 "合图_X" 模式
        for tag in ("C1", "C2", "C3", "E", "A", "M"):
            if f"_{tag}" in name:
                return tag
        # 从已放置贴图推断（取第一张的 tag）
        if atlas.placed_textures:
            first_tag = atlas.placed_textures[0].texture.tag
            if first_tag:
                return first_tag
        return ""

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        # 序号角标（左侧）
        if self._index > 0:
            index_label = QLabel(str(self._index))
            index_label.setFixedSize(22, 22)
            index_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            index_label.setStyleSheet(f"""
                background-color: {COLOR_PRIMARY};
                color: #FFFFFF;
                border-radius: 11px;
                font-size: 10px;
                font-weight: bold;
            """)
            layout.addWidget(index_label)

        # 标记类型角标
        tag = self._detect_tag(self._atlas)
        if tag and tag in self.TAG_COLORS:
            bg, fg = self.TAG_COLORS[tag]
            tag_label = QLabel(tag)
            tag_label.setFixedSize(22, 22)
            tag_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tag_label.setStyleSheet(f"""
                background-color: {bg};
                color: {fg};
                border-radius: 11px;
                font-size: 9px;
                font-weight: bold;
            """)
            tag_label.setToolTip(f"标记类型: {tag}")
            layout.addWidget(tag_label)

        preview = QLabel()
        preview.setFixedSize(48, 48)
        preview_pixmap = self._make_preview()
        preview.setPixmap(preview_pixmap)
        preview.setStyleSheet("border-radius: 4px; background: transparent;")
        layout.addWidget(preview)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)

        name_row = QHBoxLayout()
        name_label = QLabel(self._atlas.name)
        name_label.setStyleSheet("font-size: 12px; font-weight: 500; color: #FFFFFF; background: transparent;")
        name_row.addWidget(name_label)
        name_row.addStretch()

        size_combo = QComboBox()
        size_combo.setFixedWidth(80)
        size_combo.setStyleSheet("""
            QComboBox {
                background-color: #3C3C3C; color: #CCCCCC;
                border: 1px solid #555555; border-radius: 4px;
                padding: 1px 4px; font-size: 10px;
            }
            QComboBox:hover { border-color: #666666; }
            QComboBox::drop-down { border: none; width: 16px; }
            QComboBox::down-arrow {
                border-left: 3px solid transparent;
                border-right: 3px solid transparent;
                border-top: 4px solid #CCCCCC;
                margin-right: 4px;
            }
        """)
        for s in SUPPORTED_ATLAS_SIZES:
            size_combo.addItem(f"{s}", s)
        idx = SUPPORTED_ATLAS_SIZES.index(self._atlas.size) if self._atlas.size in SUPPORTED_ATLAS_SIZES else 1
        size_combo.setCurrentIndex(idx)
        size_combo.currentIndexChanged.connect(
            lambda i: self.size_changed.emit(self._atlas.id, size_combo.currentData())
        )
        name_row.addWidget(size_combo)

        info_layout.addLayout(name_row)

        count_label = QLabel(f"{len(self._atlas.placed_textures)} 张贴图")
        count_label.setStyleSheet("font-size: 10px; color: #888888; background: transparent;")
        info_layout.addWidget(count_label)

        progress = QProgressBar()
        progress.setFixedHeight(4)
        progress.setRange(0, 100)
        utilization = int(self._atlas.utilization() * 100)
        progress.setValue(utilization)
        progress.setTextVisible(False)
        progress.setStyleSheet("""
            QProgressBar { background-color: #3C3C3C; border-radius: 2px; }
            QProgressBar::chunk { background-color: #0078D4; border-radius: 2px; }
        """)
        info_layout.addWidget(progress)

        layout.addLayout(info_layout, 1)

    def _make_preview(self) -> QPixmap:
        """生成合图占位预览"""
        size = 48
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(QColor(45, 45, 48))

        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._atlas.placed_textures:
            atlas_size = self._atlas.size
            scale = size / atlas_size
            for pt in self._atlas.placed_textures:
                x = int(pt.pixel_x * scale)
                y = int(pt.pixel_y * scale)
                w = max(1, int(pt.texture.display_width * scale))
                h = max(1, int(pt.texture.display_height * scale))
                painter.fillRect(x, y, w, h, QColor(60, 100, 160, 180))
                painter.setPen(QColor(80, 120, 180, 100))
                painter.drawRect(x, y, w, h)
        else:
            painter.setPen(QColor(100, 100, 100))
            painter.drawText(0, 0, size, size, Qt.AlignmentFlag.AlignCenter, "空")

        painter.end()
        return QPixmap.fromImage(img)
