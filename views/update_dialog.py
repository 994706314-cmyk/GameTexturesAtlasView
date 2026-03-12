"""更新对话框：新版本提示 → 保存确认 → 更新确认 → 下载 → 替换重启

流程：
  1. 检测到新版本后弹出对话框，显示版本信息和更新日志
  2. 用户点击「更新」按钮
  3. 检查项目是否有未保存的修改：
     - 已保存 → 直接进入步骤 4
     - 未保存 → 弹出保存确认（保存 / 不保存 / 取消）
  4. 弹出二次确认「确认更新？」
  5. 开始后台下载新版本 EXE
  6. 下载完成后：关闭当前应用 → 删除旧版本 → 启动新版本
  7. 新版本启动后自动恢复关闭前的项目内容
"""

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

        # 进度条区域（初始隐藏）
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

        self._update_btn = QPushButton("更新")
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
        self._update_btn.clicked.connect(self._on_update_clicked)
        btn_layout.addWidget(self._update_btn)

        layout.addLayout(btn_layout)

    # =========================================================
    #  更新按钮点击 → 保存确认 → 更新确认 → 开始下载
    # =========================================================
    def _on_update_clicked(self):
        """用户点击「更新」按钮后的完整流程"""
        if not self._result.download_url:
            self._progress_widget.setVisible(True)
            self._progress_label.setText("❌ 未找到下载链接，请前往 GitHub 手动下载")
            return

        # 步骤 1: 检查项目保存状态
        save_ok = self._check_and_save_project()
        if save_ok is False:
            # 用户取消了保存，中止更新
            return

        # 步骤 2: 二次确认是否更新
        confirm = QMessageBox.question(
            self, "确认更新",
            f"确认要更新到 V{self._result.latest_version} 吗？\n\n"
            "更新将下载新版本并替换当前程序，\n"
            "完成后会自动重启应用。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        # 步骤 3: 记录更新状态（用于重启后恢复）
        self._save_state_for_restore()

        # 步骤 4: 开始下载
        self._start_download()

    def _get_main_window(self):
        """获取主窗口引用"""
        from views.main_window import MainWindow
        parent = self.parent()
        while parent is not None:
            if isinstance(parent, MainWindow):
                return parent
            parent = parent.parent() if hasattr(parent, 'parent') else None
        return None

    def _check_and_save_project(self):
        """检查项目是否需要保存，返回 True/None 表示可以继续，False 表示取消

        - 项目无修改 → 直接返回 True（不打扰用户）
        - 项目有修改且有路径 → 提示保存确认
        - 项目有修改但无路径 → 提示另存为
        """
        main_win = self._get_main_window()
        if main_win is None:
            return True

        # 项目没有未保存的修改，跳过保存步骤
        if not main_win._project.dirty:
            return True

        project_path = getattr(main_win, '_current_file_path', None)

        if project_path:
            # 有路径，提示是否保存
            ret = QMessageBox.question(
                self, "保存项目",
                "当前项目有未保存的修改。\n\n"
                "是否在更新前保存？",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if ret == QMessageBox.StandardButton.Save:
                main_win._on_save()
                return True
            elif ret == QMessageBox.StandardButton.Discard:
                # 不保存，继续更新
                return True
            else:
                # 取消
                return False
        else:
            # 无路径，提示另存为
            ret = QMessageBox.question(
                self, "保存项目",
                "当前项目有未保存的修改且从未保存过。\n\n"
                "是否先保存项目再更新？\n"
                "· 选择「Save」将弹出保存对话框\n"
                "· 选择「Discard」将丢弃未保存的更改\n"
                "· 选择「Cancel」取消更新",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if ret == QMessageBox.StandardButton.Save:
                saved = main_win._on_save_as()
                if saved:
                    return True
                else:
                    # 用户取消了另存为对话框
                    return False
            elif ret == QMessageBox.StandardButton.Discard:
                return True
            else:
                return False

    def _save_state_for_restore(self):
        """保存更新状态，用于重启后恢复项目"""
        main_win = self._get_main_window()
        project_path = None
        if main_win:
            project_path = getattr(main_win, '_current_file_path', None)
        save_update_state(project_path)

    # =========================================================
    #  下载流程
    # =========================================================
    def _start_download(self):
        """开始后台下载新版本"""
        self._progress_widget.setVisible(True)
        self._progress_label.setText("正在下载...")
        self._progress_bar.setValue(0)

        self._update_btn.setEnabled(False)
        self._later_btn.setText("取消")
        self._later_btn.clicked.disconnect()
        self._later_btn.clicked.connect(self._on_cancel_download)

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
        """下载完成 → 替换 EXE → 重启"""
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

    # =========================================================
    #  重启倒计时
    # =========================================================
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

    # =========================================================
    #  错误处理 & 重启
    # =========================================================
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
        """立即重启应用：先退出当前进程，再通过延迟脚本启动新版本"""
        self._stop_countdown()
        import subprocess
        import sys
        import os
        import tempfile

        exe_path = sys.executable if getattr(sys, 'frozen', False) else None
        if exe_path:
            # 创建延迟启动脚本：等待旧进程退出后再启动新版本
            pid = os.getpid()
            bat_path = os.path.join(
                os.path.dirname(exe_path), "_restart.bat"
            )
            bat_content = (
                "@echo off\n"
                "chcp 65001 >nul 2>&1\n"
                f"echo Waiting for process {pid} to exit...\n"
                ":wait_loop\n"
                f"tasklist /fi \"PID eq {pid}\" 2>nul | find \"{pid}\" >nul\n"
                "if not errorlevel 1 (\n"
                "    timeout /t 1 /nobreak >nul\n"
                "    goto wait_loop\n"
                ")\n"
                "echo Starting new version...\n"
                f"start \"\" \"{exe_path}\"\n"
                # 脚本自删除
                f"del \"{bat_path}\"\n"
            )
            try:
                with open(bat_path, "w", encoding="utf-8") as f:
                    f.write(bat_content)
                # 启动 bat 脚本（隐藏窗口）
                subprocess.Popen(
                    ["cmd", "/c", bat_path],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    close_fds=True,
                )
            except Exception:
                # bat 失败则回退到直接启动
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
