"""更新对话框：新版本提示 + 下载进度 + 自动保存/重启/恢复"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextEdit, QWidget, QMessageBox,
)
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont

from services.update_service import (
    UpdateDownloader, apply_update, UpdateCheckResult,
    save_update_state,
)
from utils.constants import COLOR_PRIMARY, APP_VERSION


class UpdateDialog(QDialog):
    """检查到新版本后弹出的更新对话框"""

    update_applied = Signal()  # 更新完成信号

    def __init__(self, check_result: UpdateCheckResult, parent=None):
        super().__init__(parent)
        self._result = check_result
        self._downloader = None
        self._download_thread = None
        self._countdown = 5
        self._countdown_timer = None

        self.setWindowTitle("发现新版本")
        self.setFixedSize(520, 420)
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        # 标题
        title = QLabel(f"🎉 新版本 V{self._result.latest_version} 可用！")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding-bottom: 4px;")
        layout.addWidget(title)

        # 当前版本 → 新版本
        version_label = QLabel(f"当前版本: V{APP_VERSION}  →  新版本: V{self._result.latest_version}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("font-size: 12px; color: #999999;")
        layout.addWidget(version_label)

        # 更新日志
        if self._result.release_notes:
            notes_label = QLabel("📋 更新内容：")
            notes_label.setStyleSheet("font-size: 12px; font-weight: 500; padding-top: 8px;")
            layout.addWidget(notes_label)

            notes_text = QTextEdit()
            notes_text.setPlainText(self._result.release_notes)
            notes_text.setReadOnly(True)
            notes_text.setStyleSheet("""
                QTextEdit {
                    font-size: 11px;
                    line-height: 1.5;
                    border: 1px solid #3C3C3C;
                    border-radius: 6px;
                    padding: 8px;
                }
            """)
            layout.addWidget(notes_text, 1)

        # 进度条（初始隐藏）
        self._progress_widget = QWidget()
        p_layout = QVBoxLayout(self._progress_widget)
        p_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.setSpacing(4)

        self._progress_label = QLabel("准备下载...")
        self._progress_label.setStyleSheet("font-size: 11px;")
        p_layout.addWidget(self._progress_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid #3C3C3C;
                border-radius: 4px;
                text-align: center;
                height: 20px;
                font-size: 10px;
            }}
            QProgressBar::chunk {{
                background-color: {COLOR_PRIMARY};
                border-radius: 3px;
            }}
        """)
        p_layout.addWidget(self._progress_bar)

        self._progress_widget.setVisible(False)
        layout.addWidget(self._progress_widget)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._later_btn = QPushButton("稍后再说")
        self._later_btn.setFixedWidth(100)
        self._later_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._later_btn)

        self._update_btn = QPushButton("立即更新")
        self._update_btn.setFixedWidth(100)
        self._update_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_PRIMARY}; color: #FFFFFF;
                border: none; border-radius: 6px;
                padding: 6px 16px; font-weight: 500;
            }}
            QPushButton:hover {{ background-color: #106EBE; }}
            QPushButton:disabled {{ background-color: #555555; }}
        """)
        self._update_btn.clicked.connect(self._on_start_download)
        btn_layout.addWidget(self._update_btn)

        layout.addLayout(btn_layout)

    def _get_main_window(self):
        """获取主窗口引用"""
        from views.main_window import MainWindow
        parent = self.parent()
        while parent is not None:
            if isinstance(parent, MainWindow):
                return parent
            parent = parent.parent() if hasattr(parent, 'parent') else None
        return None

    def _auto_save_before_update(self):
        """更新前自动保存当前项目，并记录项目路径用于重启后恢复"""
        main_win = self._get_main_window()
        if main_win is None:
            save_update_state(None)
            return

        project_path = getattr(main_win, '_current_file_path', None)

        # 如果项目有未保存的更改
        if main_win._project.dirty:
            if project_path:
                # 有文件路径，直接保存
                main_win._on_save()
                self._progress_label.setText("已自动保存项目...")
            else:
                # 没有文件路径，提示用户
                ret = QMessageBox.question(
                    self, "保存项目",
                    "当前项目有未保存的更改。\n是否先保存项目再更新？\n\n"
                    "选择"是"将弹出保存对话框\n"
                    "选择"否"将丢弃未保存的更改",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if ret == QMessageBox.StandardButton.Yes:
                    saved = main_win._on_save_as()
                    if saved:
                        project_path = main_win._current_file_path
                        self._progress_label.setText("项目已保存...")
                    else:
                        return False  # 用户取消了保存
        elif project_path:
            # 项目没有未保存更改，但有路径，直接记录
            pass

        save_update_state(project_path)
        return True

    def _on_start_download(self):
        """开始下载新版本"""
        if not self._result.download_url:
            self._progress_label.setText("❌ 未找到下载链接，请前往 GitHub 手动下载")
            self._progress_widget.setVisible(True)
            return

        # 先自动保存
        self._progress_widget.setVisible(True)
        self._progress_label.setText("正在保存当前项目...")
        result = self._auto_save_before_update()
        if result is False:
            self._progress_label.setText("保存已取消")
            return

        self._update_btn.setEnabled(False)
        self._later_btn.setText("取消")
        self._later_btn.clicked.disconnect()
        self._later_btn.clicked.connect(self._on_cancel_download)
        self._progress_label.setText("正在下载...")

        # 启动后台下载
        self._downloader = UpdateDownloader(self._result.download_url)
        self._download_thread = QThread()
        self._downloader.moveToThread(self._download_thread)

        self._downloader.progress.connect(self._on_download_progress)
        self._downloader.finished.connect(self._on_download_finished)
        self._downloader.error.connect(self._on_download_error)
        self._download_thread.started.connect(self._downloader.run)

        self._download_thread.start()

    def _on_cancel_download(self):
        """取消下载"""
        if self._downloader:
            self._downloader.cancel()
        self._cleanup_download()
        self._stop_countdown()
        self.reject()

    def _on_download_progress(self, downloaded: int, total: int):
        """下载进度回调"""
        if total > 0:
            percent = int(downloaded * 100 / total)
            self._progress_bar.setValue(percent)
            mb_down = downloaded / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self._progress_label.setText(
                f"正在下载... {mb_down:.1f} / {mb_total:.1f} MB ({percent}%)"
            )
        else:
            mb_down = downloaded / (1024 * 1024)
            self._progress_label.setText(f"正在下载... {mb_down:.1f} MB")

    def _on_download_finished(self, temp_path: str):
        """下载完成，执行替换"""
        self._cleanup_download()
        self._progress_label.setText("正在安装更新...")
        self._progress_bar.setValue(100)

        success, message = apply_update(temp_path)
        if success:
            self._progress_label.setText("✅ " + message)
            self._update_btn.setVisible(False)

            # 左侧按钮改为"取消重启"
            self._later_btn.setText("取消重启")
            self._later_btn.clicked.disconnect()
            self._later_btn.clicked.connect(self._cancel_and_close)

            # 新增"立即重启"按钮
            self._restart_btn = QPushButton("立即重启")
            self._restart_btn.setFixedWidth(120)
            self._restart_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #4CAF50; color: #FFFFFF;
                    border: none; border-radius: 6px;
                    padding: 6px 16px; font-weight: 500;
                }}
                QPushButton:hover {{ background-color: #45A049; }}
            """)
            self._restart_btn.clicked.connect(self._on_restart)
            btn_layout = self._later_btn.parent().layout()
            if btn_layout:
                btn_layout.addWidget(self._restart_btn)

            # 启动自动重启倒计时
            self._countdown = 5
            self._update_restart_btn_text()
            self._countdown_timer = QTimer(self)
            self._countdown_timer.setInterval(1000)
            self._countdown_timer.timeout.connect(self._on_countdown_tick)
            self._countdown_timer.start()

            self.update_applied.emit()
        else:
            self._progress_label.setText("❌ " + message)
            self._later_btn.setText("关闭")
            self._later_btn.clicked.disconnect()
            self._later_btn.clicked.connect(self.reject)

    def _update_restart_btn_text(self):
        """更新重启按钮的倒计时文字"""
        if hasattr(self, '_restart_btn'):
            self._restart_btn.setText(f"立即重启 ({self._countdown}s)")

    def _on_countdown_tick(self):
        """倒计时每秒回调"""
        self._countdown -= 1
        if self._countdown <= 0:
            self._stop_countdown()
            self._on_restart()
        else:
            self._update_restart_btn_text()

    def _stop_countdown(self):
        """停止倒计时"""
        if self._countdown_timer:
            self._countdown_timer.stop()
            self._countdown_timer = None

    def _cancel_and_close(self):
        """取消自动重启并关闭"""
        self._stop_countdown()
        self.accept()

    def _on_download_error(self, error_msg: str):
        """下载出错"""
        self._cleanup_download()
        self._progress_label.setText(f"❌ 下载失败: {error_msg}")
        self._update_btn.setEnabled(True)
        self._update_btn.setText("重试")
        self._later_btn.setText("关闭")
        self._later_btn.clicked.disconnect()
        self._later_btn.clicked.connect(self.reject)

    def _on_restart(self):
        """立即重启应用"""
        self._stop_countdown()
        import subprocess
        import sys

        exe_path = sys.executable if getattr(sys, 'frozen', False) else None
        if exe_path:
            subprocess.Popen([exe_path], close_fds=True)
        self.accept()
        from PySide6.QtWidgets import QApplication
        QApplication.instance().quit()

    def _cleanup_download(self):
        """清理下载线程"""
        if self._download_thread:
            self._download_thread.quit()
            self._download_thread.wait(3000)
            self._download_thread.deleteLater()
            self._download_thread = None
        if self._downloader:
            self._downloader.deleteLater()
            self._downloader = None

    def closeEvent(self, event):
        self._stop_countdown()
        self._cleanup_download()
        super().closeEvent(event)
