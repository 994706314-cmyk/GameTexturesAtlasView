"""底部工具栏 - 含导出进度条"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QFrame,
    QProgressBar, QMenu,
)
from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtGui import QColor

from utils.constants import COLOR_PRIMARY, PANEL_BORDER_RADIUS


class ToolbarWidget(QWidget):
    """底部工具栏"""

    export_excel_clicked = Signal(bool)  # bool: full_mode (True=完整, False=预览)
    auto_plan_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(0)

        container = QFrame()
        container.setObjectName("toolbarContainer")
        container.setStyleSheet(f"""
            QFrame#toolbarContainer {{
                background-color: #1E1E1E;
                border-radius: {PANEL_BORDER_RADIUS}px;
                border: 1px solid #3C3C3C;
            }}
        """)
        c_layout = QHBoxLayout(container)
        c_layout.setContentsMargins(16, 0, 16, 0)
        c_layout.setSpacing(8)

        self._stats_label = QLabel("合图图集: 0 | 素材: 0")
        self._stats_label.setStyleSheet("color: #888888; font-size: 12px; background: transparent;")
        c_layout.addWidget(self._stats_label)

        # 导出进度条（默认隐藏）
        self._export_progress = QProgressBar()
        self._export_progress.setFixedWidth(200)
        self._export_progress.setFixedHeight(16)
        self._export_progress.setMinimum(0)
        self._export_progress.setMaximum(100)
        self._export_progress.setValue(0)
        self._export_progress.setTextVisible(True)
        self._export_progress.setFormat("%p%")
        self._export_progress.setStyleSheet("""
            QProgressBar {
                background-color: #333333;
                border: 1px solid #555555;
                border-radius: 4px;
                text-align: center;
                font-size: 10px;
                color: #CCCCCC;
            }
            QProgressBar::chunk {
                background-color: #0078D4;
                border-radius: 3px;
            }
        """)
        self._export_progress.setVisible(False)
        c_layout.addWidget(self._export_progress)

        # 导出完成标记（绿色）
        self._export_done_label = QLabel("✓")
        self._export_done_label.setStyleSheet("""
            color: #4CAF50; font-size: 16px; font-weight: bold;
            background: transparent;
        """)
        self._export_done_label.setToolTip("导出完成")
        self._export_done_label.setVisible(False)
        c_layout.addWidget(self._export_done_label)

        c_layout.addStretch()

        # 自动规划按钮
        self._auto_plan_btn = QPushButton("自动规划合图")
        self._auto_plan_btn.setToolTip("根据所有素材的规划尺寸自动创建合图并填充")
        self._auto_plan_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #2D7D46; color: #FFFFFF;
                border: none; border-radius: 6px;
                padding: 6px 16px; font-size: 12px; font-weight: 500;
            }}
            QPushButton:hover {{ background-color: #35914F; }}
            QPushButton:pressed {{ background-color: #246B3A; }}
        """)
        self._auto_plan_btn.clicked.connect(self.auto_plan_clicked)
        c_layout.addWidget(self._auto_plan_btn)

        # 导出 Excel 下拉按钮
        self._export_excel_btn = QPushButton("导出 Excel ▾")
        self._export_excel_btn.setStyleSheet(self._primary_btn_style())
        self._export_excel_btn.clicked.connect(self._show_export_menu)
        c_layout.addWidget(self._export_excel_btn)

        layout.addWidget(container)

    def _show_export_menu(self):
        """显示导出模式选择菜单"""
        menu = QMenu(self)
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

        preview_action = menu.addAction("📊 预览模式（仅缩略图，快速导出）")
        full_action = menu.addAction("📋 完整模式（含原图，生成较慢）")

        action = menu.exec(
            self._export_excel_btn.mapToGlobal(
                self._export_excel_btn.rect().topLeft()
            )
        )
        if action == preview_action:
            self.export_excel_clicked.emit(False)
        elif action == full_action:
            self.export_excel_clicked.emit(True)

    def update_stats(self, atlas_count: int, texture_count: int):
        self._stats_label.setText(f"合图图集: {atlas_count} | 素材: {texture_count}")

    # ---- 导出进度条控制 ----
    def set_export_progress(self, current: int, total: int):
        """更新导出进度条"""
        if not self._export_progress.isVisible():
            self._export_progress.setVisible(True)
            self._export_done_label.setVisible(False)
            self._export_excel_btn.setEnabled(False)

        pct = int(current / max(total, 1) * 100)
        self._export_progress.setValue(pct)

    def set_export_finished(self):
        """导出完成，显示绿标"""
        self._export_progress.setVisible(False)
        self._export_done_label.setVisible(True)
        self._export_excel_btn.setEnabled(True)

        # 3秒后隐藏绿标
        QTimer.singleShot(3000, self._hide_export_done)

    def set_export_error(self):
        """导出失败"""
        self._export_progress.setVisible(False)
        self._export_done_label.setVisible(False)
        self._export_excel_btn.setEnabled(True)

    def _hide_export_done(self):
        self._export_done_label.setVisible(False)

    @staticmethod
    def _outline_btn_style() -> str:
        return """
            QPushButton {
                background-color: transparent;
                color: #CCCCCC;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3C3C3C;
                color: #FFFFFF;
                border-color: #666666;
            }
            QPushButton:pressed {
                background-color: #333333;
            }
        """

    @staticmethod
    def _primary_btn_style() -> str:
        return f"""
            QPushButton {{
                background-color: {COLOR_PRIMARY};
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: #106EBE;
            }}
            QPushButton:pressed {{
                background-color: #005A9E;
            }}
        """
