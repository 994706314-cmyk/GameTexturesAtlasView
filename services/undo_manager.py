"""撤销/重做管理器"""

import copy
import json
from typing import Optional, Callable
from PySide6.QtCore import QObject, Signal

from utils.constants import DEFAULT_UNDO_STEPS


class UndoManager(QObject):
    """基于项目快照的撤销/重做管理器"""

    state_changed = Signal()  # 当 undo/redo 可用性变化时

    def __init__(self, max_steps: int = DEFAULT_UNDO_STEPS, parent=None):
        super().__init__(parent)
        self._max_steps = max_steps
        self._undo_stack = []  # list of (description, snapshot_dict)
        self._redo_stack = []
        self._current_snapshot = None

    @property
    def max_steps(self) -> int:
        return self._max_steps

    @max_steps.setter
    def max_steps(self, value: int):
        self._max_steps = max(1, value)
        while len(self._undo_stack) > self._max_steps:
            self._undo_stack.pop(0)

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def set_initial_state(self, snapshot: dict):
        """设置初始快照（清空所有历史）"""
        self._current_snapshot = copy.deepcopy(snapshot)
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.state_changed.emit()

    def push(self, description: str, new_snapshot: dict):
        """在操作完成后推入新快照"""
        if self._current_snapshot is not None:
            self._undo_stack.append((description, self._current_snapshot))
            if len(self._undo_stack) > self._max_steps:
                self._undo_stack.pop(0)
        self._current_snapshot = copy.deepcopy(new_snapshot)
        self._redo_stack.clear()
        self.state_changed.emit()

    def undo(self) -> Optional[dict]:
        """撤销，返回要恢复到的快照"""
        if not self._undo_stack:
            return None
        desc, snapshot = self._undo_stack.pop()
        if self._current_snapshot is not None:
            self._redo_stack.append((desc, self._current_snapshot))
        self._current_snapshot = snapshot
        self.state_changed.emit()
        return copy.deepcopy(snapshot)

    def redo(self) -> Optional[dict]:
        """重做，返回要恢复到的快照"""
        if not self._redo_stack:
            return None
        desc, snapshot = self._redo_stack.pop()
        if self._current_snapshot is not None:
            self._undo_stack.append((desc, self._current_snapshot))
        self._current_snapshot = snapshot
        self.state_changed.emit()
        return copy.deepcopy(snapshot)

    def clear(self):
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._current_snapshot = None
        self.state_changed.emit()
