"""假分辨率设置对话框 — 同时支持改名和标记类型"""

import os

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QFrame, QLineEdit,
)
from PySide6.QtCore import Qt

from utils.constants import VALID_TEXTURE_SIZES


# 标记类型列表
TAG_OPTIONS = [
    ("无标记", ""),
    ("E — 自发光 (Emissive)", "E"),
    ("A — 半透明 (Alpha)", "A"),
    ("M — 遮罩 (Mask)", "M"),
    ("C1 — 自定义1", "C1"),
    ("C2 — 自定义2", "C2"),
    ("C3 — 自定义3", "C3"),
]


class SizeEditDialog(QDialog):
    """设置贴图的假分辨率、名称和标记（仅规划用）"""

    def __init__(self, name: str, original_size: tuple,
                 current_display_size: tuple, parent=None,
                 current_tag: str = "", is_batch: bool = False):
        super().__init__(parent)
        self.setWindowTitle("贴图设置")
        self.setFixedSize(400, 420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._original_size = original_size
        self._current_display_size = current_display_size
        self._result_size = current_display_size
        self._result_name = name  # 改名结果
        self._result_tag = current_tag  # 标记结果
        self._original_name = name
        self._is_batch = is_batch
        self._name_changed = False  # 标识名字是否被修改
        self._tag_changed = False  # 标识标记是否被修改
        self._init_ui(name, original_size, current_display_size, current_tag)

    def _init_ui(self, name, original_size, current_display_size, current_tag):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # ---- 贴图名称 ----
        name_section_label = QLabel("贴图名称")
        name_section_label.setStyleSheet("font-size: 11px; color: #888888;")
        layout.addWidget(name_section_label)

        self._name_edit = QLineEdit(name)
        self._name_edit.setStyleSheet("""
            QLineEdit {
                font-size: 13px; font-weight: 600; color: #FFFFFF;
                background-color: #2D2D30; border: 1px solid #3C3C3C;
                border-radius: 4px; padding: 6px 10px;
            }
            QLineEdit:focus {
                border-color: #0078D4;
            }
        """)
        if self._is_batch:
            self._name_edit.setEnabled(False)
            self._name_edit.setToolTip("批量编辑时不支持改名")
            self._name_edit.setStyleSheet("""
                QLineEdit {
                    font-size: 13px; font-weight: 600; color: #666666;
                    background-color: #252526; border: 1px solid #3C3C3C;
                    border-radius: 4px; padding: 6px 10px;
                }
            """)
        layout.addWidget(self._name_edit)

        orig_label = QLabel(
            f"原始尺寸: {original_size[0]} x {original_size[1]} px"
        )
        orig_label.setStyleSheet("font-size: 11px; color: #888888;")
        layout.addWidget(orig_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #3C3C3C; max-height: 1px;")
        layout.addWidget(sep)

        # ---- 标记类型 ----
        tag_row = QHBoxLayout()
        tag_label = QLabel("标记类型")
        tag_label.setStyleSheet("font-size: 11px; color: #888888;")
        tag_row.addWidget(tag_label)

        self._tag_combo = QComboBox()
        self._tag_combo.setStyleSheet("QComboBox { font-size: 11px; }")
        for label, val in TAG_OPTIONS:
            self._tag_combo.addItem(label, val)
        # 回显当前标记
        idx = 0
        for i, (_, val) in enumerate(TAG_OPTIONS):
            if val == current_tag:
                idx = i
                break
        self._tag_combo.setCurrentIndex(idx)
        tag_row.addWidget(self._tag_combo, 1)
        layout.addLayout(tag_row)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("background-color: #3C3C3C; max-height: 1px;")
        layout.addWidget(sep2)

        # ---- 规划尺寸 ----
        hint = QLabel("设置规划用尺寸（不修改原图，仅用于合图规划）")
        hint.setStyleSheet("font-size: 11px; color: #CCCCCC;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        size_layout = QHBoxLayout()
        size_layout.setSpacing(12)

        w_container = QVBoxLayout()
        w_label = QLabel("宽度")
        w_label.setStyleSheet("font-size: 11px; color: #888888;")
        self._width_combo = QComboBox()
        for s in VALID_TEXTURE_SIZES:
            self._width_combo.addItem(f"{s} px", s)
        idx_w = VALID_TEXTURE_SIZES.index(current_display_size[0]) if current_display_size[0] in VALID_TEXTURE_SIZES else 2
        self._width_combo.setCurrentIndex(idx_w)
        self._width_combo.currentIndexChanged.connect(self._on_width_changed)
        w_container.addWidget(w_label)
        w_container.addWidget(self._width_combo)
        size_layout.addLayout(w_container)

        x_label = QLabel("×")
        x_label.setStyleSheet("font-size: 16px; color: #888888;")
        x_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        x_label.setFixedWidth(20)
        size_layout.addWidget(x_label)

        h_container = QVBoxLayout()
        h_label = QLabel("高度")
        h_label.setStyleSheet("font-size: 11px; color: #888888;")
        self._height_combo = QComboBox()
        # 第一项: 等比
        self._height_combo.addItem("等比", -1)
        for s in VALID_TEXTURE_SIZES:
            self._height_combo.addItem(f"{s} px", s)
        # 默认回显当前实际高度：如果宽高相同则选"等比"，否则选实际高度值
        cur_w, cur_h = current_display_size
        if cur_w == cur_h:
            self._height_combo.setCurrentIndex(0)  # 正方形 → 等比
        elif cur_h in VALID_TEXTURE_SIZES:
            self._height_combo.setCurrentIndex(VALID_TEXTURE_SIZES.index(cur_h) + 1)  # +1 跳过"等比"
        else:
            self._height_combo.setCurrentIndex(0)
        h_container.addWidget(h_label)
        h_container.addWidget(self._height_combo)
        size_layout.addLayout(h_container)

        layout.addLayout(size_layout)

        # 等比提示
        self._ratio_hint = QLabel()
        self._ratio_hint.setStyleSheet("font-size: 10px; color: #4CAF50;")
        layout.addWidget(self._ratio_hint)
        self._update_ratio_hint()

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        confirm_btn = QPushButton("确认")
        confirm_btn.setFixedWidth(80)
        confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078D4; color: #FFFFFF;
                border: none; border-radius: 6px;
                padding: 6px 16px; font-weight: 500;
            }
            QPushButton:hover { background-color: #106EBE; }
            QPushButton:pressed { background-color: #005A9E; }
        """)
        confirm_btn.clicked.connect(self._on_confirm)
        btn_layout.addWidget(confirm_btn)

        layout.addLayout(btn_layout)

        self._height_combo.currentIndexChanged.connect(self._update_ratio_hint)

    def _on_width_changed(self, index):
        self._update_ratio_hint()

    def _update_ratio_hint(self):
        """更新等比提示"""
        if self._height_combo.currentData() == -1:
            w = self._width_combo.currentData()
            h = self._calc_proportional_height(w)
            self._ratio_hint.setText(f"等比缩放高度: {h} px")
            self._ratio_hint.show()
        else:
            self._ratio_hint.hide()

    def _calc_proportional_height(self, new_w: int) -> int:
        """根据宽度等比计算高度，基于当前规划尺寸的宽高比，snap到2的幂"""
        disp_w, disp_h = self._current_display_size
        if disp_w <= 0:
            return new_w
        ratio = disp_h / disp_w
        raw_h = max(VALID_TEXTURE_SIZES[0], int(new_w * ratio))
        # snap to power of 2
        for s in VALID_TEXTURE_SIZES:
            if s >= raw_h:
                return s
        return VALID_TEXTURE_SIZES[-1]

    def _on_confirm(self):
        w = self._width_combo.currentData()
        if self._height_combo.currentData() == -1:
            h = self._calc_proportional_height(w)
        else:
            h = self._height_combo.currentData()
        self._result_size = (w, h)

        # 名称变更检测
        new_name = self._name_edit.text().strip()
        if new_name and new_name != self._original_name:
            self._result_name = new_name
            self._name_changed = True
        else:
            self._result_name = self._original_name
            self._name_changed = False

        # 标记变更检测
        new_tag = self._tag_combo.currentData()
        self._result_tag = new_tag
        self._tag_changed = True  # 总是记录当前值

        self.accept()

    def get_size(self) -> tuple:
        return self._result_size

    def get_name(self) -> str:
        return self._result_name

    def is_name_changed(self) -> bool:
        return self._name_changed

    def get_tag(self) -> str:
        return self._result_tag

    def is_tag_changed(self) -> bool:
        return self._tag_changed
