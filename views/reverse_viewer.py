"""检查模式 - 中间图集预览区

显示图集大图，支持缩放、平移，分析后叠加彩色矩形标注。
"""

import os
from typing import Optional, List, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsRectItem, QGraphicsSimpleTextItem,
    QFrame, QToolButton, QCheckBox,
)
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import (
    QPixmap, QColor, QPen, QBrush, QFont, QWheelEvent,
    QPainter, QTransform,
)

from models.reverse_atlas_item import ReverseAtlasItem, SubRegion
from models.duplicate_result import DuplicateResult, DuplicateGroup
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
)


class ReverseViewer(QWidget):
    """检查模式 - 中间预览面板"""

    # 用户点击了标记矩形时发出：(group_id)
    mark_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_atlas: Optional[ReverseAtlasItem] = None
        self._duplicate_result: Optional[DuplicateResult] = None
        self._show_marks = True
        self._selected_group_id: Optional[int] = None  # 当前选中的重复组
        self._mark_items: List = []  # QGraphicsRectItem + text items
        self._zoom_level = 1.0
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        container = QFrame()
        container.setObjectName("reverseViewerContainer")
        container.setStyleSheet(f"""
            QFrame#reverseViewerContainer {{
                background-color: {REVERSE_COLOR_BG_CARD};
                border-radius: {PANEL_BORDER_RADIUS}px;
                border: 1px solid {REVERSE_COLOR_BORDER};
            }}
        """)
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(8, 8, 8, 8)
        c_layout.setSpacing(6)

        # 顶部工具条
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self._title_label = QLabel("选择一张图集开始预览")
        self._title_label.setStyleSheet(f"""
            font-size: 13px; font-weight: 500;
            color: {REVERSE_COLOR_TEXT_PRIMARY};
            background: transparent;
        """)
        top_bar.addWidget(self._title_label)
        top_bar.addStretch()

        # 显示/隐藏标记
        self._marks_check = QCheckBox("显示标记")
        self._marks_check.setChecked(True)
        self._marks_check.setStyleSheet(f"""
            QCheckBox {{
                color: {REVERSE_COLOR_TEXT_SECONDARY};
                font-size: 11px;
                background: transparent;
            }}
        """)
        self._marks_check.toggled.connect(self._on_toggle_marks)
        top_bar.addWidget(self._marks_check)

        # 缩放控件
        self._zoom_out_btn = QToolButton()
        self._zoom_out_btn.setText("−")
        self._zoom_out_btn.setFixedSize(24, 24)
        self._zoom_out_btn.setStyleSheet(self._tool_btn_style())
        self._zoom_out_btn.clicked.connect(self._zoom_out)
        top_bar.addWidget(self._zoom_out_btn)

        self._zoom_label = QLabel("100%")
        self._zoom_label.setFixedWidth(40)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_label.setStyleSheet(f"""
            font-size: 11px; color: {REVERSE_COLOR_TEXT_SECONDARY};
            background: transparent;
        """)
        top_bar.addWidget(self._zoom_label)

        self._zoom_in_btn = QToolButton()
        self._zoom_in_btn.setText("+")
        self._zoom_in_btn.setFixedSize(24, 24)
        self._zoom_in_btn.setStyleSheet(self._tool_btn_style())
        self._zoom_in_btn.clicked.connect(self._zoom_in)
        top_bar.addWidget(self._zoom_in_btn)

        self._fit_btn = QToolButton()
        self._fit_btn.setText("适应")
        self._fit_btn.setFixedSize(36, 24)
        self._fit_btn.setStyleSheet(self._tool_btn_style())
        self._fit_btn.clicked.connect(self._fit_view)
        top_bar.addWidget(self._fit_btn)

        c_layout.addLayout(top_bar)

        # GraphicsView 主区域
        self._scene = QGraphicsScene()
        self._view = _ZoomableGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.setStyleSheet(f"""
            QGraphicsView {{
                background-color: {REVERSE_COLOR_BG_BASE};
                border: 1px solid {REVERSE_COLOR_BORDER};
                border-radius: 6px;
            }}
        """)
        self._view.zoom_changed.connect(self._on_zoom_changed)
        self._view.item_clicked.connect(self._on_mark_clicked)
        c_layout.addWidget(self._view, 1)

        # 底部提示
        self._hint_label = QLabel("")
        self._hint_label.setStyleSheet(f"""
            font-size: 10px; color: {REVERSE_COLOR_TEXT_DISABLED};
            background: transparent;
        """)
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_layout.addWidget(self._hint_label)

        layout.addWidget(container)

        # 场景中的图片项
        self._pixmap_item: Optional[QGraphicsPixmapItem] = None

    # ---- 公共接口 ----
    def show_atlas(self, atlas: ReverseAtlasItem):
        """显示一个图集"""
        self._current_atlas = atlas
        self._title_label.setText(f"{atlas.name}  ({atlas.size_str})")
        self._load_image(atlas.file_path)
        self._update_marks()
        self._hint_label.setText(
            f"子图区域: {atlas.region_count} | 滚轮缩放 · 拖拽平移"
        )

    def set_duplicate_result(self, result: Optional[DuplicateResult]):
        """设置分析结果"""
        self._duplicate_result = result
        self._selected_group_id = None
        self._update_marks()

    def highlight_group(self, group_id: int):
        """高亮指定的重复组"""
        self._selected_group_id = group_id
        self._update_marks()

    def focus_region(self, region_id: str):
        """聚焦到指定的重复区域。"""
        if not self._current_atlas or not region_id:
            return

        region = next(
            (item for item in self._current_atlas.sub_regions if item.region_id == region_id),
            None,
        )
        if not region:
            return

        padding = max(32.0, float(max(region.width, region.height)))
        target_rect = QRectF(
            region.x - padding,
            region.y - padding,
            region.width + padding * 2,
            region.height + padding * 2,
        ).intersected(self._scene.sceneRect())
        if target_rect.isEmpty():
            return

        self._view.fitInView(target_rect, Qt.AspectRatioMode.KeepAspectRatio)
        transform = self._view.transform()
        self._zoom_level = transform.m11()
        self._update_zoom_label()
        self._hint_label.setText(
            f"子图区域: {self._current_atlas.region_count} | 已定位到重复区域 ({region.width}×{region.height})"
        )

    def clear(self):

        """清空预览"""
        self._scene.clear()
        self._pixmap_item = None
        self._mark_items.clear()
        self._current_atlas = None
        self._duplicate_result = None
        self._title_label.setText("选择一张图集开始预览")
        self._hint_label.setText("")

    # ---- 内部方法 ----
    def _load_image(self, file_path: str):
        """加载图集图片到场景"""
        self._scene.clear()
        self._pixmap_item = None
        self._mark_items.clear()

        if not os.path.exists(file_path):
            return

        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            return

        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self._fit_view()

    def _update_marks(self):
        """根据分析结果更新标记矩形"""
        # 清除旧标记
        for item in self._mark_items:
            self._scene.removeItem(item)
        self._mark_items.clear()

        if not self._current_atlas or not self._duplicate_result:
            return

        if not self._show_marks:
            return

        atlas_id = self._current_atlas.id

        # 获取该图集涉及的重复组
        groups = self._duplicate_result.get_groups_for_atlas(atlas_id)
        if not groups:
            return

        # 建立 region_id -> SubRegion 映射
        region_map: Dict[str, SubRegion] = {}
        for region in self._current_atlas.sub_regions:
            region_map[region.region_id] = region

        # 绘制标记
        for group in groups:
            color = QColor(group.color)
            is_selected = (self._selected_group_id == group.group_id)

            # 选中组用更粗的边框
            pen_width = 5 if is_selected else 3
            pen = QPen(color, pen_width)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

            brush_color = QColor(color)
            brush_color.setAlpha(50 if is_selected else 25)
            brush = QBrush(brush_color)

            for region_id in group.region_ids:
                if region_id not in region_map:
                    continue
                region = region_map[region_id]

                # 矩形标记
                rect_item = QGraphicsRectItem(
                    region.x, region.y, region.width, region.height
                )
                rect_item.setPen(pen)
                rect_item.setBrush(brush)
                rect_item.setZValue(200 if is_selected else 100)
                rect_item.setData(0, group.group_id)  # 存储 group_id 用于点击识别
                self._scene.addItem(rect_item)
                self._mark_items.append(rect_item)

                # 组编号标签 - 带背景色的标签
                label_text = f" #{group.group_id} "
                text_item = QGraphicsSimpleTextItem(label_text)
                font = QFont("Microsoft YaHei UI", 9, QFont.Weight.Bold)
                text_item.setFont(font)
                text_item.setBrush(QBrush(QColor("#FFFFFF")))
                text_item.setZValue(202 if is_selected else 102)

                # 标签背景矩形
                text_rect = text_item.boundingRect()
                label_y = max(0.0, region.y - text_rect.height() - 2)
                bg_item = QGraphicsRectItem(
                    region.x, label_y,
                    text_rect.width() + 4, text_rect.height() + 2,
                )
                bg_pen = QPen(color, 1)
                bg_item.setPen(bg_pen)
                bg_item.setBrush(QBrush(color))
                bg_item.setZValue(201 if is_selected else 101)
                bg_item.setData(0, group.group_id)
                self._scene.addItem(bg_item)
                self._mark_items.append(bg_item)

                text_item.setPos(region.x + 2, label_y + 1)
                text_item.setData(0, group.group_id)
                self._scene.addItem(text_item)
                self._mark_items.append(text_item)


    def _on_toggle_marks(self, checked: bool):
        self._show_marks = checked
        self._update_marks()

    def _on_mark_clicked(self, group_id: int):
        """用户点击了视口中的标记矩形"""
        self._selected_group_id = group_id
        self._update_marks()
        self.mark_clicked.emit(group_id)

    def _zoom_in(self):
        self._view.scale(1.2, 1.2)
        self._zoom_level *= 1.2
        self._update_zoom_label()

    def _zoom_out(self):
        self._view.scale(1 / 1.2, 1 / 1.2)
        self._zoom_level /= 1.2
        self._update_zoom_label()

    def _fit_view(self):
        if self._pixmap_item:
            self._view.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
            transform = self._view.transform()
            self._zoom_level = transform.m11()
            self._update_zoom_label()

    def _on_zoom_changed(self, factor: float):
        self._zoom_level *= factor
        self._update_zoom_label()

    def _update_zoom_label(self):
        self._zoom_label.setText(f"{int(self._zoom_level * 100)}%")

    @staticmethod
    def _tool_btn_style() -> str:
        return f"""
            QToolButton {{
                background-color: {REVERSE_COLOR_BG_PANEL};
                color: {REVERSE_COLOR_TEXT_SECONDARY};
                border: 1px solid {REVERSE_COLOR_BORDER};
                border-radius: 4px;
                font-size: 14px; font-weight: bold;
            }}
            QToolButton:hover {{
                background-color: {REVERSE_COLOR_PRIMARY};
                color: #FFFFFF;
                border-color: {REVERSE_COLOR_PRIMARY};
            }}
            QToolButton:pressed {{
                background-color: #C08810;
            }}
        """


class _ZoomableGraphicsView(QGraphicsView):
    """支持滚轮缩放和标记点击的 QGraphicsView"""

    zoom_changed = Signal(float)
    item_clicked = Signal(int)  # group_id

    def wheelEvent(self, event: QWheelEvent):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)
        self.zoom_changed.emit(factor)

    def mousePressEvent(self, event):
        """鼠标点击时检查是否点中了标记矩形"""
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            items = self.scene().items(scene_pos)
            for item in items:
                group_id = item.data(0)
                if group_id is not None:
                    self.item_clicked.emit(group_id)
                    break
        super().mousePressEvent(event)
