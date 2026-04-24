"""合图编辑器：中间主操作区域"""

import json
from typing import Optional, Dict, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView, QGraphicsScene,
    QPushButton, QSlider, QLabel, QFrame, QCheckBox, QMessageBox,
)
from PySide6.QtCore import (
    Qt, QRectF, QPointF, Signal, QMimeData, QTimer,
)
from PySide6.QtGui import (
    QPainter, QPen, QColor, QWheelEvent, QDragEnterEvent, QDropEvent,
    QMouseEvent, QBrush, QKeyEvent,
)

from models.atlas_model import AtlasModel
from models.placed_texture import PlacedTexture
from models.project_model import ProjectModel
from models.texture_item import TextureItem
from services.animation_engine import AnimationEngine
from services.bin_packer import MaxRectsBinPacker, PackRect
from utils.constants import (
    GRID_UNIT, DEFAULT_ATLAS_SIZE, COLOR_PRIMARY,
    COLOR_GRID_LINE, COLOR_GRID_MAJOR, PANEL_BORDER_RADIUS,
)
from .texture_graphics_item import TextureGraphicsItem


class AtlasGraphicsScene(QGraphicsScene):
    """合图编辑场景，绘制网格背景"""

    def __init__(self, atlas_size: int = DEFAULT_ATLAS_SIZE, parent=None):
        super().__init__(parent)
        self._atlas_size = atlas_size
        self._show_grid = True
        self._smooth_mode = False
        margin = 200
        self.setSceneRect(-margin, -margin, atlas_size + margin * 2, atlas_size + margin * 2)

    def set_smooth_mode(self, enabled: bool):
        """切换流畅模式"""
        self._smooth_mode = enabled
        self.invalidate(self.sceneRect(), QGraphicsScene.SceneLayer.BackgroundLayer)

    def set_atlas_size(self, size: int):
        self._atlas_size = size
        margin = 200
        self.setSceneRect(-margin, -margin, size + margin * 2, size + margin * 2)
        self.invalidate(self.sceneRect(), QGraphicsScene.SceneLayer.BackgroundLayer)

    def set_show_grid(self, show: bool):
        self._show_grid = show
        self.invalidate(self.sceneRect(), QGraphicsScene.SceneLayer.BackgroundLayer)

    def _get_view_scale(self) -> float:
        """获取当前视图缩放比例"""
        views = self.views()
        if views:
            return views[0].transform().m11()
        return 1.0

    def _draw_grid(self, painter: QPainter, rect: QRectF):
        """根据缩放级别自适应绘制网格（统一逻辑，流畅/标准模式共用）"""
        atlas_rect = QRectF(0, 0, self._atlas_size, self._atlas_size)
        visible = rect.intersected(atlas_rect)
        if visible.isEmpty():
            return

        scale = self._get_view_scale()

        # 根据缩放级别决定显示哪些网格层级
        # 缩放很小时只显示大网格，缩放大时显示细网格
        step_small = GRID_UNIT   # 16px
        step_mid = 64
        step_major = 256

        # 计算屏幕上的像素间距
        screen_px_small = step_small * scale
        screen_px_mid = step_mid * scale
        screen_px_major = step_major * scale

        # 只在屏幕像素间距 >= 3px 时才绘制该层级
        show_minor = screen_px_small >= 4
        show_mid = screen_px_mid >= 4
        show_major = screen_px_major >= 4

        if not show_major:
            return  # 缩放太小，什么都不画

        # Cosmetic pen：线宽以屏幕像素为单位，不受缩放影响
        # 根据缩放自适应线宽
        minor_pen = QPen(QColor(60, 60, 60, 140))
        minor_pen.setWidthF(1.0)
        minor_pen.setCosmetic(True)

        mid_pen = QPen(QColor(85, 85, 85, 200))
        mid_pen.setWidthF(1.0)
        mid_pen.setCosmetic(True)

        major_pen = QPen(QColor(120, 120, 120, 240))
        major_pen.setWidthF(1.5 if scale > 0.15 else 1.0)
        major_pen.setCosmetic(True)

        # 计算可见范围（仅绘制可见区域内的线条）
        # 选取当前最细的可见层级作为步长
        if show_minor:
            step = step_small
        elif show_mid:
            step = step_mid
        else:
            step = step_major

        left = max(0, int(visible.left()) // step * step)
        right = min(self._atlas_size, int(visible.right()) + step)
        top = max(0, int(visible.top()) // step * step)
        bottom = min(self._atlas_size, int(visible.bottom()) + step)

        vt = max(0, int(visible.top()))
        vb = min(self._atlas_size, int(visible.bottom()))
        vl = max(0, int(visible.left()))
        vr = min(self._atlas_size, int(visible.right()))

        # 竖线
        x = left
        while x <= right:
            if x == 0 or x == self._atlas_size:
                x += step
                continue
            if x % step_major == 0 and show_major:
                painter.setPen(major_pen)
            elif x % step_mid == 0 and show_mid:
                painter.setPen(mid_pen)
            elif x % step_small == 0 and show_minor:
                painter.setPen(minor_pen)
            else:
                x += step
                continue
            painter.drawLine(x, vt, x, vb)
            x += step

        # 横线
        y = top
        while y <= bottom:
            if y == 0 or y == self._atlas_size:
                y += step
                continue
            if y % step_major == 0 and show_major:
                painter.setPen(major_pen)
            elif y % step_mid == 0 and show_mid:
                painter.setPen(mid_pen)
            elif y % step_small == 0 and show_minor:
                painter.setPen(minor_pen)
            else:
                y += step
                continue
            painter.drawLine(vl, y, vr, y)
            y += step

    def drawBackground(self, painter: QPainter, rect: QRectF):
        super().drawBackground(painter, rect)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # 外部背景
        full_scene = self.sceneRect()
        painter.fillRect(full_scene, QBrush(QColor(20, 20, 20)))

        atlas_rect = QRectF(0, 0, self._atlas_size, self._atlas_size)

        # 合图区域背景
        painter.fillRect(atlas_rect, QBrush(QColor(30, 30, 30)))

        if self._show_grid:
            self._draw_grid(painter, rect)

        # 合图范围边框 - 始终显示，更明显
        border_pen = QPen(QColor(COLOR_PRIMARY), 3.0, Qt.PenStyle.SolidLine)
        border_pen.setCosmetic(True)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(atlas_rect)


class AtlasEditorView(QWidget):
    """合图编辑器组件"""

    project_changed = Signal()
    before_change = Signal(str)
    after_change = Signal(str)
    atlas_auto_created = Signal(str)  # atlas_id - 自动创建合图时通知外部
    texture_selected_in_editor = Signal(str)  # texture_id - 编辑器中点击贴图时通知外部

    def __init__(self, project: ProjectModel, animation_engine: AnimationEngine, parent=None):
        super().__init__(parent)
        self._project = project
        self._anim = animation_engine
        self._current_atlas: Optional[AtlasModel] = None
        self._items: Dict[str, TextureGraphicsItem] = {}
        self._auto_layout_running = False
        self._show_grid = True
        self._smooth_mode = False

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 外层容器
        container = QFrame()
        container.setObjectName("editorContainer")
        container.setStyleSheet(f"""
            QFrame#editorContainer {{
                background-color: #1E1E1E;
                border-radius: {PANEL_BORDER_RADIUS}px;
                border: 1px solid #3C3C3C;
            }}
        """)
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(0)

        # 顶部工具栏
        toolbar = QFrame()
        toolbar.setFixedHeight(40)
        toolbar.setStyleSheet(f"""
            QFrame {{
                background-color: #252526;
                border-top-left-radius: {PANEL_BORDER_RADIUS}px;
                border-top-right-radius: {PANEL_BORDER_RADIUS}px;
                border-bottom: 1px solid #3C3C3C;
            }}
        """)
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 0, 12, 0)
        tb_layout.setSpacing(8)

        self._atlas_info_label = QLabel("未选择合图")
        self._atlas_info_label.setStyleSheet("color: #888888; font-size: 12px; background: transparent;")
        tb_layout.addWidget(self._atlas_info_label)

        tb_layout.addStretch()

        # 网格开关 - ✓ 复选框
        self._grid_check = QCheckBox("显示网格")
        self._grid_check.setChecked(True)
        self._grid_check.setStyleSheet(self._checkbox_style())
        self._grid_check.toggled.connect(self._on_grid_toggle)
        tb_layout.addWidget(self._grid_check)

        sep0 = QFrame()
        sep0.setFrameShape(QFrame.Shape.VLine)
        sep0.setStyleSheet("color: #3C3C3C; background: transparent;")
        tb_layout.addWidget(sep0)

        zoom_label = QLabel("缩放:")
        zoom_label.setStyleSheet("color: #888888; font-size: 11px; background: transparent;")
        tb_layout.addWidget(zoom_label)

        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setFixedWidth(120)
        self._zoom_slider.setRange(5, 200)
        self._zoom_slider.setValue(30)
        self._zoom_slider.valueChanged.connect(self._on_zoom_changed)
        tb_layout.addWidget(self._zoom_slider)

        self._zoom_value_label = QLabel("30%")
        self._zoom_value_label.setFixedWidth(40)
        self._zoom_value_label.setStyleSheet("color: #CCCCCC; font-size: 11px; background: transparent;")
        tb_layout.addWidget(self._zoom_value_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #3C3C3C; background: transparent;")
        tb_layout.addWidget(sep)

        self._auto_fill_btn = QPushButton("自动整理")
        self._auto_fill_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_PRIMARY}; color: #FFFFFF;
                border: none; border-radius: 6px;
                padding: 4px 14px; font-size: 11px; font-weight: 500;
            }}
            QPushButton:hover {{ background-color: #106EBE; }}
            QPushButton:pressed {{ background-color: #005A9E; }}
            QPushButton:disabled {{ background-color: #3C3C3C; color: #888888; }}
        """)
        self._auto_fill_btn.clicked.connect(self._on_auto_fill)
        tb_layout.addWidget(self._auto_fill_btn)

        self._clear_btn = QPushButton("清空")
        self._clear_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent; color: #CCCCCC;
                border: 1px solid #555555; border-radius: 6px;
                padding: 4px 14px; font-size: 11px;
            }
            QPushButton:hover { background-color: #3C3C3C; color: #FFFFFF; }
            QPushButton:pressed { background-color: #333333; }
        """)
        self._clear_btn.clicked.connect(self._on_clear)
        tb_layout.addWidget(self._clear_btn)

        c_layout.addWidget(toolbar)

        # 编辑器场景和视图
        self._scene = AtlasGraphicsScene()
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self._view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self._view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self._view.setRubberBandSelectionMode(Qt.ItemSelectionMode.IntersectsItemShape)
        self._view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.setStyleSheet("border: none;")
        self._view.setAcceptDrops(True)
        self._view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._view.setInteractive(True)

        self._view.dragEnterEvent = self._drag_enter_event
        self._view.dragMoveEvent = self._drag_move_event
        self._view.dropEvent = self._drop_event
        self._view.wheelEvent = self._wheel_event
        self._view.mousePressEvent = self._view_mouse_press
        self._view.mouseReleaseEvent = self._view_mouse_release
        self._view.mouseMoveEvent = self._view_mouse_move
        self._view.keyPressEvent = self._view_key_press

        self._is_panning = False
        self._pan_start = QPointF()

        c_layout.addWidget(self._view, 1)

        # 右侧删除区
        self._delete_zone = DeleteZoneWidget(self)
        self._delete_zone.texture_dropped.connect(self._on_delete_zone_drop)

        # 编辑器 + 删除区水平布局
        editor_h_layout = QHBoxLayout()
        editor_h_layout.setContentsMargins(0, 0, 0, 0)
        editor_h_layout.setSpacing(0)

        # 用一个容器包裹 view 和删除区
        editor_content = QWidget()
        editor_content_layout = QHBoxLayout(editor_content)
        editor_content_layout.setContentsMargins(0, 0, 0, 0)
        editor_content_layout.setSpacing(0)

        # 将 view 从 c_layout 中移出，放入新的水平布局
        c_layout.removeWidget(self._view)
        editor_content_layout.addWidget(self._view, 1)
        editor_content_layout.addWidget(self._delete_zone)

        c_layout.addWidget(editor_content, 1)

        # 浮动提醒标签
        self._toast_label = QLabel(self._view)
        self._toast_label.setStyleSheet("""
            QLabel {
                background-color: rgba(244, 67, 54, 200);
                color: #FFFFFF;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 500;
            }
        """)
        self._toast_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._toast_label.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._toast_label.hide)

        layout.addWidget(container)

        self._apply_zoom(30)

    @staticmethod
    def _checkbox_style() -> str:
        """统一的 ✓ 复选框样式"""
        import os
        from utils.constants import get_base_dir
        check_svg = os.path.join(
            get_base_dir(), "styles", "check.svg"
        ).replace("\\", "/")
        return f"""
            QCheckBox {{ color: #CCCCCC; font-size: 11px; spacing: 4px; background: transparent; }}
            QCheckBox::indicator {{
                width: 16px; height: 16px; border-radius: 3px;
                border: 1px solid #555555; background-color: #3C3C3C;
            }}
            QCheckBox::indicator:checked {{
                background-color: #0078D4; border-color: #0078D4;
                image: url({check_svg});
            }}
            QCheckBox::indicator:hover {{ border-color: #888888; }}
        """

    def _show_toast(self, msg: str, duration_ms: int = 2000):
        self._toast_label.setText(msg)
        self._toast_label.adjustSize()
        x = (self._view.width() - self._toast_label.width()) // 2
        self._toast_label.move(max(10, x), 10)
        self._toast_label.show()
        self._toast_label.raise_()
        self._toast_timer.start(duration_ms)

    def _on_grid_toggle(self, checked: bool):
        self._show_grid = checked
        self._scene.set_show_grid(checked)

    def set_smooth_mode(self, enabled: bool):
        """切换流畅模式：OpenGL 加速 + 局部重绘 + 场景缓存"""
        self._smooth_mode = enabled
        self._scene.set_smooth_mode(enabled)

        if enabled:
            # OpenGL 硬件加速渲染
            try:
                from PySide6.QtOpenGLWidgets import QOpenGLWidget
                gl_widget = QOpenGLWidget()
                self._view.setViewport(gl_widget)
            except ImportError:
                pass  # 没有 OpenGL 支持则跳过

            # 局部重绘（最大的性能提升）
            self._view.setViewportUpdateMode(
                QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate
            )
            # 关闭抗锯齿的 SmoothPixmapTransform（GPU 渲染下不需要）
            self._view.setRenderHints(QPainter.RenderHint.Antialiasing)
            # 启用场景缓存模式
            self._view.setCacheMode(
                QGraphicsView.CacheModeFlag.CacheBackground
            )
        else:
            # 恢复默认 viewport
            self._view.setViewport(QWidget())
            self._view.setViewportUpdateMode(
                QGraphicsView.ViewportUpdateMode.FullViewportUpdate
            )
            self._view.setRenderHints(
                QPainter.RenderHint.Antialiasing
                | QPainter.RenderHint.SmoothPixmapTransform
            )
            self._view.setCacheMode(
                QGraphicsView.CacheModeFlag(0)
            )

        # 重新绑定 viewport 事件（viewport 替换后旧绑定失效）
        self._view.setAcceptDrops(True)
        self._view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._view.setInteractive(True)

    def set_project(self, project: ProjectModel):
        self._project = project
        self.clear()

    def set_atlas(self, atlas: AtlasModel):
        self._current_atlas = atlas
        self._scene.set_atlas_size(atlas.size)
        self._atlas_info_label.setText(
            f"{atlas.name}  ({atlas.size}x{atlas.size})  "
            f"利用率: {atlas.utilization():.1%}"
        )
        self._rebuild_items()
        self._view.fitInView(
            QRectF(-50, -50, atlas.size + 100, atlas.size + 100),
            Qt.AspectRatioMode.KeepAspectRatio
        )

    def clear(self):
        for item in self._items.values():
            self._anim.stop_all(item)
        self._items.clear()
        self._scene.clear()
        self._current_atlas = None
        self._atlas_info_label.setText("未选择合图")

    def refresh(self):
        if self._current_atlas:
            self._atlas_info_label.setText(
                f"{self._current_atlas.name}  ({self._current_atlas.size}x{self._current_atlas.size})  "
                f"利用率: {self._current_atlas.utilization():.1%}"
            )

    def refresh_items(self):
        """检测并移除已不在合图中的图形项（素材库移除贴图时调用）"""
        self.refresh()
        if not self._current_atlas:
            return
        placed_ids = {pt.texture.id for pt in self._current_atlas.placed_textures}
        stale_ids = [tid for tid in self._items if tid not in placed_ids]
        for tid in stale_ids:
            item = self._items.pop(tid)
            self._anim.stop_all(item)
            self._scene.removeItem(item)
        if stale_ids:
            self._update_info()

    def _rebuild_items(self):
        for item in self._items.values():
            self._anim.stop_all(item)
        self._items.clear()
        self._scene.clear()

        if not self._current_atlas:
            return

        for pt in self._current_atlas.placed_textures:
            self._create_item_for_placed(pt, animate=False)

    def _create_item_for_placed(self, pt: PlacedTexture, animate=True) -> TextureGraphicsItem:
        item = TextureGraphicsItem(
            texture_id=pt.texture.id,
            name=pt.texture.name,
            grid_w=pt.texture.grid_width,
            grid_h=pt.texture.grid_height,
            thumbnail_path=pt.texture.thumbnail_path,
            tag=pt.texture.tag,
            quality_tier=getattr(pt.texture, 'quality_tier', 'None'),
        )
        pixel_pos = QPointF(pt.pixel_x, pt.pixel_y)
        item.setPos(pixel_pos)
        item.rest_pos = pixel_pos

        item.move_attempted.connect(self._on_item_move_attempted)
        item.removed.connect(self._on_item_removed)
        item.batch_removed.connect(self._on_batch_removed)
        item.size_change_requested.connect(self._on_item_size_change)
        item.clicked.connect(self.texture_selected_in_editor.emit)

        self._scene.addItem(item)
        self._items[pt.texture.id] = item

        if animate:
            self._anim.bounce_in(item)

        return item

    # ---- Key press: Delete selected items / F to reset view ----
    def _view_key_press(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Delete:
            selected_items = self._scene.selectedItems()
            if selected_items and self._current_atlas:
                self.before_change.emit("删除选中贴图")
                for gitem in list(selected_items):
                    if isinstance(gitem, TextureGraphicsItem):
                        tid = gitem.texture_id
                        item = self._items.pop(tid, None)
                        if item:
                            self._anim.stop_all(item)
                            self._scene.removeItem(item)
                        self._current_atlas.remove(tid)
                self.project_changed.emit()
                self.after_change.emit("删除选中贴图")
                self._update_info()
        elif event.key() == Qt.Key.Key_F:
            self._fit_view_to_atlas()
        else:
            QGraphicsView.keyPressEvent(self._view, event)

    def _fit_view_to_atlas(self):
        """F键：快速居中重置视图，将合图全部居中显示"""
        if self._current_atlas:
            size = self._current_atlas.size
            self._view.fitInView(
                QRectF(-50, -50, size + 100, size + 100),
                Qt.AspectRatioMode.KeepAspectRatio
            )
            # 同步缩放滑块
            transform = self._view.transform()
            scale_percent = int(transform.m11() * 100)
            scale_percent = max(5, min(200, scale_percent))
            self._zoom_slider.blockSignals(True)
            self._zoom_slider.setValue(scale_percent)
            self._zoom_slider.blockSignals(False)
            self._zoom_value_label.setText(f"{scale_percent}%")
            # 刷新背景缓存
            if self._smooth_mode:
                self._view.resetCachedContent()
                self._scene.invalidate(self._scene.sceneRect(),
                                       QGraphicsScene.SceneLayer.BackgroundLayer)

    # ---- Drop handling ----
    def _drag_enter_event(self, event: QDragEnterEvent):
        if event.mimeData().hasFormat("application/x-texture-items"):
            event.acceptProposedAction()
        elif event.mimeData().hasFormat("application/x-texture-item"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _drag_move_event(self, event):
        if (event.mimeData().hasFormat("application/x-texture-items") or
                event.mimeData().hasFormat("application/x-texture-item")):
            event.acceptProposedAction()

    def _auto_create_atlas(self):
        """自动创建一张合图并设置为当前合图"""
        from models.atlas_model import AtlasModel
        count = len(self._project.atlas_list)
        atlas = AtlasModel(name=f"合图 {count + 1}", size=DEFAULT_ATLAS_SIZE)
        self._project.add_atlas(atlas)
        self._current_atlas = atlas
        self._scene.set_atlas_size(atlas.size)
        self._atlas_info_label.setText(
            f"{atlas.name}  ({atlas.size}x{atlas.size})  "
            f"利用率: {atlas.utilization():.1%}"
        )
        self._view.fitInView(
            QRectF(-50, -50, atlas.size + 100, atlas.size + 100),
            Qt.AspectRatioMode.KeepAspectRatio
        )
        # 通知外部刷新合图列表
        self.atlas_auto_created.emit(atlas.id)
        return atlas

    def _drop_event(self, event: QDropEvent):
        mime = event.mimeData()

        # 检查是否有有效的纹理拖入数据
        has_texture_data = (
            mime.hasFormat("application/x-texture-items") or
            mime.hasFormat("application/x-texture-item")
        )

        # 如果没有合图但有纹理数据，自动创建
        if not self._current_atlas and has_texture_data:
            self._auto_create_atlas()

        if not self._current_atlas:
            event.ignore()
            return

        if mime.hasFormat("application/x-texture-items"):
            try:
                data = json.loads(bytes(mime.data("application/x-texture-items")).decode())
                texture_ids = data.get("texture_ids", [])
            except Exception:
                event.ignore()
                return
            if texture_ids:
                self.before_change.emit("批量拖入贴图")
                self._batch_place_textures(texture_ids)
                self.after_change.emit("批量拖入贴图")
                event.acceptProposedAction()
            return

        if not mime.hasFormat("application/x-texture-item"):
            event.ignore()
            return

        try:
            data = json.loads(bytes(mime.data("application/x-texture-item")).decode())
        except Exception:
            event.ignore()
            return

        texture_id = data.get("texture_id")
        texture = self._project.find_texture(texture_id)
        if not texture:
            event.ignore()
            return

        if texture_id in self._items:
            old_item = self._items.pop(texture_id)
            self._anim.stop_all(old_item)
            self._scene.removeItem(old_item)
            self._current_atlas.remove(texture_id)

        scene_pos = self._view.mapToScene(event.position().toPoint())
        grid_x = max(0, int(scene_pos.x() / GRID_UNIT))
        grid_y = max(0, int(scene_pos.y() / GRID_UNIT))

        gw = texture.grid_width
        gh = texture.grid_height

        # 策略1: 尝试放在拖入的精确位置
        if self._current_atlas.can_place(grid_x, grid_y, gw, gh):
            pt = PlacedTexture(texture=texture, grid_x=grid_x, grid_y=grid_y)
            self.before_change.emit("放置贴图")
            if self._current_atlas.place(pt):
                self._create_item_for_placed(pt, animate=True)
                self.project_changed.emit()
                self.after_change.emit("放置贴图")
                self._update_info()
                event.acceptProposedAction()
                return

        # 策略2: 在附近找最近空位
        pos = self._find_nearest_free(grid_x, grid_y, gw, gh)
        if pos is not None:
            pt = PlacedTexture(texture=texture, grid_x=pos[0], grid_y=pos[1])
            self.before_change.emit("放置贴图")
            if self._current_atlas.place(pt):
                self._create_item_for_placed(pt, animate=True)
                self.project_changed.emit()
                self.after_change.emit("放置贴图")
                self._update_info()
                event.acceptProposedAction()
                return

        # 策略3: 自动整理后尝试放入（利用零碎空间）
        # 先检查面积是否够
        atlas_area = self._current_atlas.size * self._current_atlas.size
        existing_area = sum(
            pt.texture.display_width * pt.texture.display_height
            for pt in self._current_atlas.placed_textures
        )
        new_area = texture.display_width * texture.display_height
        if new_area > atlas_area - existing_area:
            self._show_toast(
                f"空间不足，无法放置 {texture.name} "
                f"({texture.display_width}x{texture.display_height})"
            )
            event.ignore()
            return

        # 面积够但碎片化，尝试用 BinPacker 重排所有贴图
        all_rects = []
        for pt in self._current_atlas.placed_textures:
            all_rects.append(PackRect(
                id=pt.texture.id,
                width=pt.texture.display_width,
                height=pt.texture.display_height,
            ))
        all_rects.append(PackRect(
            id=texture.id,
            width=texture.display_width,
            height=texture.display_height,
        ))

        packer = MaxRectsBinPacker(self._current_atlas.size, self._current_atlas.size)
        results = packer.pack(all_rects)
        result_map = {r.id: r for r in results}

        # 检查所有贴图（含新增）是否都能放下
        if texture.id not in result_map:
            self._show_toast(
                f"空间不足，无法放置 {texture.name} "
                f"({texture.display_width}x{texture.display_height})"
            )
            event.ignore()
            return

        for pt in self._current_atlas.placed_textures:
            if pt.texture.id not in result_map:
                self._show_toast(
                    f"空间不足，无法放置 {texture.name} "
                    f"({texture.display_width}x{texture.display_height})"
                )
                event.ignore()
                return

        # 自动整理成功，重新排列所有贴图
        self.before_change.emit("自动整理放置贴图")
        moves = {}
        for pt in list(self._current_atlas.placed_textures):
            r = result_map.get(pt.texture.id)
            if r:
                new_gx = r.x // GRID_UNIT
                new_gy = r.y // GRID_UNIT
                self._current_atlas._mark_grid(pt, False)
                pt.grid_x = new_gx
                pt.grid_y = new_gy
                self._current_atlas._mark_grid(pt, True)

                item = self._items.get(pt.texture.id)
                if item:
                    target = QPointF(r.x, r.y)
                    item.rest_pos = target
                    moves[item] = target

        # 放入新贴图
        r = result_map[texture.id]
        new_pt = PlacedTexture(
            texture=texture,
            grid_x=r.x // GRID_UNIT,
            grid_y=r.y // GRID_UNIT,
        )
        self._current_atlas.place(new_pt)
        self._create_item_for_placed(new_pt, animate=True)

        # 动画移动已有贴图到新位置
        if moves:
            self._auto_layout_running = True
            self._auto_fill_btn.setEnabled(False)

            def _on_done():
                self._auto_layout_running = False
                self._auto_fill_btn.setEnabled(True)

            self._anim.auto_layout_animate(moves, on_finished=_on_done)

        self.project_changed.emit()
        self.after_change.emit("自动整理放置贴图")
        self._update_info()
        self._show_toast("已自动整理空间并放入", 2000)
        event.acceptProposedAction()

    def _batch_place_textures(self, texture_ids: List[str]):
        """批量放置贴图：先检查总空间 → 自动整理放入 → 空间不足则警告"""
        if not self._current_atlas:
            return

        # 1. 收集所有要放入的贴图
        textures_to_place = []
        for tid in texture_ids:
            texture = self._project.find_texture(tid)
            if not texture:
                continue
            textures_to_place.append(texture)

        if not textures_to_place:
            return

        # 2. 计算拖入贴图的总占用面积
        total_new_area = sum(t.display_width * t.display_height for t in textures_to_place)

        # 3. 计算图集剩余空间（总面积 - 已占用面积，排除即将被替换的）
        atlas_area = self._current_atlas.size * self._current_atlas.size
        existing_area = 0
        for pt in self._current_atlas.placed_textures:
            if pt.texture.id not in texture_ids:
                existing_area += pt.texture.display_width * pt.texture.display_height
        remaining_area = atlas_area - existing_area

        # 4. 如果总面积超出剩余空间，直接警告
        if total_new_area > remaining_area:
            count = len(textures_to_place)
            total_mb = total_new_area / 1024  # 以K为单位展示
            remain_mb = remaining_area / 1024
            self._show_toast(
                f"空间不足：{count} 张贴图需要 {total_new_area}px²，"
                f"剩余 {remaining_area}px²", 4000
            )
            return

        # 5. 移除已存在的旧版本（替换场景）
        for texture in textures_to_place:
            if texture.id in self._items:
                old_item = self._items.pop(texture.id)
                self._anim.stop_all(old_item)
                self._scene.removeItem(old_item)
                self._current_atlas.remove(texture.id)

        # 6. 使用 MaxRectsBinPacker 重新排列所有贴图（已有 + 新增）
        all_rects = []
        # 已有的贴图
        for pt in self._current_atlas.placed_textures:
            all_rects.append(PackRect(
                id=pt.texture.id,
                width=pt.texture.display_width,
                height=pt.texture.display_height,
            ))
        # 新增的贴图
        for texture in textures_to_place:
            all_rects.append(PackRect(
                id=texture.id,
                width=texture.display_width,
                height=texture.display_height,
            ))

        packer = MaxRectsBinPacker(self._current_atlas.size, self._current_atlas.size)
        results = packer.pack(all_rects)
        result_map = {r.id: r for r in results}

        # 检查是否所有贴图都被成功放置
        failed_names = [t.name for t in textures_to_place if t.id not in result_map]
        # 也检查已有贴图是否被挤出
        for pt in self._current_atlas.placed_textures:
            if pt.texture.id not in result_map:
                failed_names.append(pt.texture.name)

        if failed_names:
            count = len(failed_names)
            self._show_toast(f"空间不足，{count} 张贴图无法放置", 3000)
            return

        # 7. 重新排列已有贴图
        moves = {}
        for pt in list(self._current_atlas.placed_textures):
            r = result_map.get(pt.texture.id)
            if r:
                new_gx = r.x // GRID_UNIT
                new_gy = r.y // GRID_UNIT
                self._current_atlas._mark_grid(pt, False)
                pt.grid_x = new_gx
                pt.grid_y = new_gy
                self._current_atlas._mark_grid(pt, True)

                item = self._items.get(pt.texture.id)
                if item:
                    target = QPointF(r.x, r.y)
                    item.rest_pos = target
                    moves[item] = target

        # 8. 放入新贴图
        for texture in textures_to_place:
            r = result_map.get(texture.id)
            if r:
                new_gx = r.x // GRID_UNIT
                new_gy = r.y // GRID_UNIT
                pt = PlacedTexture(texture=texture, grid_x=new_gx, grid_y=new_gy)
                self._current_atlas.place(pt)
                self._create_item_for_placed(pt, animate=True)

        # 9. 动画移动已有贴图到新位置
        if moves:
            self._auto_layout_running = True
            self._auto_fill_btn.setEnabled(False)

            def _on_done():
                self._auto_layout_running = False
                self._auto_fill_btn.setEnabled(True)

            self._anim.auto_layout_animate(moves, on_finished=_on_done)

        self.project_changed.emit()
        self._update_info()

    def _find_any_free(self, gw, gh):
        atlas = self._current_atlas
        max_grid = atlas.grid_count
        for gy in range(max_grid - gh + 1):
            for gx in range(max_grid - gw + 1):
                if atlas.can_place(gx, gy, gw, gh):
                    return (gx, gy)
        return None

    def _find_nearest_free(self, gx, gy, gw, gh):
        atlas = self._current_atlas
        max_grid = atlas.grid_count
        for radius in range(0, max_grid):
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    if abs(dx) != radius and abs(dy) != radius:
                        continue
                    nx, ny = gx + dx, gy + dy
                    if 0 <= nx and nx + gw <= max_grid and 0 <= ny and ny + gh <= max_grid:
                        if atlas.can_place(nx, ny, gw, gh):
                            return (nx, ny)
        return None

    # ---- Item move / remove ----
    def _on_item_move_attempted(self, texture_id: str, grid_x: int, grid_y: int, item):
        if not self._current_atlas:
            return

        # 如果自动整理动画正在运行，拖拽操作会中断它，需要强制结束
        if self._auto_layout_running:
            self._anim.force_finish_auto_layout()

        pt = self._current_atlas.find_placed(texture_id)
        if not pt:
            return

        gw = pt.texture.grid_width
        gh = pt.texture.grid_height

        if self._current_atlas.can_place(grid_x, grid_y, gw, gh, exclude_id=texture_id):
            self.before_change.emit("移动贴图")
            self._current_atlas.move(texture_id, grid_x, grid_y)
            target = QPointF(grid_x * GRID_UNIT, grid_y * GRID_UNIT)
            item.rest_pos = target
            self._anim.elastic_snap(item, target)
            self.project_changed.emit()
            self.after_change.emit("移动贴图")
            self._update_info()
        else:
            original = QPointF(pt.pixel_x, pt.pixel_y)
            item.set_colliding(True)
            self._anim.collision_reject(item, original)

            QTimer.singleShot(400, lambda: item.set_colliding(False))

    def _on_item_removed(self, texture_id: str):
        if not self._current_atlas:
            return

        item = self._items.get(texture_id)
        if not item:
            return

        self.before_change.emit("移除贴图")

        def _do_remove():
            self._scene.removeItem(item)
            self._items.pop(texture_id, None)
            self._current_atlas.remove(texture_id)
            self.project_changed.emit()
            self.after_change.emit("移除贴图")
            self._update_info()

        self._anim.fade_remove(item, on_finished=_do_remove)

    def _on_batch_removed(self, texture_ids: list):
        """批量移除选中贴图（右键菜单触发）"""
        if not self._current_atlas or not texture_ids:
            return

        self.before_change.emit("批量移除贴图")

        for tid in texture_ids:
            item = self._items.pop(tid, None)
            if item:
                self._anim.stop_all(item)
                self._scene.removeItem(item)
            self._current_atlas.remove(tid)

        self.project_changed.emit()
        self.after_change.emit("批量移除贴图")
        self._update_info()

    def _on_delete_zone_drop(self, texture_ids: list):
        """删除区拖入处理：从合图中移除贴图"""
        if not self._current_atlas or not texture_ids:
            return

        self.before_change.emit("删除区移除贴图")

        for tid in texture_ids:
            item = self._items.pop(tid, None)
            if item:
                self._anim.stop_all(item)
                self._scene.removeItem(item)
            self._current_atlas.remove(tid)

        self.project_changed.emit()
        self.after_change.emit("删除区移除贴图")
        self._update_info()

    def _on_item_size_change(self, texture_id: str):
        """编辑器中右键修改规划尺寸"""
        if not self._current_atlas:
            return

        tex = self._project.find_texture(texture_id)
        if not tex:
            return

        pt = self._current_atlas.find_placed(texture_id)
        if not pt:
            return

        from .size_edit_dialog import SizeEditDialog
        dlg = SizeEditDialog(
            tex.name, tex.original_size, tex.display_size, self
        )
        if dlg.exec() != SizeEditDialog.DialogCode.Accepted:
            return

        new_size = dlg.get_size()
        if new_size == tex.display_size:
            return

        self.before_change.emit("修改规划尺寸")

        old_gx, old_gy = pt.grid_x, pt.grid_y

        # 从合图中移除旧位置（用旧尺寸清除网格）
        self._current_atlas._mark_grid(pt, False)

        # 同时更新素材库和合图中的 display_size
        # （PlacedTexture.texture 可能是独立副本，两者都需要更新）
        tex.display_size = new_size
        pt.texture.display_size = new_size

        # 检查新尺寸在旧位置是否可以放置
        new_gw = pt.texture.grid_width
        new_gh = pt.texture.grid_height
        if self._current_atlas.can_place(old_gx, old_gy, new_gw, new_gh, exclude_id=texture_id):
            pt.grid_x, pt.grid_y = old_gx, old_gy
        else:
            # 尝试在旧位置附近找到合适位置
            pos = self._find_nearest_free(old_gx, old_gy, new_gw, new_gh)
            if pos is not None:
                pt.grid_x, pt.grid_y = pos
            else:
                # 实在找不到位置，恢复到旧位置并标记
                pt.grid_x, pt.grid_y = old_gx, old_gy
                self._show_toast(f"调整后空间不足，{tex.name} 可能与其他贴图重叠", 3000)

        # 重新标记网格（现在用新尺寸）
        self._current_atlas._mark_grid(pt, True)

        # 更新图形项
        item = self._items.get(texture_id)
        if item:
            item.update_size(new_gw, new_gh, tex.thumbnail_path)
            new_pos = QPointF(pt.pixel_x, pt.pixel_y)
            item.rest_pos = new_pos
            self._anim.elastic_snap(item, new_pos)

        self.project_changed.emit()
        self.after_change.emit("修改规划尺寸")
        self._update_info()

    # ---- Auto fill ----
    def do_auto_fill(self):
        self._on_auto_fill()

    def _on_auto_fill(self):
        if not self._current_atlas or self._auto_layout_running:
            return

        placed = self._current_atlas.placed_textures
        if not placed:
            return

        self._auto_layout_running = True
        self._auto_fill_btn.setEnabled(False)

        self.before_change.emit("自动填充")

        rects = []
        for pt in placed:
            rects.append(PackRect(
                id=pt.texture.id,
                width=pt.texture.display_width,
                height=pt.texture.display_height,
            ))

        packer = MaxRectsBinPacker(self._current_atlas.size, self._current_atlas.size)
        results = packer.pack(rects)

        result_map = {r.id: r for r in results}

        moves = {}
        for pt in placed:
            r = result_map.get(pt.texture.id)
            if r:
                new_gx = r.x // GRID_UNIT
                new_gy = r.y // GRID_UNIT

                self._current_atlas._mark_grid(pt, False)
                pt.grid_x = new_gx
                pt.grid_y = new_gy
                self._current_atlas._mark_grid(pt, True)

                item = self._items.get(pt.texture.id)
                if item:
                    target = QPointF(r.x, r.y)
                    item.rest_pos = target
                    moves[item] = target

        def _on_done():
            self._auto_layout_running = False
            self._auto_fill_btn.setEnabled(True)
            self.project_changed.emit()
            self.after_change.emit("自动填充")
            self._update_info()

        # 如果没有需要移动的 item，直接完成
        if not moves:
            _on_done()
            return

        self._anim.auto_layout_animate(moves, on_finished=_on_done)

    def _on_clear(self):
        if not self._current_atlas:
            return

        if self._current_atlas.placed_textures:
            ret = QMessageBox.warning(
                self, "清空合图",
                f"确定要清空当前合图 \"{self._current_atlas.name}\" 中的所有贴图吗？\n此操作可通过 Ctrl+Z 撤销。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if ret != QMessageBox.StandardButton.Yes:
                return

        self.before_change.emit("清空合图")

        for item in list(self._items.values()):
            self._anim.stop_all(item)
            self._scene.removeItem(item)

        self._items.clear()
        self._current_atlas.placed_textures.clear()
        self._current_atlas._rebuild_grid()
        self.project_changed.emit()
        self.after_change.emit("清空合图")
        self._update_info()

    def _update_info(self):
        if self._current_atlas:
            self._atlas_info_label.setText(
                f"{self._current_atlas.name}  ({self._current_atlas.size}x{self._current_atlas.size})  "
                f"利用率: {self._current_atlas.utilization():.1%}"
            )

    # ---- Zoom / Pan ----
    def _on_zoom_changed(self, value):
        self._apply_zoom(value)

    def _apply_zoom(self, percent):
        scale = percent / 100.0
        self._view.resetTransform()
        self._view.scale(scale, scale)
        self._zoom_value_label.setText(f"{percent}%")
        # 缩放后刷新背景（网格根据缩放自适应）
        if self._smooth_mode:
            self._view.resetCachedContent()
            self._scene.invalidate(self._scene.sceneRect(),
                                   QGraphicsScene.SceneLayer.BackgroundLayer)

    def _wheel_event(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            current = self._zoom_slider.value()
            step = 5 if abs(delta) < 120 else 10
            if delta > 0:
                new_val = min(200, current + step)
            else:
                new_val = max(5, current - step)
            self._zoom_slider.setValue(new_val)
            event.accept()
        else:
            QGraphicsView.wheelEvent(self._view, event)
            # 普通滚轮后也可能改变可视区域，刷新背景
            if self._smooth_mode:
                self._view.resetCachedContent()

    def _view_mouse_press(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._pan_start = event.position()
            self._view.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            QGraphicsView.mousePressEvent(self._view, event)

    def _view_mouse_move(self, event: QMouseEvent):
        if self._is_panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            hs = self._view.horizontalScrollBar()
            vs = self._view.verticalScrollBar()
            hs.setValue(int(hs.value() - delta.x()))
            vs.setValue(int(vs.value() - delta.y()))
            event.accept()
        else:
            # 检测拖拽贴图时是否悬停在删除区上
            selected = [item for item in self._scene.selectedItems()
                        if isinstance(item, TextureGraphicsItem) and item._is_dragging]
            if selected:
                global_pos = self._view.mapToGlobal(event.position().toPoint())
                delete_zone_rect = self._delete_zone.rect()
                delete_zone_global = self._delete_zone.mapToGlobal(delete_zone_rect.topLeft())
                from PySide6.QtCore import QRect
                dz_global_rect = QRect(delete_zone_global, delete_zone_rect.size())
                hovering = dz_global_rect.contains(global_pos)
                if self._delete_zone._hovering != hovering:
                    self._delete_zone._hovering = hovering
                    self._delete_zone.update()

            QGraphicsView.mouseMoveEvent(self._view, event)

    def _view_mouse_release(self, event: QMouseEvent):
        # 重置删除区高亮状态
        if self._delete_zone._hovering:
            self._delete_zone._hovering = False
            self._delete_zone.update()

        if self._is_panning:
            self._is_panning = False
            self._view.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
        else:
            # 检查是否有拖拽中的贴图落在删除区上
            global_pos = self._view.mapToGlobal(event.position().toPoint())
            delete_zone_rect = self._delete_zone.rect()
            delete_zone_global = self._delete_zone.mapToGlobal(delete_zone_rect.topLeft())
            from PySide6.QtCore import QRect
            dz_global_rect = QRect(delete_zone_global, delete_zone_rect.size())

            if dz_global_rect.contains(global_pos):
                # 获取正在拖拽的贴图项
                selected = [item for item in self._scene.selectedItems()
                            if isinstance(item, TextureGraphicsItem)]
                if selected and self._current_atlas:
                    ids = [item.texture_id for item in selected]
                    # 先恢复位置再处理删除
                    for item in selected:
                        item.setPos(item.rest_pos)
                    self._on_delete_zone_drop(ids)
                    event.accept()
                    return

            QGraphicsView.mouseReleaseEvent(self._view, event)


class DeleteZoneWidget(QWidget):
    """编辑器右侧删除区：拖入贴图即可从合图移除"""

    texture_dropped = Signal(list)  # [texture_id, ...]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(48)
        self.setAcceptDrops(True)
        self._hovering = False
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(4, 8, -4, -8)

        if self._hovering:
            # 拖拽悬停时高亮红色
            painter.setPen(QPen(QColor("#F44336"), 2, Qt.PenStyle.SolidLine))
            painter.setBrush(QColor(244, 67, 54, 40))
        else:
            painter.setPen(QPen(QColor(100, 100, 100, 150), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(60, 60, 60, 40))

        painter.drawRoundedRect(rect, 8, 8)

        # 绘制删除图标（垃圾桶）
        icon_color = QColor("#F44336") if self._hovering else QColor(120, 120, 120)
        painter.setPen(QPen(icon_color, 2))
        cx = rect.center().x()
        cy = rect.center().y()

        # 垃圾桶顶盖
        painter.drawLine(int(cx - 8), int(cy - 6), int(cx + 8), int(cy - 6))
        painter.drawLine(int(cx - 3), int(cy - 9), int(cx + 3), int(cy - 9))
        painter.drawLine(int(cx - 3), int(cy - 9), int(cx - 3), int(cy - 6))
        painter.drawLine(int(cx + 3), int(cy - 9), int(cx + 3), int(cy - 6))

        # 垃圾桶桶身
        painter.drawLine(int(cx - 7), int(cy - 6), int(cx - 5), int(cy + 10))
        painter.drawLine(int(cx + 7), int(cy - 6), int(cx + 5), int(cy + 10))
        painter.drawLine(int(cx - 5), int(cy + 10), int(cx + 5), int(cy + 10))

        # 桶身竖线
        painter.drawLine(int(cx), int(cy - 4), int(cx), int(cy + 8))
        painter.drawLine(int(cx - 3), int(cy - 4), int(cx - 3), int(cy + 8))
        painter.drawLine(int(cx + 3), int(cy - 4), int(cx + 3), int(cy + 8))

        painter.end()

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        # 只接受从编辑器场景中拖出的项（通过检测场景相关mime）
        # 或者接受已放置的贴图项
        if (mime.hasFormat("application/x-texture-item") or
                mime.hasFormat("application/x-texture-items") or
                mime.hasFormat("application/x-atlas-texture-ids")):
            self._hovering = True
            self.update()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._hovering = False
        self.update()

    def dropEvent(self, event):
        self._hovering = False
        self.update()

        mime = event.mimeData()
        texture_ids = []

        if mime.hasFormat("application/x-atlas-texture-ids"):
            try:
                import json
                data = json.loads(bytes(mime.data("application/x-atlas-texture-ids")).decode())
                texture_ids = data.get("texture_ids", [])
            except Exception:
                pass
        elif mime.hasFormat("application/x-texture-items"):
            try:
                import json
                data = json.loads(bytes(mime.data("application/x-texture-items")).decode())
                texture_ids = data.get("texture_ids", [])
            except Exception:
                pass
        elif mime.hasFormat("application/x-texture-item"):
            try:
                import json
                data = json.loads(bytes(mime.data("application/x-texture-item")).decode())
                tid = data.get("texture_id")
                if tid:
                    texture_ids = [tid]
            except Exception:
                pass

        if texture_ids:
            self.texture_dropped.emit(texture_ids)
            event.acceptProposedAction()
        else:
            event.ignore()
