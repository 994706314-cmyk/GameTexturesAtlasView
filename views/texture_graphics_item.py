"""合图编辑器中的贴图图形项"""

import os
from PySide6.QtWidgets import (
    QGraphicsObject, QGraphicsSceneMouseEvent,
    QGraphicsSceneHoverEvent, QMenu, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import (
    Qt, QRectF, QPointF, Property, Signal,
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPixmap, QFont,
    QLinearGradient,
)

from utils.constants import GRID_UNIT, COLOR_PRIMARY, COLOR_COLLISION


class TextureGraphicsItem(QGraphicsObject):
    """编辑器中可拖拽的贴图图形项，支持 QPropertyAnimation"""

    position_changed = Signal(str, int, int)
    removed = Signal(str)
    move_attempted = Signal(str, int, int, object)
    size_change_requested = Signal(str)  # texture_id - 请求修改规划尺寸

    def __init__(self, texture_id: str, name: str,
                 grid_w: int, grid_h: int,
                 thumbnail_path: str = None,
                 parent=None):
        super().__init__(parent)
        self.texture_id = texture_id
        self._name = name
        self._grid_w = grid_w
        self._grid_h = grid_h
        self._pixel_w = grid_w * GRID_UNIT
        self._pixel_h = grid_h * GRID_UNIT

        self._thumbnail = None
        if thumbnail_path and os.path.exists(thumbnail_path):
            self._thumbnail = QPixmap(thumbnail_path)

        self._glow_opacity_val = 0.0
        self._is_colliding = False
        self._drag_start_pos = QPointF()
        self._is_dragging = False
        self._rest_pos = QPointF()

        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsFocusable, True)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setZValue(1)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(8)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

    def boundingRect(self) -> QRectF:
        margin = 4
        return QRectF(-margin, -margin,
                      self._pixel_w + margin * 2,
                      self._pixel_h + margin * 2)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(0, 0, self._pixel_w, self._pixel_h)

        # 绘制贴图内容
        if self._thumbnail:
            thumb_rect = rect
            scaled = self._thumbnail.scaled(
                int(thumb_rect.width()), int(thumb_rect.height()),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(int(thumb_rect.x()), int(thumb_rect.y()), scaled)
        else:
            grad = QLinearGradient(0, 0, 0, self._pixel_h)
            grad.setColorAt(0, QColor(60, 80, 120, 200))
            grad.setColorAt(1, QColor(40, 55, 85, 200))
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(rect)

        # 只画外部边框
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self._is_colliding:
            painter.setPen(QPen(QColor(COLOR_COLLISION), 3))
            painter.drawRect(rect)
        elif self.isSelected():
            glow_color = QColor(COLOR_PRIMARY)
            glow_color.setAlphaF(max(0.6, self._glow_opacity_val))
            painter.setPen(QPen(glow_color, 3))
            painter.drawRect(rect)
        else:
            painter.setPen(QPen(QColor(80, 90, 110, 120), 1))
            painter.drawRect(rect)

        # 文字信息
        min_dim = min(self._pixel_w, self._pixel_h)
        if min_dim >= 32:
            # 顶部名称条
            text_bg_h = min(28, int(self._pixel_h * 0.35))
            text_bg_rect = QRectF(0, 0, self._pixel_w, text_bg_h)
            painter.fillRect(text_bg_rect, QColor(0, 0, 0, 140))

            font_size = max(8, min(13, self._pixel_w // 10))
            font = QFont("Microsoft YaHei UI", font_size)
            font.setFamilies(["Microsoft YaHei UI", "PingFang SC", "Segoe UI"])
            font.setBold(True)

            painter.setPen(QColor(255, 255, 255, 240))
            painter.setFont(font)
            name_rect = QRectF(4, 1, self._pixel_w - 8, text_bg_h)
            painter.drawText(name_rect,
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             self._truncate_name(self._name, self._pixel_w // 7))

            # 底部尺寸标签
            size_bg_h = min(22, int(self._pixel_h * 0.25))
            size_bg_rect = QRectF(0, self._pixel_h - size_bg_h, self._pixel_w, size_bg_h)
            painter.fillRect(size_bg_rect, QColor(0, 0, 0, 140))

            size_text = f"{self._pixel_w}x{self._pixel_h}"
            size_font_size = max(7, min(11, self._pixel_w // 12))
            size_font = QFont("Microsoft YaHei UI", size_font_size)
            size_font.setFamilies(["Microsoft YaHei UI", "PingFang SC", "Segoe UI"])
            painter.setFont(size_font)
            painter.setPen(QColor(200, 220, 255, 220))
            size_rect = QRectF(4, self._pixel_h - size_bg_h, self._pixel_w - 8, size_bg_h)
            painter.drawText(size_rect,
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             size_text)

    def _truncate_name(self, name: str, max_chars: int) -> str:
        if len(name) <= max_chars:
            return name
        return name[:max(1, max_chars - 2)] + ".."

    # ---- Q Properties for animation ----
    def _get_glow_opacity(self) -> float:
        return self._glow_opacity_val

    def _set_glow_opacity(self, val: float):
        self._glow_opacity_val = val
        self.update()

    glow_opacity = Property(float, _get_glow_opacity, _set_glow_opacity)

    @property
    def rest_pos(self) -> QPointF:
        return self._rest_pos

    @rest_pos.setter
    def rest_pos(self, pos: QPointF):
        self._rest_pos = pos

    def set_colliding(self, colliding: bool):
        self._is_colliding = colliding
        self.update()

    def update_size(self, grid_w: int, grid_h: int, thumbnail_path: str = None):
        """动态更新图形项的尺寸"""
        self.prepareGeometryChange()
        self._grid_w = grid_w
        self._grid_h = grid_h
        self._pixel_w = grid_w * GRID_UNIT
        self._pixel_h = grid_h * GRID_UNIT
        if thumbnail_path and os.path.exists(thumbnail_path):
            self._thumbnail = QPixmap(thumbnail_path)
        self.update()

    # ---- Mouse events ----
    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._drag_start_pos = self.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.setZValue(100)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self._is_dragging:
            new_pos = self.mapToScene(event.pos()) - self.boundingRect().center()
            self.setPos(new_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.setZValue(1)

            scene_pos = self.pos()
            grid_x = max(0, round(scene_pos.x() / GRID_UNIT))
            grid_y = max(0, round(scene_pos.y() / GRID_UNIT))

            self.move_attempted.emit(self.texture_id, grid_x, grid_y, self)
        super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent):
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            effect.setBlurRadius(16)
            effect.setColor(QColor(0, 0, 0, 160))
            effect.setOffset(0, 4)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent):
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            effect.setBlurRadius(8)
            effect.setColor(QColor(0, 0, 0, 100))
            effect.setOffset(0, 2)
        super().hoverLeaveEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
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
        size_action = menu.addAction(f"修改规划尺寸 ({self._pixel_w}x{self._pixel_h})")
        menu.addSeparator()
        remove_action = menu.addAction("从合图中移除")
        action = menu.exec(event.screenPos())
        if action == remove_action:
            self.removed.emit(self.texture_id)
        elif action == size_action:
            self.size_change_requested.emit(self.texture_id)
