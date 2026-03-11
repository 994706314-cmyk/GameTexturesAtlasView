"""撤销/重做系统"""

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional
from copy import deepcopy

from PySide6.QtCore import QObject, Signal


@dataclass
class UndoAction:
    """单个可撤销操作"""
    description: str
    undo_data: Any
    redo_data: Any


class UndoRedoManager(QObject):
    """撤销/重做管理器"""

    state_changed = Signal()  # 当可撤销/重做状态变化时发出

    def __init__(self, max_steps: int = 100, parent=None):
        super().__init__(parent)
        self._undo_stack: List[UndoAction] = []
        self._redo_stack: List[UndoAction] = []
        self._max_steps = max_steps
        self._snapshot_func: Optional[Callable] = None
        self._restore_func: Optional[Callable] = None

    @property
    def max_steps(self) -> int:
        return self._max_steps

    @max_steps.setter
    def max_steps(self, value: int):
        self._max_steps = max(1, value)
        while len(self._undo_stack) > self._max_steps:
            self._undo_stack.pop(0)
        self.state_changed.emit()

    def set_snapshot_func(self, func: Callable):
        """设置快照函数，用于保存当前状态"""
        self._snapshot_func = func

    def set_restore_func(self, func: Callable):
        """设置恢复函数，用于恢复到某个状态"""
        self._restore_func = func

    def push(self, description: str, before_data: Any, after_data: Any):
        """记录一个操作"""
        action = UndoAction(
            description=description,
            undo_data=before_data,
            redo_data=after_data,
        )
        self._undo_stack.append(action)
        if len(self._undo_stack) > self._max_steps:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self.state_changed.emit()

    def take_snapshot(self, description: str):
        """在操作前调用，保存当前状态快照"""
        if self._snapshot_func:
            return self._snapshot_func()
        return None

    def commit(self, description: str, before_snapshot: Any):
        """在操作后调用，记录操作前后的状态"""
        if self._snapshot_func:
            after_snapshot = self._snapshot_func()
            self.push(description, before_snapshot, after_snapshot)

    def undo(self) -> bool:
        if not self._undo_stack or not self._restore_func:
            return False
        action = self._undo_stack.pop()
        self._redo_stack.append(action)
        self._restore_func(action.undo_data)
        self.state_changed.emit()
        return True

    def redo(self) -> bool:
        if not self._redo_stack or not self._restore_func:
            return False
        action = self._redo_stack.pop()
        self._undo_stack.append(action)
        self._restore_func(action.redo_data)
        self.state_changed.emit()
        return True

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def clear(self):
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.state_changed.emit()

    def undo_description(self) -> str:
        if self._undo_stack:
            return self._undo_stack[-1].description
        return ""

    def redo_description(self) -> str:
        if self._redo_stack:
            return self._redo_stack[-1].description
        return ""
