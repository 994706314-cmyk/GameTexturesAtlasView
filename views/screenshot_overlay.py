"""截图选区覆盖窗口 - 全屏半透明遮罩 + 自由拖拽选区（支持多屏幕 + DPI缩放）"""

from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, QRect, QPoint, QRectF, Signal
from PySide6.QtGui import (
    QPainter, QColor, QPixmap, QPen, QFont, QCursor, QGuiApplication,
    QImage,
)


class ScreenshotOverlay(QWidget):
    """全屏截图选区窗口（多屏幕 + DPI 感知）

    使用方式：
        overlay = ScreenshotOverlay()
        overlay.screenshot_taken.connect(on_screenshot)
        overlay.start()

    流程：
        1. 对每个屏幕单独截图，拼合到一张完整的物理像素大图
        2. 窗口覆盖整个虚拟桌面（逻辑坐标）
        3. 用户拖拽选区（逻辑坐标）
        4. 裁剪时将逻辑坐标映射到物理像素坐标，确保结果精确
    """

    screenshot_taken = Signal(QPixmap)  # 截图完成，发出裁剪后的 QPixmap
    cancelled = Signal()                # 用户按 ESC 取消

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._full_pixmap: QPixmap = QPixmap()   # 拼合后的全屏截图（物理像素）
        self._display_pixmap: QPixmap = QPixmap()  # 缩放到逻辑尺寸用于绘制
        self._virtual_rect = QRect()              # 虚拟桌面逻辑区域
        self._origin = QPoint()
        self._selection = QRect()
        self._selecting = False
        self._confirmed = False

        # 每个屏幕的信息：(逻辑几何, devicePixelRatio)
        self._screen_infos = []

    def start(self):
        """截取全屏并显示选区窗口"""
        screens = QGuiApplication.screens()
        if not screens:
            self.cancelled.emit()
            return

        # 计算虚拟桌面逻辑区域
        self._virtual_rect = QRect()
        self._screen_infos = []
        for screen in screens:
            geo = screen.geometry()  # 逻辑坐标
            dpr = screen.devicePixelRatio()
            self._virtual_rect = self._virtual_rect.united(geo)
            self._screen_infos.append((geo, dpr))

        vr = self._virtual_rect

        # 使用最大 DPR 来确定物理像素大图的尺寸
        max_dpr = max(dpr for _, dpr in self._screen_infos) if self._screen_infos else 1.0

        # 创建物理像素大图
        phys_w = int(vr.width() * max_dpr)
        phys_h = int(vr.height() * max_dpr)
        full_image = QImage(phys_w, phys_h, QImage.Format.Format_ARGB32)
        full_image.fill(QColor(0, 0, 0))

        # 对每个屏幕单独截图并拼合
        for screen in screens:
            geo = screen.geometry()
            dpr = screen.devicePixelRatio()

            # 每个屏幕截图（返回的 pixmap 是物理像素大小）
            screen_pixmap = screen.grabWindow(0)

            # 计算该屏幕在大图上的物理像素位置
            dst_x = int((geo.x() - vr.x()) * max_dpr)
            dst_y = int((geo.y() - vr.y()) * max_dpr)

            # 绘制到大图
            painter = QPainter(full_image)
            # 将截图缩放到统一 DPR 的物理尺寸
            dst_w = int(geo.width() * max_dpr)
            dst_h = int(geo.height() * max_dpr)
            painter.drawPixmap(
                QRect(dst_x, dst_y, dst_w, dst_h),
                screen_pixmap,
                screen_pixmap.rect(),
            )
            painter.end()

        self._full_pixmap = QPixmap.fromImage(full_image)
        self._max_dpr = max_dpr

        # 创建逻辑尺寸的显示用 pixmap
        self._display_pixmap = self._full_pixmap.scaled(
            vr.width(), vr.height(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        # 设置窗口覆盖整个虚拟桌面（逻辑坐标）
        self.setGeometry(vr)
        # 不用 showFullScreen()，因为它只会全屏到一个显示器
        self.show()
        self.activateWindow()
        self.raise_()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制全屏截图作为背景（逻辑尺寸）
        if not self._display_pixmap.isNull():
            painter.drawPixmap(0, 0, self._display_pixmap)

        # 半透明遮罩
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))

        # 如果有选区，清除选区内的遮罩（显示原图）
        if not self._selection.isNull() and self._selection.isValid():
            sel = self._selection.normalized()

            # 选区内显示原图（去掉遮罩）
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            if not self._display_pixmap.isNull():
                painter.drawPixmap(sel, self._display_pixmap, sel)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # 选区边框
            pen = QPen(QColor(0, 120, 212), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(sel)

            # 尺寸提示（显示实际物理像素尺寸）
            phys_sel = self._logical_to_physical(sel)
            w = phys_sel.width()
            h = phys_sel.height()
            size_text = f"{w} × {h} px"
            font = QFont("Microsoft YaHei UI", 10)
            painter.setFont(font)
            fm = painter.fontMetrics()
            text_w = fm.horizontalAdvance(size_text) + 12
            text_h = fm.height() + 6

            # 提示框位置：选区上方
            tx = sel.left()
            ty = sel.top() - text_h - 4
            if ty < 0:
                ty = sel.bottom() + 4

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 120, 212, 200))
            painter.drawRoundedRect(tx, ty, text_w, text_h, 4, 4)

            painter.setPen(QColor(255, 255, 255))
            painter.drawText(tx, ty, text_w, text_h,
                             Qt.AlignmentFlag.AlignCenter, size_text)

        else:
            # 没有选区时显示提示
            painter.setPen(QColor(255, 255, 255, 200))
            font = QFont("Microsoft YaHei UI", 14)
            painter.setFont(font)
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                "拖拽选择截图区域，松开完成截图\nESC 取消"
            )

        painter.end()

    def _logical_to_physical(self, logical_rect: QRect) -> QRect:
        """将逻辑坐标选区映射到物理像素坐标（用于裁剪）"""
        dpr = getattr(self, '_max_dpr', 1.0)
        return QRect(
            int(logical_rect.x() * dpr),
            int(logical_rect.y() * dpr),
            int(logical_rect.width() * dpr),
            int(logical_rect.height() * dpr),
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._selection = QRect(self._origin, self._origin)
            self._selecting = True
            self.update()

    def mouseMoveEvent(self, event):
        if self._selecting:
            self._selection = QRect(self._origin, event.position().toPoint())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._selecting:
            self._selecting = False
            sel = self._selection.normalized()

            # 选区太小视为无效
            if sel.width() < 5 or sel.height() < 5:
                self._selection = QRect()
                self.update()
                return

            # 将逻辑选区映射到物理像素坐标，从大图中裁剪
            if not self._full_pixmap.isNull():
                phys_sel = self._logical_to_physical(sel)
                # 确保不超出大图边界
                phys_sel = phys_sel.intersected(self._full_pixmap.rect())
                cropped = self._full_pixmap.copy(phys_sel)
                self._confirmed = True
                self.close()
                self.screenshot_taken.emit(cropped)
            else:
                self.close()
                self.cancelled.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._selecting = False
            self._selection = QRect()
            self.close()
            self.cancelled.emit()
