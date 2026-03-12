"""假分辨率设置对话框"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QFrame, QCheckBox,
)
from PySide6.QtCore import Qt

from utils.constants import VALID_TEXTURE_SIZES


class SizeEditDialog(QDialog):
    """设置贴图的假分辨率（仅规划用）"""

    def __init__(self, name: str, original_size: tuple,
                 current_display_size: tuple, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置假分辨率")
        self.setFixedSize(360, 310)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._original_size = original_size
        self._current_display_size = current_display_size  # 等比缩放基准
        self._result_size = current_display_size
        self._init_ui(name, original_size, current_display_size)

    def _init_ui(self, name, original_size, current_display_size):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel(f"贴图: {name}")
        title.setStyleSheet("font-size: 14px; font-weight: 600; color: #FFFFFF;")
        layout.addWidget(title)

        orig_label = QLabel(
            f"原始尺寸: {original_size[0]} x {original_size[1]} px"
        )
        orig_label.setStyleSheet("font-size: 11px; color: #888888;")
        layout.addWidget(orig_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #3C3C3C; max-height: 1px;")
        layout.addWidget(sep)

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
        self.accept()

    def get_size(self) -> tuple:
        return self._result_size
