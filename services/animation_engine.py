"""动效引擎：统一管理所有贴图交互动画"""

from typing import Dict, Optional, Callable
from PySide6.QtCore import (
    QPropertyAnimation, QEasingCurve, QPointF, QRectF,
    QParallelAnimationGroup, QSequentialAnimationGroup,
    QAbstractAnimation, Property,
)
from PySide6.QtWidgets import QGraphicsObject

from utils.constants import (
    ANIM_BOUNCE_IN, ANIM_ELASTIC_SNAP, ANIM_COLLISION,
    ANIM_AUTO_LAYOUT, ANIM_FADE_REMOVE, ANIM_HOVER, ANIM_BREATHING,
)


class AnimationEngine:
    """统一动效管理器"""

    def __init__(self):
        self._animations: Dict[str, Dict[str, QAbstractAnimation]] = {}

    def _key(self, item) -> str:
        return getattr(item, "texture_id", id(item))

    def _stop_existing(self, item, group: str):
        """停止同一 item 同一组的旧动画"""
        key = self._key(item)
        if key in self._animations and group in self._animations[key]:
            anim = self._animations[key][group]
            if anim.state() == QAbstractAnimation.State.Running:
                anim.stop()
            del self._animations[key][group]

    def _store(self, item, group: str, anim: QAbstractAnimation):
        key = self._key(item)
        if key not in self._animations:
            self._animations[key] = {}
        self._animations[key][group] = anim

    def _cleanup(self, item, group: str):
        key = self._key(item)
        if key in self._animations:
            self._animations[key].pop(group, None)
            if not self._animations[key]:
                del self._animations[key]

    def bounce_in(self, item: QGraphicsObject):
        """弹入动画：scale 0→1 + OutBounce"""
        self._stop_existing(item, "scale")
        item.setScale(0.0)

        anim = QPropertyAnimation(item, b"scale")
        anim.setDuration(ANIM_BOUNCE_IN)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutBounce)
        anim.finished.connect(lambda: self._cleanup(item, "scale"))
        self._store(item, "scale", anim)
        anim.start()

    def elastic_snap(self, item: QGraphicsObject, target_pos: QPointF):
        """弹性吸附到目标网格位置"""
        self._stop_existing(item, "pos")

        anim = QPropertyAnimation(item, b"pos")
        anim.setDuration(ANIM_ELASTIC_SNAP)
        anim.setStartValue(item.pos())
        anim.setEndValue(target_pos)
        anim.setEasingCurve(QEasingCurve.Type.OutElastic)
        anim.finished.connect(lambda: self._cleanup(item, "pos"))
        self._store(item, "pos", anim)
        anim.start()

    def collision_reject(self, item: QGraphicsObject, original_pos: QPointF):
        """碰撞拒绝：抖动 + 弹回原位"""
        self._stop_existing(item, "pos")

        current = item.pos()
        shake_offset = 6.0

        seq = QSequentialAnimationGroup()

        for i in range(3):
            amplitude = shake_offset * (1.0 - i * 0.25)

            left_anim = QPropertyAnimation(item, b"pos")
            left_anim.setDuration(40)
            left_anim.setStartValue(current)
            left_anim.setEndValue(QPointF(current.x() - amplitude, current.y()))
            left_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            seq.addAnimation(left_anim)

            right_anim = QPropertyAnimation(item, b"pos")
            right_anim.setDuration(40)
            right_anim.setStartValue(QPointF(current.x() - amplitude, current.y()))
            right_anim.setEndValue(QPointF(current.x() + amplitude, current.y()))
            right_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            seq.addAnimation(right_anim)

            center_anim = QPropertyAnimation(item, b"pos")
            center_anim.setDuration(40)
            center_anim.setStartValue(QPointF(current.x() + amplitude, current.y()))
            center_anim.setEndValue(current)
            center_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            seq.addAnimation(center_anim)

        snap_back = QPropertyAnimation(item, b"pos")
        snap_back.setDuration(ANIM_COLLISION)
        snap_back.setStartValue(current)
        snap_back.setEndValue(original_pos)
        snap_back.setEasingCurve(QEasingCurve.Type.OutBack)
        seq.addAnimation(snap_back)

        seq.finished.connect(lambda: self._cleanup(item, "pos"))
        self._store(item, "pos", seq)
        seq.start()

    def auto_layout_animate(self, moves: Dict[QGraphicsObject, QPointF],
                            on_finished: Optional[Callable] = None):
        """自动整理批量动画"""
        if not moves:
            if on_finished:
                on_finished()
            return

        for item in moves:
            self._stop_existing(item, "pos")

        group = QParallelAnimationGroup()

        for item, target_pos in moves.items():
            anim = QPropertyAnimation(item, b"pos")
            anim.setDuration(ANIM_AUTO_LAYOUT)
            anim.setStartValue(item.pos())
            anim.setEndValue(target_pos)
            anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
            group.addAnimation(anim)

        def _on_done():
            for item in moves:
                self._cleanup(item, "pos")
            if on_finished:
                on_finished()

        group.finished.connect(_on_done)
        self._store_group("auto_layout", group)
        group.start()

    def fade_remove(self, item: QGraphicsObject, on_finished: Optional[Callable] = None):
        """删除淡出：opacity 1→0 + scale 1→0.3"""
        self._stop_existing(item, "scale")
        self._stop_existing(item, "opacity")

        group = QParallelAnimationGroup()

        opacity_anim = QPropertyAnimation(item, b"opacity")
        opacity_anim.setDuration(ANIM_FADE_REMOVE)
        opacity_anim.setStartValue(1.0)
        opacity_anim.setEndValue(0.0)
        opacity_anim.setEasingCurve(QEasingCurve.Type.InQuad)
        group.addAnimation(opacity_anim)

        scale_anim = QPropertyAnimation(item, b"scale")
        scale_anim.setDuration(ANIM_FADE_REMOVE)
        scale_anim.setStartValue(1.0)
        scale_anim.setEndValue(0.3)
        scale_anim.setEasingCurve(QEasingCurve.Type.InQuad)
        group.addAnimation(scale_anim)

        def _on_done():
            self._cleanup(item, "scale")
            self._cleanup(item, "opacity")
            if on_finished:
                on_finished()

        group.finished.connect(_on_done)
        self._store(item, "scale", group)
        group.start()

    def hover_lift(self, item: QGraphicsObject):
        """悬停上浮"""
        self._stop_existing(item, "hover")

        target = QPointF(item.pos().x(), item.pos().y() - 2)
        anim = QPropertyAnimation(item, b"pos")
        anim.setDuration(ANIM_HOVER)
        anim.setStartValue(item.pos())
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: self._cleanup(item, "hover"))
        self._store(item, "hover", anim)
        anim.start()

    def hover_drop(self, item: QGraphicsObject, rest_pos: QPointF):
        """悬停恢复"""
        self._stop_existing(item, "hover")

        anim = QPropertyAnimation(item, b"pos")
        anim.setDuration(ANIM_HOVER)
        anim.setStartValue(item.pos())
        anim.setEndValue(rest_pos)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: self._cleanup(item, "hover"))
        self._store(item, "hover", anim)
        anim.start()

    def breathing_glow(self, item: QGraphicsObject):
        """选中呼吸发光：glow_opacity 循环动画"""
        self._stop_existing(item, "glow")

        if not hasattr(item, "glow_opacity"):
            return

        anim = QPropertyAnimation(item, b"glow_opacity")
        anim.setDuration(ANIM_BREATHING)
        anim.setStartValue(0.3)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        anim.setLoopCount(-1)

        self._store(item, "glow", anim)
        anim.start()

    def stop_breathing(self, item: QGraphicsObject):
        """停止呼吸动画"""
        self._stop_existing(item, "glow")

    def stop_all(self, item: QGraphicsObject):
        """停止该 item 的所有动画"""
        key = self._key(item)
        if key in self._animations:
            for group, anim in list(self._animations[key].items()):
                if anim.state() == QAbstractAnimation.State.Running:
                    anim.stop()
            del self._animations[key]

    def _store_group(self, name: str, anim: QAbstractAnimation):
        """存储非 item 关联的全局动画组"""
        if "__global__" not in self._animations:
            self._animations["__global__"] = {}
        old = self._animations["__global__"].get(name)
        if old and old.state() == QAbstractAnimation.State.Running:
            old.stop()
        self._animations["__global__"][name] = anim
