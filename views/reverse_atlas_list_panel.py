"""检查模式 - 左侧图集列表面板"""

import os
import subprocess
import platform
from typing import Optional, List, Set

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFrame, QMessageBox,
    QAbstractItemView, QMenu,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QPixmap, QPainter, QImage, QFont, QPen, QAction

from models.reverse_atlas_item import ReverseAtlasItem
from models.duplicate_result import DuplicateResult
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
)


class ReverseAtlasListPanel(QWidget):
    """检查模式 - 左侧已导入图集列表"""

    atlas_selected = Signal(str)    # atlas_id
    atlas_list_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._atlas_items: List[ReverseAtlasItem] = []
        self._current_atlas_id: Optional[str] = None
        self._duplicate_result: Optional[DuplicateResult] = None
        self._affected_atlas_ids: Set[str] = set()  # 有重复内容的图集ID集合
        self.setMinimumWidth(240)
        self.setMaximumWidth(380)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        container = QFrame()
        container.setObjectName("reverseAtlasListContainer")
        container.setStyleSheet(f"""
            QFrame#reverseAtlasListContainer {{
                background-color: {REVERSE_COLOR_BG_PANEL};
                border-radius: {PANEL_BORDER_RADIUS}px;
                border: 1px solid {REVERSE_COLOR_BORDER};
            }}
        """)
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(12, 12, 12, 12)
        c_layout.setSpacing(8)

        # 头部标题
        header = QHBoxLayout()
        title = QLabel("图集列表")
        title.setStyleSheet(f"""
            font-size: 14px; font-weight: 600;
            color: {REVERSE_COLOR_PRIMARY};
            background: transparent;
        """)
        header.addWidget(title)
        header.addStretch()

        self._count_label = QLabel("0 张")
        self._count_label.setStyleSheet(f"""
            font-size: 11px; color: {REVERSE_COLOR_TEXT_DISABLED};
            background: transparent;
        """)
        header.addWidget(self._count_label)
        c_layout.addLayout(header)

        # 图集列表
        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setStyleSheet(f"""
            QListWidget {{
                background: transparent; border: none; outline: none;
            }}
            QListWidget::item {{
                background-color: {REVERSE_COLOR_BG_CARD};
                border-radius: 8px;
                padding: 0px; margin: 3px 0px;
                border: 1px solid {REVERSE_COLOR_BORDER};
            }}
            QListWidget::item:hover {{
                background-color: #FFFDF5;
                border-color: {REVERSE_COLOR_PRIMARY};
            }}
            QListWidget::item:selected {{
                background-color: #FFFDF5;
                border-left: 3px solid {REVERSE_COLOR_PRIMARY};
            }}
        """)
        self._list.currentItemChanged.connect(self._on_item_selected)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        c_layout.addWidget(self._list, 1)

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self._clear_btn = QPushButton("清空全部")
        self._clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {REVERSE_COLOR_TEXT_SECONDARY};
                border: 1px solid {REVERSE_COLOR_BORDER};
                border-radius: 6px;
                padding: 5px 12px; font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #F0E0D0;
                color: #C0392B; border-color: #E74C3C;
            }}
            QPushButton:pressed {{ background-color: #E8D5C0; }}
        """)
        self._clear_btn.clicked.connect(self._on_clear_all)
        btn_layout.addWidget(self._clear_btn)

        btn_layout.addStretch()

        self._remove_btn = QPushButton("移除选中")
        self._remove_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {REVERSE_COLOR_TEXT_SECONDARY};
                border: 1px solid {REVERSE_COLOR_BORDER};
                border-radius: 6px;
                padding: 5px 12px; font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #F0E0D0;
                color: {REVERSE_COLOR_TEXT_PRIMARY};
                border-color: {REVERSE_COLOR_PRIMARY};
            }}
            QPushButton:pressed {{ background-color: #E8D5C0; }}
        """)
        self._remove_btn.clicked.connect(self._on_remove_selected)
        btn_layout.addWidget(self._remove_btn)

        c_layout.addLayout(btn_layout)
        layout.addWidget(container)

    # ---- 公共接口 ----
    def get_atlas_items(self) -> List[ReverseAtlasItem]:
        """返回所有已导入的图集数据"""
        return self._atlas_items

    def add_atlas_item(self, item: ReverseAtlasItem):
        """添加一个图集"""
        self._atlas_items.append(item)
        self._add_list_item(item)
        self._update_count()
        self.atlas_list_changed.emit()

    def add_atlas_items(self, items: List[ReverseAtlasItem]):
        """批量添加图集"""
        self._list.setUpdatesEnabled(False)
        for item in items:
            self._atlas_items.append(item)
            self._add_list_item(item)
        self._list.setUpdatesEnabled(True)
        self._update_count()
        self.atlas_list_changed.emit()

    def clear_all(self):
        """清空所有图集"""
        self._atlas_items.clear()
        self._list.clear()
        self._current_atlas_id = None
        self._duplicate_result = None
        self._affected_atlas_ids.clear()
        self._update_count()
        self.atlas_list_changed.emit()

    def get_current_atlas_id(self) -> Optional[str]:
        return self._current_atlas_id

    def find_atlas(self, atlas_id: str) -> Optional[ReverseAtlasItem]:
        for item in self._atlas_items:
            if item.id == atlas_id:
                return item
        return None

    def set_duplicate_result(self, result: Optional[DuplicateResult]):
        """设置分析结果，更新图集卡片的重复标记"""
        self._duplicate_result = result
        self._affected_atlas_ids.clear()
        if result:
            for group in result.groups:
                for aid in group.atlas_ids:
                    self._affected_atlas_ids.add(aid)
        # 刷新列表以更新标记
        self._refresh_cards()

    def select_atlas(self, atlas_id: str) -> bool:
        """按图集 ID 选中并滚动到对应卡片。"""
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) != atlas_id:
                continue
            self._list.scrollToItem(item, QListWidget.ScrollHint.PositionAtCenter)
            if self._list.currentItem() == item:
                self._current_atlas_id = atlas_id
                self.atlas_selected.emit(atlas_id)
            else:
                self._list.setCurrentItem(item)
            return True
        return False


    # ---- 内部方法 ----
    def _add_list_item(self, atlas_item: ReverseAtlasItem):
        is_affected = atlas_item.id in self._affected_atlas_ids
        dup_count = 0
        if self._duplicate_result:
            dup_count = len(self._duplicate_result.get_groups_for_atlas(atlas_item.id))
        widget = _ReverseAtlasCardWidget(atlas_item, is_affected, dup_count)
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, atlas_item.id)
        item.setSizeHint(QSize(0, 84))
        self._list.addItem(item)
        self._list.setItemWidget(item, widget)


    def _refresh_cards(self):
        """重建列表卡片以反映重复状态"""
        self._list.setUpdatesEnabled(False)
        self._list.clear()
        for item in self._atlas_items:
            self._add_list_item(item)
        self._list.setUpdatesEnabled(True)
        # 恢复选中
        if self._current_atlas_id:
            for i in range(self._list.count()):
                if self._list.item(i).data(Qt.ItemDataRole.UserRole) == self._current_atlas_id:
                    self._list.setCurrentRow(i)
                    break

    def _update_count(self):
        self._count_label.setText(f"{len(self._atlas_items)} 张")

    def _on_item_selected(self, current, previous):
        if current:
            atlas_id = current.data(Qt.ItemDataRole.UserRole)
            self._current_atlas_id = atlas_id
            self.atlas_selected.emit(atlas_id)

    def _on_clear_all(self):
        if not self._atlas_items:
            return
        ret = QMessageBox.question(
            self, "清空图集",
            f"确定要清空所有 {len(self._atlas_items)} 张图集吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret == QMessageBox.StandardButton.Yes:
            self.clear_all()

    def _on_remove_selected(self):
        """移除所有选中的图集（支持多选）"""
        selected = self._list.selectedItems()
        if not selected:
            return
        remove_ids = set()
        for item in selected:
            atlas_id = item.data(Qt.ItemDataRole.UserRole)
            remove_ids.add(atlas_id)
        self._atlas_items = [a for a in self._atlas_items if a.id not in remove_ids]
        # 从列表中移除（从后往前删避免索引偏移）
        for i in range(self._list.count() - 1, -1, -1):
            item = self._list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) in remove_ids:
                self._list.takeItem(i)
        if self._current_atlas_id in remove_ids:
            self._current_atlas_id = None
        self._update_count()
        self.atlas_list_changed.emit()

    def _on_context_menu(self, pos):
        """右键菜单：打开文件位置 / 移除图集"""
        item = self._list.itemAt(pos)
        if not item:
            return

        selected = self._list.selectedItems()
        count = len(selected)

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {REVERSE_COLOR_BG_CARD};
                border: 1px solid {REVERSE_COLOR_BORDER};
                border-radius: 6px; padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 24px; color: {REVERSE_COLOR_TEXT_PRIMARY};
                border-radius: 4px; margin: 2px;
            }}
            QMenu::item:selected {{
                background-color: #FFF8E8;
                color: {REVERSE_COLOR_PRIMARY};
            }}
            QMenu::separator {{
                height: 1px;
                background: {REVERSE_COLOR_BORDER};
                margin: 4px 8px;
            }}
        """)

        open_loc_action = QAction("在资源管理器中显示", self)
        menu.addAction(open_loc_action)

        menu.addSeparator()

        remove_text = f"移除选中 ({count} 张)" if count > 1 else "移除该图集"
        remove_action = QAction(remove_text, self)
        menu.addAction(remove_action)

        action = menu.exec(self._list.mapToGlobal(pos))
        if action == open_loc_action:
            atlas_id = item.data(Qt.ItemDataRole.UserRole)
            atlas = self.find_atlas(atlas_id)
            if atlas and os.path.exists(atlas.file_path):
                self._open_in_explorer(atlas.file_path)
        elif action == remove_action:
            self._on_remove_selected()

    @staticmethod
    def _open_in_explorer(file_path: str):
        """在资源管理器中打开文件所在目录"""
        file_path = os.path.normpath(file_path)
        if platform.system() == "Windows":
            subprocess.run(["explorer", "/select,", file_path])
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-R", file_path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(file_path)])

    def refresh(self):
        """重建列表"""
        self._list.setUpdatesEnabled(False)
        self._list.clear()
        for item in self._atlas_items:
            self._add_list_item(item)
        self._list.setUpdatesEnabled(True)
        self._update_count()
        if self._current_atlas_id:
            for i in range(self._list.count()):
                if self._list.item(i).data(Qt.ItemDataRole.UserRole) == self._current_atlas_id:
                    self._list.setCurrentRow(i)
                    break


class _ReverseAtlasCardWidget(QWidget):
    """图集卡片组件 - 含重复警告标记"""

    def __init__(
        self,
        atlas_item: ReverseAtlasItem,
        is_affected: bool = False,
        dup_count: int = 0,
        parent=None,
    ):
        super().__init__(parent)
        self._atlas = atlas_item
        self._is_affected = is_affected
        self._dup_count = dup_count
        self._init_ui()

    def _init_ui(self):
        accent_color = "#E74C3C" if self._is_affected else REVERSE_COLOR_BORDER
        card_bg = "#FFF6EE" if self._is_affected else "transparent"

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(2, 2, 2, 2)
        outer_layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("reverseAtlasCard")
        card.setStyleSheet(f"""
            QFrame#reverseAtlasCard {{
                background-color: {card_bg};
                border: 2px solid {accent_color if self._is_affected else 'transparent'};
                border-radius: 8px;
            }}
        """)
        outer_layout.addWidget(card)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        if self._is_affected:
            accent_bar = QFrame()
            accent_bar.setFixedWidth(5)
            accent_bar.setStyleSheet(f"background-color: {accent_color}; border-radius: 2px;")
            layout.addWidget(accent_bar)

        # 缩略图预览
        preview = QLabel()
        preview.setFixedSize(48, 48)
        pixmap = self._make_preview()
        preview.setPixmap(pixmap)
        preview.setStyleSheet(f"""
            border: 2px solid {accent_color if self._is_affected else REVERSE_COLOR_BORDER};
            border-radius: 4px;
            background: transparent;
        """)
        layout.addWidget(preview)

        # 信息区域
        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)

        name_label = QLabel(self._atlas.name)
        name_label.setStyleSheet(f"""
            font-size: 12px; font-weight: 600;
            color: {REVERSE_COLOR_TEXT_PRIMARY};
            background: transparent;
        """)
        name_label.setToolTip(self._atlas.file_path)
        info_layout.addWidget(name_label)

        size_label = QLabel(f"{self._atlas.size_str}")
        size_label.setStyleSheet(f"""
            font-size: 10px;
            color: {REVERSE_COLOR_TEXT_DISABLED};
            background: transparent;
        """)
        info_layout.addWidget(size_label)

        # 第三行：子图区域 + 重复标记
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(4)

        region_label = QLabel(f"{self._atlas.region_count} 个子图区域")
        region_label.setStyleSheet(f"""
            font-size: 10px;
            color: {REVERSE_COLOR_PRIMARY};
            background: transparent;
        """)
        bottom_layout.addWidget(region_label)

        if self._is_affected:
            warn_label = QLabel(f"⚠ {self._dup_count}组重复")
            warn_label.setStyleSheet(f"""
                font-size: 9px; font-weight: 700;
                color: #FFFFFF;
                background-color: {accent_color};
                border-radius: 3px;
                padding: 1px 4px;
            """)
            bottom_layout.addWidget(warn_label)

        bottom_layout.addStretch()
        info_layout.addLayout(bottom_layout)

        layout.addLayout(info_layout, 1)


    def _make_preview(self) -> QPixmap:
        """生成缩略图预览"""
        size = 48
        # 尝试使用图片本身的缩略图
        if self._atlas.thumbnail_path and os.path.exists(self._atlas.thumbnail_path):
            pix = QPixmap(self._atlas.thumbnail_path)
            return pix.scaled(size, size,
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)

        if os.path.exists(self._atlas.file_path):
            thumb = ImageService.generate_thumbnail(self._atlas.file_path, size=size)
            if thumb:
                self._atlas.thumbnail_path = thumb
                return QPixmap(thumb)

        # 占位图
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(QColor(REVERSE_COLOR_BG_PANEL))
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(REVERSE_COLOR_TEXT_DISABLED))
        painter.setFont(QFont("Microsoft YaHei UI", 8))
        painter.drawText(0, 0, size, size, Qt.AlignmentFlag.AlignCenter, "图集")
        painter.end()
        return QPixmap.fromImage(img)
