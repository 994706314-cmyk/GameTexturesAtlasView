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
    SMOOTH_ANIM_BOUNCE_IN, SMOOTH_ANIM_ELASTIC_SNAP, SMOOTH_ANIM_COLLISION,
    SMOOTH_ANIM_AUTO_LAYOUT, SMOOTH_ANIM_FADE_REMOVE, SMOOTH_ANIM_HOVER,
    SMOOTH_ANIM_BREATHING, SMOOTH_ANIM_UPDATE_INTERVAL,
)


def _apple_ease_out() -> QEasingCurve:
    """Apple 风格 ease-out 贝塞尔曲线 (0.25, 0.1, 0.25, 1.0)
    等同于 CSS cubic-bezier(0.25, 0.1, 0.25, 1.0)"""
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(
        QPointF(0.25, 0.1),
        QPointF(0.25, 1.0),
        QPointF(1.0, 1.0),
    )
    return curve


def _apple_ease_in_out() -> QEasingCurve:
    """Apple 风格 ease-in-out 贝塞尔曲线 (0.42, 0, 0.58, 1.0)
    模拟 iOS 系统级动画过渡"""
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(
        QPointF(0.42, 0.0),
        QPointF(0.58, 1.0),
        QPointF(1.0, 1.0),
    )
    return curve


def _apple_spring() -> QEasingCurve:
    """Apple 风格弹性曲线 (0.175, 0.885, 0.32, 1.275)
    模拟 iOS 的 spring 弹性回弹效果"""
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(
        QPointF(0.175, 0.885),
        QPointF(0.32, 1.275),
        QPointF(1.0, 1.0),
    )
    return curve


def _apple_overshoot() -> QEasingCurve:
    """Apple 风格回弹曲线 (0.34, 1.56, 0.64, 1.0)
    模拟 iOS 弹簧超调效果"""
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(
        QPointF(0.34, 1.56),
        QPointF(0.64, 1.0),
        QPointF(1.0, 1.0),
    )
    return curve


class AnimationEngine:
    """统一动效管理器"""

    def __init__(self):
        self._animations: Dict[str, Dict[str, QAbstractAnimation]] = {}
        self._smooth_mode = False

    def set_smooth_mode(self, enabled: bool):
        """切换流畅模式"""
        self._smooth_mode = enabled

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

    def _configure_smooth(self, anim: QPropertyAnimation):
        """为流畅模式配置高帧率更新间隔"""
        if self._smooth_mode:
            # 降低更新间隔至 ~120fps，让动画更丝滑
            anim.setDuration(anim.duration())  # keep duration
            # Qt 6 内部默认 16ms interval，无法直接设 updateInterval
            # 但通过 QOpenGLWidget viewport + MinimalViewportUpdate 已实现高帧率

    def bounce_in(self, item: QGraphicsObject):
        """弹入动画：scale 0→1"""
        self._stop_existing(item, "scale")
        item.setScale(0.0)

        duration = SMOOTH_ANIM_BOUNCE_IN if self._smooth_mode else ANIM_BOUNCE_IN
        anim = QPropertyAnimation(item, b"scale")
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)

        if self._smooth_mode:
            anim.setEasingCurve(_apple_overshoot())
        else:
            anim.setEasingCurve(QEasingCurve.Type.OutBounce)

        anim.finished.connect(lambda: self._cleanup(item, "scale"))
        self._store(item, "scale", anim)
        anim.start()

    def elastic_snap(self, item: QGraphicsObject, target_pos: QPointF):
        """弹性吸附到目标网格位置"""
        self._stop_existing(item, "pos")

        duration = SMOOTH_ANIM_ELASTIC_SNAP if self._smooth_mode else ANIM_ELASTIC_SNAP
        anim = QPropertyAnimation(item, b"pos")
        anim.setDuration(duration)
        anim.setStartValue(item.pos())
        anim.setEndValue(target_pos)

        if self._smooth_mode:
            anim.setEasingCurve(_apple_spring())
        else:
            anim.setEasingCurve(QEasingCurve.Type.OutElastic)

        anim.finished.connect(lambda: self._cleanup(item, "pos"))
        self._store(item, "pos", anim)
        anim.start()

    def collision_reject(self, item: QGraphicsObject, original_pos: QPointF):
        """碰撞拒绝：抖动 + 弹回原位"""
        self._stop_existing(item, "pos")

        current = item.pos()

        if self._smooth_mode:
            # 流畅模式：更短更丝滑的抖动 + Apple ease-out 回弹
            shake_offset = 4.0
            seq = QSequentialAnimationGroup()

            for i in range(2):
                amplitude = shake_offset * (1.0 - i * 0.35)

                left_anim = QPropertyAnimation(item, b"pos")
                left_anim.setDuration(30)
                left_anim.setStartValue(current)
                left_anim.setEndValue(QPointF(current.x() - amplitude, current.y()))
                left_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
                seq.addAnimation(left_anim)

                right_anim = QPropertyAnimation(item, b"pos")
                right_anim.setDuration(30)
                right_anim.setStartValue(QPointF(current.x() - amplitude, current.y()))
                right_anim.setEndValue(QPointF(current.x() + amplitude, current.y()))
                right_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
                seq.addAnimation(right_anim)

                center_anim = QPropertyAnimation(item, b"pos")
                center_anim.setDuration(30)
                center_anim.setStartValue(QPointF(current.x() + amplitude, current.y()))
                center_anim.setEndValue(current)
                center_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
                seq.addAnimation(center_anim)

            snap_back = QPropertyAnimation(item, b"pos")
            snap_back.setDuration(SMOOTH_ANIM_COLLISION)
            snap_back.setStartValue(current)
            snap_back.setEndValue(original_pos)
            snap_back.setEasingCurve(_apple_ease_out())
            seq.addAnimation(snap_back)
        else:
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

        duration = SMOOTH_ANIM_AUTO_LAYOUT if self._smooth_mode else ANIM_AUTO_LAYOUT
        curve = _apple_ease_in_out() if self._smooth_mode else QEasingCurve(QEasingCurve.Type.InOutCubic)

        for item, target_pos in moves.items():
            anim = QPropertyAnimation(item, b"pos")
            anim.setDuration(duration)
            anim.setStartValue(item.pos())
            anim.setEndValue(target_pos)
            anim.setEasingCurve(curve)
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

        duration = SMOOTH_ANIM_FADE_REMOVE if self._smooth_mode else ANIM_FADE_REMOVE
        curve = _apple_ease_in_out() if self._smooth_mode else QEasingCurve(QEasingCurve.Type.InQuad)

        opacity_anim = QPropertyAnimation(item, b"opacity")
        opacity_anim.setDuration(duration)
        opacity_anim.setStartValue(1.0)
        opacity_anim.setEndValue(0.0)
        opacity_anim.setEasingCurve(curve)
        group.addAnimation(opacity_anim)

        scale_anim = QPropertyAnimation(item, b"scale")
        scale_anim.setDuration(duration)
        scale_anim.setStartValue(1.0)
        scale_anim.setEndValue(0.3)
        scale_anim.setEasingCurve(curve)
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

        duration = SMOOTH_ANIM_HOVER if self._smooth_mode else ANIM_HOVER
        target = QPointF(item.pos().x(), item.pos().y() - 2)
        anim = QPropertyAnimation(item, b"pos")
        anim.setDuration(duration)
        anim.setStartValue(item.pos())
        anim.setEndValue(target)

        if self._smooth_mode:
            anim.setEasingCurve(_apple_ease_out())
        else:
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        anim.finished.connect(lambda: self._cleanup(item, "hover"))
        self._store(item, "hover", anim)
        anim.start()

    def hover_drop(self, item: QGraphicsObject, rest_pos: QPointF):
        """悬停恢复"""
        self._stop_existing(item, "hover")

        duration = SMOOTH_ANIM_HOVER if self._smooth_mode else ANIM_HOVER
        anim = QPropertyAnimation(item, b"pos")
        anim.setDuration(duration)
        anim.setStartValue(item.pos())
        anim.setEndValue(rest_pos)

        if self._smooth_mode:
            anim.setEasingCurve(_apple_ease_out())
        else:
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        anim.finished.connect(lambda: self._cleanup(item, "hover"))
        self._store(item, "hover", anim)
        anim.start()

    def breathing_glow(self, item: QGraphicsObject):
        """选中呼吸发光：glow_opacity 循环动画"""
        self._stop_existing(item, "glow")

        if not hasattr(item, "glow_opacity"):
            return

        duration = SMOOTH_ANIM_BREATHING if self._smooth_mode else ANIM_BREATHING
        anim = QPropertyAnimation(item, b"glow_opacity")
        anim.setDuration(duration)
        anim.setStartValue(0.3)
        anim.setEndValue(1.0)

        if self._smooth_mode:
            anim.setEasingCurve(_apple_ease_in_out())
        else:
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
