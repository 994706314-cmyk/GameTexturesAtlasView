"""检查模式 - 底部工具栏"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QFrame, QMenu,
    QProgressBar, QVBoxLayout,
)
from PySide6.QtCore import Signal
from PySide6.QtGui import QAction

from models.duplicate_result import DuplicateResult

from utils.constants import (
    PANEL_BORDER_RADIUS,
    REVERSE_COLOR_PRIMARY,
    REVERSE_COLOR_PRIMARY_HOVER,
    REVERSE_COLOR_PRIMARY_PRESSED,
    REVERSE_COLOR_BG_PANEL,
    REVERSE_COLOR_BG_CARD,
    REVERSE_COLOR_BORDER,
    REVERSE_COLOR_TEXT_PRIMARY,
    REVERSE_COLOR_TEXT_SECONDARY,
    REVERSE_COLOR_TEXT_DISABLED,
)


class ReverseToolbar(QWidget):
    """检查模式 - 底部工具栏"""

    start_analysis = Signal(str)       # mode: "exact" | "fuzzy"
    export_report = Signal(bool)       # detailed: True=详细报告, False=粗略报告

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_mode = "exact"
        self.setFixedHeight(52)
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(0)

        container = QFrame()
        container.setObjectName("reverseToolbarContainer")
        container.setStyleSheet(f"""
            QFrame#reverseToolbarContainer {{
                background-color: {REVERSE_COLOR_BG_CARD};
                border-radius: {PANEL_BORDER_RADIUS}px;
                border: 1px solid {REVERSE_COLOR_BORDER};
            }}
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # 顶部进度条（生成结果时显示）
        self._populate_progress = QProgressBar()
        self._populate_progress.setFixedHeight(3)
        self._populate_progress.setTextVisible(False)
        self._populate_progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: {REVERSE_COLOR_BORDER};
                border: none;
                border-top-left-radius: {PANEL_BORDER_RADIUS}px;
                border-top-right-radius: {PANEL_BORDER_RADIUS}px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }}
            QProgressBar::chunk {{
                background-color: {REVERSE_COLOR_PRIMARY};
                border-top-left-radius: {PANEL_BORDER_RADIUS}px;
                border-top-right-radius: 0px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }}
        """)
        self._populate_progress.hide()
        container_layout.addWidget(self._populate_progress)

        # 内容行
        c_layout = QHBoxLayout()
        c_layout.setContentsMargins(16, 0, 16, 0)
        c_layout.setSpacing(10)

        # 左侧统计信息
        self._stats_label = QLabel("已导入 0 张图集 | 检测到 0 组重复")
        self._stats_label.setStyleSheet(f"""
            color: {REVERSE_COLOR_TEXT_DISABLED};
            font-size: 12px; background: transparent;
        """)
        c_layout.addWidget(self._stats_label)

        c_layout.addStretch()

        # 开始分析按钮
        self._analyze_btn = QPushButton("开始分析")
        self._analyze_btn.setStyleSheet(self._primary_btn_style())
        self._analyze_btn.clicked.connect(self._on_analyze)
        c_layout.addWidget(self._analyze_btn)

        # 导出报告按钮（带下拉菜单）
        self._export_btn = QPushButton("导出报告 ▾")
        self._export_btn.setEnabled(False)
        self._export_btn.setStyleSheet(self._outline_btn_style())
        self._export_btn.clicked.connect(self._show_export_menu)
        c_layout.addWidget(self._export_btn)

        container_layout.addLayout(c_layout)

        layout.addWidget(container)

    def _show_export_menu(self):
        """弹出导出选项菜单"""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {REVERSE_COLOR_BG_CARD};
                border: 1px solid {REVERSE_COLOR_BORDER};
                border-radius: 6px;
                padding: 4px 0;
            }}
            QMenu::item {{
                padding: 8px 20px;
                font-size: 12px;
                color: {REVERSE_COLOR_TEXT_PRIMARY};
            }}
            QMenu::item:selected {{
                background-color: #FFF8E8;
                color: {REVERSE_COLOR_PRIMARY};
            }}
            QMenu::separator {{
                height: 1px;
                background: {REVERSE_COLOR_BORDER};
                margin: 4px 8px;
            }}
        """)

        # 粗略报告
        brief_action = QAction("📊 粗略报告", self)
        brief_action.setToolTip("导出分组概览，含缩略图和重复信息")
        brief_action.triggered.connect(lambda: self.export_report.emit(False))
        menu.addAction(brief_action)

        menu.addSeparator()

        # 详细报告
        detail_action = QAction("🔍 详细报告（含图集标注）", self)
        detail_action.setToolTip("在每张图集上用红框标记重复区域位置，耗时较长")
        detail_action.triggered.connect(lambda: self.export_report.emit(True))
        menu.addAction(detail_action)

        # 提示信息
        menu.addSeparator()
        hint_action = QAction("💡 详细报告需更长时间生成", self)
        hint_action.setEnabled(False)
        menu.addAction(hint_action)

        # 在按钮上方弹出
        pos = self._export_btn.mapToGlobal(self._export_btn.rect().topLeft())
        pos.setY(pos.y() - menu.sizeHint().height())
        menu.exec(pos)

    # ---- 公共接口 ----
    def update_stats(self, atlas_count: int, duplicate_count: int,
                     result: 'DuplicateResult | None' = None):
        """更新统计信息，支持按分辨率分类显示"""
        base_text = f"已导入 {atlas_count} 张图集 | 检测到 {duplicate_count} 组重复"

        if result and result.groups:
            # 按 tier_size 分类统计
            tier_counts = {}
            for group in result.groups:
                ts = group.tier_size
                if ts > 0:
                    tier_counts[ts] = tier_counts.get(ts, 0) + 1

            if tier_counts:
                parts = []
                for ts in sorted(tier_counts.keys(), reverse=True):
                    parts.append(f"{ts}×{ts}: {tier_counts[ts]}组")
                detail = "  (" + ", ".join(parts) + ")"
                base_text += detail

        self._stats_label.setText(base_text)

    def set_analysis_enabled(self, enabled: bool):
        self._analyze_btn.setEnabled(enabled)

    def set_export_enabled(self, enabled: bool):
        self._export_btn.setEnabled(enabled)

    def get_current_mode(self) -> str:
        return self._current_mode

    def set_analyzing(self, analyzing: bool):
        """切换分析中状态"""
        if analyzing:
            self._analyze_btn.setText("分析中...")
            self._analyze_btn.setEnabled(False)
        else:
            self._analyze_btn.setText("开始分析")
            self._analyze_btn.setEnabled(True)

    def set_populate_progress(self, current: int, total: int):
        """更新底部进度条（分批渲染结果卡片时调用）"""
        if total <= 0:
            self._populate_progress.hide()
            return
        self._populate_progress.setMaximum(total)
        self._populate_progress.setValue(current)
        if not self._populate_progress.isVisible():
            self._populate_progress.show()

    def set_populate_finished(self):
        """结果卡片渲染完成，隐藏进度条"""
        self._populate_progress.hide()

    # ---- 导出报告进度 ----
    def set_export_progress(self, current: int, total: int):
        """更新导出报告进度条"""
        if total <= 0:
            self._populate_progress.hide()
            return
        self._populate_progress.setMaximum(total)
        self._populate_progress.setValue(current)
        if not self._populate_progress.isVisible():
            self._populate_progress.show()
        # 导出期间禁用导出按钮
        self._export_btn.setEnabled(False)
        self._export_btn.setText("导出中...")

    def set_export_finished(self):
        """导出报告完成"""
        self._populate_progress.hide()
        self._export_btn.setEnabled(True)
        self._export_btn.setText("导出报告 ▾")

    def set_export_error(self):
        """导出报告失败"""
        self._populate_progress.hide()
        self._export_btn.setEnabled(True)
        self._export_btn.setText("导出报告 ▾")

    # ---- 内部方法 ----
    def _on_analyze(self):
        self.start_analysis.emit(self._current_mode)

    @staticmethod
    def _primary_btn_style() -> str:
        return f"""
            QPushButton {{
                background-color: {REVERSE_COLOR_PRIMARY};
                color: #FFFFFF;
                border: none; border-radius: 6px;
                padding: 6px 20px; font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {REVERSE_COLOR_PRIMARY_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {REVERSE_COLOR_PRIMARY_PRESSED};
            }}
            QPushButton:disabled {{
                background-color: #D0D0CC;
                color: #999999;
            }}
        """

    @staticmethod
    def _outline_btn_style() -> str:
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {REVERSE_COLOR_TEXT_SECONDARY};
                border: 1px solid {REVERSE_COLOR_BORDER};
                border-radius: 6px;
                padding: 6px 16px; font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #FFFDF5;
                color: {REVERSE_COLOR_TEXT_PRIMARY};
                border-color: {REVERSE_COLOR_PRIMARY};
            }}
            QPushButton:pressed {{
                background-color: #F5EDD5;
            }}
            QPushButton:disabled {{
                background-color: transparent;
                color: #CCCCCC;
                border-color: #E0E0DB;
            }}
        """
