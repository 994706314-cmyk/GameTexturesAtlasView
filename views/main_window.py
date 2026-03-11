"""主窗口：菜单栏 + 三栏布局 + 撤销重做 + 快捷键 + 设置 + 检查模式"""

import os
import json
from typing import Optional, List

from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QWidget, QVBoxLayout, QHBoxLayout,
    QMessageBox, QFileDialog, QStackedWidget, QPushButton,
    QApplication, QProgressDialog,
)
from PySide6.QtCore import Qt, QMargins, QSettings, QByteArray, QThread, Signal, QObject
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QShortcut, QScreen

from models.project_model import ProjectModel
from models.atlas_model import AtlasModel
from models.placed_texture import PlacedTexture
from utils.constants import (
    PROJECT_FILE_FILTER, EXCEL_FILE_FILTER, DEFAULT_UNDO_STEPS,
    DEFAULT_SHORTCUTS, SHORTCUT_NAMES, PANEL_BORDER_RADIUS,
    DEFAULT_ATLAS_SIZE, DEFAULT_WIDTH_COMPRESS_MAP, DEFAULT_AUTO_COMPRESS,
    DEFAULT_EXCLUDE_SUFFIXES, DEFAULT_WIDTH_COLOR_MAP,
    DEFAULT_THUMBNAIL_QUALITY,
    DEFAULT_ATLAS_SUFFIX, DEFAULT_FUZZY_THRESHOLD, DEFAULT_MIN_TIER_SIZE,
    REVERSE_COLOR_PRIMARY, REVERSE_COLOR_PRIMARY_HOVER,
    REVERSE_COLOR_PRIMARY_PRESSED,
    REVERSE_FILE_FILTER, REVERSE_FILE_EXTENSION, REVERSE_MODE_VERSION,
    GITHUB_OWNER, GITHUB_REPO, APP_VERSION,
)
from services.animation_engine import AnimationEngine
from services.bin_packer import MaxRectsBinPacker, PackRect
from services.undo_manager import UndoManager

from .toolbar_widget import ToolbarWidget
from .settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    """TexturesAtlasView 主窗口"""

    def __init__(self):
        super().__init__()
        self._project = ProjectModel()
        self._current_file_path: Optional[str] = None
        self._animation_engine = AnimationEngine()
        self._undo_manager = UndoManager(DEFAULT_UNDO_STEPS)

        self._settings = {
            "undo_steps": DEFAULT_UNDO_STEPS,
            "shortcuts": DEFAULT_SHORTCUTS.copy(),
            "auto_compress": DEFAULT_AUTO_COMPRESS,
            "width_compress_map": dict(DEFAULT_WIDTH_COMPRESS_MAP),
            "height_compress_mode": "proportional",
            "height_compress_map": None,
            "exclude_suffixes": list(DEFAULT_EXCLUDE_SUFFIXES),
            "width_color_map": dict(DEFAULT_WIDTH_COLOR_MAP),
            "thumbnail_quality": DEFAULT_THUMBNAIL_QUALITY,
            "atlas_suffix": DEFAULT_ATLAS_SUFFIX,
            "fuzzy_threshold": DEFAULT_FUZZY_THRESHOLD,
            "min_tier_size": DEFAULT_MIN_TIER_SIZE,
        }
        self._shortcuts = {}
        self._current_mode = "plan"  # "plan" 或 "reverse"
        self._analysis_worker = None
        self._global_hotkey = None  # 全局热键服务
        self._reverse_file_path: Optional[str] = None  # 检查模式独立存档路径

        self.setWindowTitle("TexturesAtlasView")
        self.setMinimumSize(1280, 800)
        self.resize(1920, 1080)
        self.setStyleSheet("QMainWindow { background-color: #1A1A1A; }")

        self._init_menu_bar()
        self._init_ui()
        self._restore_user_preferences()
        self._setup_shortcuts()
        self._setup_global_hotkeys()
        self._update_title()
        self._init_undo_state()

        # 用恢复的快捷键更新素材库按钮文字
        screenshot_key = self._settings.get("shortcuts", {}).get("screenshot", "Alt+D")
        self._library_panel.update_screenshot_shortcut_label(screenshot_key)

        # 恢复上次窗口状态（几何尺寸、splitter 比例等）
        self._restore_window_state()

        # 启动时清理上次更新遗留的旧 EXE
        from services.update_service import cleanup_old_exe
        cleanup_old_exe()

        # 延迟 3 秒后静默检查更新（不打扰用户启动流程）
        from PySide6.QtCore import QTimer
        QTimer.singleShot(3000, self._auto_check_update)

    def _init_menu_bar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("文件(&F)")
        self._file_menu = file_menu

        self._new_action = QAction("新建(&N)", self)
        self._new_action.triggered.connect(self._on_new)
        file_menu.addAction(self._new_action)

        self._open_action = QAction("打开(&O)", self)
        self._open_action.triggered.connect(self._on_open)
        file_menu.addAction(self._open_action)

        # 最近打开子菜单
        self._recent_menu = file_menu.addMenu("最近打开(&R)")
        self._update_recent_menu()

        file_menu.addSeparator()

        self._save_action = QAction("保存(&S)", self)
        self._save_action.triggered.connect(self._on_save)
        file_menu.addAction(self._save_action)

        self._save_as_action = QAction("另存为(&A)", self)
        self._save_as_action.triggered.connect(self._on_save_as)
        file_menu.addAction(self._save_as_action)

        file_menu.addSeparator()

        self._export_excel_action = QAction("导出 Excel(&E)", self)
        self._export_excel_action.triggered.connect(lambda: self._on_export_excel(False))
        file_menu.addAction(self._export_excel_action)

        file_menu.addSeparator()

        exit_action = QAction("退出(&Q)", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = menu_bar.addMenu("编辑(&E)")
        self._edit_menu = edit_menu

        self._undo_action = QAction("撤销(&Z)", self)
        self._undo_action.triggered.connect(self._on_undo)
        self._undo_action.setEnabled(False)
        edit_menu.addAction(self._undo_action)

        self._redo_action = QAction("重做(&Y)", self)
        self._redo_action.triggered.connect(self._on_redo)
        self._redo_action.setEnabled(False)
        edit_menu.addAction(self._redo_action)

        edit_menu.addSeparator()

        self._auto_plan_action = QAction("自动规划合图(&P)", self)
        self._auto_plan_action.triggered.connect(self._on_auto_plan)
        edit_menu.addAction(self._auto_plan_action)

        # ===== 检查模式专用文件菜单（插入到设置菜单之前，默认隐藏）=====
        from PySide6.QtWidgets import QMenu
        self._reverse_file_menu = QMenu("文件(&F)", self)
        self._reverse_file_menu.menuAction().setVisible(False)

        settings_menu = menu_bar.addMenu("设置(&T)")
        self._settings_menu = settings_menu
        self._settings_action = QAction("偏好设置...", self)
        self._settings_action.triggered.connect(self._on_open_settings)
        settings_menu.addAction(self._settings_action)

        settings_menu.addSeparator()
        self._clear_screenshot_action = QAction("清理截图缓存...", self)
        self._clear_screenshot_action.triggered.connect(self._on_clear_screenshot_cache)
        settings_menu.addAction(self._clear_screenshot_action)

        # 将检查模式文件菜单插入到设置菜单之前，保证显示顺序为：文件 | 设置
        menu_bar.insertMenu(self._settings_menu.menuAction(), self._reverse_file_menu)

        self._reverse_new_action = QAction("新建(&N)", self)
        self._reverse_new_action.setShortcut(QKeySequence("Ctrl+N"))
        self._reverse_new_action.triggered.connect(self._on_reverse_new)
        self._reverse_file_menu.addAction(self._reverse_new_action)

        self._reverse_open_action = QAction("打开(&O)", self)
        self._reverse_open_action.setShortcut(QKeySequence("Ctrl+O"))
        self._reverse_open_action.triggered.connect(self._on_reverse_open)
        self._reverse_file_menu.addAction(self._reverse_open_action)

        # 最近打开子菜单（检查模式独立）
        self._reverse_recent_menu = self._reverse_file_menu.addMenu("最近打开(&R)")
        self._update_reverse_recent_menu()

        self._reverse_file_menu.addSeparator()

        self._reverse_save_action = QAction("保存(&S)", self)
        self._reverse_save_action.setShortcut(QKeySequence("Ctrl+S"))
        self._reverse_save_action.triggered.connect(self._on_reverse_save)
        self._reverse_file_menu.addAction(self._reverse_save_action)

        self._reverse_save_as_action = QAction("另存为(&A)", self)
        self._reverse_save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self._reverse_save_as_action.triggered.connect(self._on_reverse_save_as)
        self._reverse_file_menu.addAction(self._reverse_save_as_action)

        self._reverse_file_menu.addSeparator()

        # 导出报告（与底部工具栏一致）
        self._reverse_export_brief_action = QAction("导出粗略报告", self)
        self._reverse_export_brief_action.triggered.connect(
            lambda: self._on_export_reverse_report(False)
        )
        self._reverse_file_menu.addAction(self._reverse_export_brief_action)

        self._reverse_export_detail_action = QAction("导出详细报告（含图集标注）", self)
        self._reverse_export_detail_action.triggered.connect(
            lambda: self._on_export_reverse_report(True)
        )
        self._reverse_file_menu.addAction(self._reverse_export_detail_action)

        # ---- 模式切换按钮（菜单栏右上角）----
        self._mode_switch_btn = QPushButton("⇄ 检查模式")
        self._mode_switch_btn.setToolTip("切换到检查模式 - 分析图集重复内容")
        self._mode_switch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mode_switch_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {REVERSE_COLOR_PRIMARY};
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 3px 12px;
                font-size: 11px;
                font-weight: 500;
                margin: 2px 6px;
            }}
            QPushButton:hover {{
                background-color: {REVERSE_COLOR_PRIMARY_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {REVERSE_COLOR_PRIMARY_PRESSED};
            }}
        """)
        self._mode_switch_btn.clicked.connect(self._toggle_mode)
        menu_bar.setCornerWidget(self._mode_switch_btn, Qt.Corner.TopRightCorner)

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 4, 8, 4)
        main_layout.setSpacing(4)

        # ---- QStackedWidget 双模式 ----
        self._mode_stack = QStackedWidget()

        # ========== Page 0: 规划模式 ==========
        plan_page = QWidget()
        plan_layout = QVBoxLayout(plan_page)
        plan_layout.setContentsMargins(0, 0, 0, 0)
        plan_layout.setSpacing(4)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: transparent;
                width: 6px;
            }
            QSplitter::handle:hover {
                background-color: #0078D4;
            }
        """)
        self._splitter.setHandleWidth(6)

        from .atlas_outline_panel import AtlasOutlinePanel
        from .atlas_editor_view import AtlasEditorView
        from .library_panel import LibraryPanel

        self._outline_panel = AtlasOutlinePanel(self._project, self)
        self._editor_view = AtlasEditorView(self._project, self._animation_engine, self)
        self._library_panel = LibraryPanel(self._project, self)

        self._splitter.addWidget(self._outline_panel)
        self._splitter.addWidget(self._editor_view)
        self._splitter.addWidget(self._library_panel)

        # 素材库默认宽度需保证列表视图所有列完整显示
        self._splitter.setSizes([140, 780, 680])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)

        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(1, False)
        self._splitter.setCollapsible(2, False)

        plan_layout.addWidget(self._splitter, 1)

        self._toolbar = ToolbarWidget(self)
        plan_layout.addWidget(self._toolbar)

        self._mode_stack.addWidget(plan_page)  # index 0

        # ========== Page 1: 检查模式 ==========
        reverse_page = QWidget()
        reverse_layout = QVBoxLayout(reverse_page)
        reverse_layout.setContentsMargins(0, 0, 0, 0)
        reverse_layout.setSpacing(4)

        from .reverse_atlas_list_panel import ReverseAtlasListPanel
        from .reverse_viewer import ReverseViewer
        from .reverse_import_panel import ReverseImportPanel
        from .reverse_toolbar import ReverseToolbar

        self._reverse_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._reverse_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: transparent;
                width: 6px;
            }}
            QSplitter::handle:hover {{
                background-color: {REVERSE_COLOR_PRIMARY};
            }}
        """)
        self._reverse_splitter.setHandleWidth(6)

        self._reverse_atlas_list = ReverseAtlasListPanel(self)
        self._reverse_viewer = ReverseViewer(self)
        self._reverse_import_panel = ReverseImportPanel(self)

        self._reverse_splitter.addWidget(self._reverse_atlas_list)
        self._reverse_splitter.addWidget(self._reverse_viewer)
        self._reverse_splitter.addWidget(self._reverse_import_panel)

        self._reverse_splitter.setSizes([260, 740, 320])
        self._reverse_splitter.setStretchFactor(0, 0)
        self._reverse_splitter.setStretchFactor(1, 1)
        self._reverse_splitter.setStretchFactor(2, 0)

        self._reverse_splitter.setCollapsible(0, False)
        self._reverse_splitter.setCollapsible(1, False)
        self._reverse_splitter.setCollapsible(2, False)

        reverse_layout.addWidget(self._reverse_splitter, 1)

        self._reverse_toolbar = ReverseToolbar(self)
        reverse_layout.addWidget(self._reverse_toolbar)

        self._mode_stack.addWidget(reverse_page)  # index 1

        main_layout.addWidget(self._mode_stack, 1)

        self._connect_signals()

    def _connect_signals(self):
        # ---- 规划模式信号 ----
        self._outline_panel.atlas_selected.connect(self._on_atlas_selected)
        self._outline_panel.project_changed.connect(self._on_project_changed)

        self._editor_view.project_changed.connect(self._on_project_changed)
        self._editor_view.before_change.connect(self._before_editor_change)
        self._editor_view.after_change.connect(self._after_editor_change)
        self._editor_view.atlas_auto_created.connect(self._on_atlas_auto_created)

        self._library_panel.project_changed.connect(self._on_project_changed)
        self._library_panel.jump_to_atlas.connect(self._on_jump_to_atlas)

        self._toolbar.export_excel_clicked.connect(self._on_export_excel)
        self._toolbar.auto_plan_clicked.connect(self._on_auto_plan)

        self._undo_manager.state_changed.connect(self._update_undo_actions)

        # ---- 检查模式信号 ----
        self._reverse_atlas_list.atlas_selected.connect(self._on_reverse_atlas_selected)
        self._reverse_atlas_list.atlas_list_changed.connect(self._on_reverse_list_changed)
        self._reverse_import_panel.files_imported.connect(self._on_reverse_files_imported)
        self._reverse_import_panel.group_selected.connect(self._on_reverse_group_selected)
        self._reverse_toolbar.start_analysis.connect(self._on_start_analysis)
        self._reverse_toolbar.export_report.connect(self._on_export_reverse_report)
        self._reverse_viewer.mark_clicked.connect(self._on_reverse_mark_clicked)
        self._reverse_import_panel.populate_progress.connect(self._on_populate_progress)
        self._reverse_import_panel.populate_finished.connect(self._on_populate_finished)

    def _on_jump_to_atlas(self, atlas_id: str):
        """素材库中点击合图标记时跳转到对应合图"""
        atlas = self._project.find_atlas(atlas_id)
        if atlas:
            self._outline_panel.select_atlas(atlas_id)
            self._editor_view.set_atlas(atlas)

    def _on_atlas_auto_created(self, atlas_id: str):
        """编辑器自动创建合图后，刷新大纲面板并选中"""
        self._outline_panel.set_project(self._project)
        self._outline_panel.select_atlas(atlas_id)
        self._on_project_changed()

    # ---- Shortcuts ----
    def _setup_shortcuts(self):
        for _, sc in self._shortcuts.items():
            sc.setEnabled(False)
            sc.deleteLater()
        self._shortcuts.clear()

        shortcuts = self._settings.get("shortcuts", DEFAULT_SHORTCUTS)

        self._new_action.setShortcut(QKeySequence(shortcuts.get("new", "Ctrl+N")))
        self._open_action.setShortcut(QKeySequence(shortcuts.get("open", "Ctrl+O")))
        self._save_action.setShortcut(QKeySequence(shortcuts.get("save", "Ctrl+S")))
        self._save_as_action.setShortcut(QKeySequence(shortcuts.get("save_as", "Ctrl+Shift+S")))
        self._undo_action.setShortcut(QKeySequence(shortcuts.get("undo", "Ctrl+Z")))
        self._redo_action.setShortcut(QKeySequence(shortcuts.get("redo", "Ctrl+Y")))

        prev_sc = QShortcut(QKeySequence(shortcuts.get("prev_atlas", "PgUp")), self)
        prev_sc.activated.connect(self._on_prev_atlas)
        self._shortcuts["prev_atlas"] = prev_sc

        next_sc = QShortcut(QKeySequence(shortcuts.get("next_atlas", "PgDown")), self)
        next_sc.activated.connect(self._on_next_atlas)
        self._shortcuts["next_atlas"] = next_sc

        fill_sc = QShortcut(QKeySequence(shortcuts.get("auto_fill", "Ctrl+F")), self)
        fill_sc.activated.connect(self._on_auto_fill_shortcut)
        self._shortcuts["auto_fill"] = fill_sc

        screenshot_sc = QShortcut(QKeySequence(shortcuts.get("screenshot", "Alt+D")), self)
        screenshot_sc.activated.connect(self._on_screenshot_shortcut)
        self._shortcuts["screenshot"] = screenshot_sc

        # 同步更新全局热键
        self._setup_global_hotkeys()

    def _setup_global_hotkeys(self):
        """设置系统级全局热键（窗口不在前台也能响应）"""
        import platform
        if platform.system() != "Windows":
            return  # 仅 Windows 支持

        from services.global_hotkey import GlobalHotkeyService

        # 先停止旧的全局热键服务
        if self._global_hotkey is not None:
            self._global_hotkey.stop()
            self._global_hotkey = None

        shortcuts = self._settings.get("shortcuts", DEFAULT_SHORTCUTS)
        screenshot_key = shortcuts.get("screenshot", "Alt+D")

        self._global_hotkey = GlobalHotkeyService(self)
        self._global_hotkey.hotkey_triggered.connect(self._on_global_hotkey)
        self._global_hotkey.register("screenshot", screenshot_key)
        self._global_hotkey.start()

    def _on_prev_atlas(self):
        self._outline_panel.select_prev_atlas()

    def _on_next_atlas(self):
        self._outline_panel.select_next_atlas()

    def _on_auto_fill_shortcut(self):
        self._editor_view.do_auto_fill()

    def _on_screenshot_shortcut(self):
        """截图快捷键 - 仅在规划模式下生效"""
        if self._current_mode == "plan":
            self._library_panel._on_screenshot()

    def _on_global_hotkey(self, name: str):
        """全局热键回调（从后台线程通过 Signal 分发到主线程）"""
        if name == "screenshot":
            # 全局热键截图：不限模式，直接启动截图
            if self._current_mode == "plan":
                self._library_panel._on_screenshot()
            else:
                # 检查模式下也允许截图，但先切回规划模式
                # 或者直接启动截图（截图本身不依赖模式）
                self._library_panel._on_screenshot()

    # ---- Auto Plan (自动规划合图) ----
    def _on_auto_plan(self):
        """自动规划：会删除所有现有合图并重新创建"""
        if not self._project.library:
            QMessageBox.information(self, "自动规划", "素材库中没有图片，请先导入素材。")
            return

        # 警告用户
        ret = QMessageBox.warning(
            self, "自动规划合图",
            "自动规划会删除所有现有的手动合图，并根据素材库中所有图的压缩尺寸重新创建合图。\n\n"
            "建议先保存当前项目后再执行此操作。\n\n"
            "确定要继续自动规划吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        self._editor_view.before_change.emit("自动规划合图")

        # 清空所有现有合图
        self._project.atlas_list.clear()
        self._editor_view.clear()

        atlas_size = DEFAULT_ATLAS_SIZE
        created_atlases = 0

        remaining = list(self._project.library)
        remaining.sort(key=lambda t: t.display_width * t.display_height, reverse=True)

        while remaining:
            count = len(self._project.atlas_list)
            atlas = AtlasModel(name=f"合图 {count + 1}", size=atlas_size)

            rects = [
                PackRect(id=t.id, width=t.display_width, height=t.display_height)
                for t in remaining
            ]
            packer = MaxRectsBinPacker(atlas_size, atlas_size)
            results = packer.pack(rects)

            if not results:
                break

            placed_ids = set()
            for r in results:
                tex = self._project.find_texture(r.id)
                if tex:
                    pt = PlacedTexture(
                        texture=tex,
                        grid_x=r.x // 16,
                        grid_y=r.y // 16,
                    )
                    atlas.place(pt)
                    placed_ids.add(r.id)

            if not placed_ids:
                break

            self._project.add_atlas(atlas)
            created_atlases += 1
            remaining = [t for t in remaining if t.id not in placed_ids]

        self._outline_panel.set_project(self._project)
        self._library_panel.refresh()

        if self._project.atlas_list:
            last = self._project.atlas_list[-1]
            self._outline_panel.select_atlas(last.id)
            self._editor_view.set_atlas(last)

        self._editor_view.after_change.emit("自动规划合图")
        self._on_project_changed()

        remain_count = len(remaining)
        msg = f"自动规划完成，新建 {created_atlases} 张合图。"
        if remain_count > 0:
            msg += f"\n{remain_count} 张素材因尺寸过大无法放入。"
        QMessageBox.information(self, "自动规划", msg)

    # ---- Undo / Redo ----
    def _init_undo_state(self):
        self._undo_manager.set_initial_state(self._project.to_dict())

    def _before_editor_change(self, desc: str):
        pass

    def _after_editor_change(self, desc: str):
        self._undo_manager.push(desc, self._project.to_dict())

    def _on_undo(self):
        snapshot = self._undo_manager.undo()
        if snapshot:
            self._restore_from_snapshot(snapshot)

    def _on_redo(self):
        snapshot = self._undo_manager.redo()
        if snapshot:
            self._restore_from_snapshot(snapshot)

    def _restore_from_snapshot(self, snapshot: dict):
        project = ProjectModel.from_dict(snapshot)
        self._project = project

        current_atlas_id = self._outline_panel.get_current_atlas_id()

        self._outline_panel.set_project(self._project)
        self._editor_view.set_project(self._project)
        self._library_panel.set_project(self._project)

        if current_atlas_id:
            atlas = self._project.find_atlas(current_atlas_id)
            if atlas:
                self._outline_panel.select_atlas(current_atlas_id)
                self._editor_view.set_atlas(atlas)
            elif self._project.atlas_list:
                first = self._project.atlas_list[0]
                self._outline_panel.select_atlas(first.id)
                self._editor_view.set_atlas(first)

        self._project.mark_dirty()
        self._update_title()
        self._update_stats()

    def _update_undo_actions(self):
        self._undo_action.setEnabled(self._undo_manager.can_undo())
        self._redo_action.setEnabled(self._undo_manager.can_redo())

    # ---- Auto Update (自动检查更新) ----
    def _auto_check_update(self):
        """启动时静默检查更新（后台线程，不弹任何提示除非有新版本）"""
        from services.update_service import UpdateChecker

        self._silent_update_checker = UpdateChecker(GITHUB_OWNER, GITHUB_REPO, APP_VERSION)
        self._silent_update_thread = QThread()
        self._silent_update_checker.moveToThread(self._silent_update_thread)

        self._silent_update_checker.check_finished.connect(self._on_silent_check_result)
        self._silent_update_thread.started.connect(self._silent_update_checker.run)

        self._silent_update_thread.start()

    def _on_silent_check_result(self, result):
        """静默检查更新结果回调"""
        # 清理线程
        if hasattr(self, '_silent_update_thread') and self._silent_update_thread:
            self._silent_update_thread.quit()
            self._silent_update_thread.wait(3000)
            self._silent_update_thread.deleteLater()
            self._silent_update_thread = None
        if hasattr(self, '_silent_update_checker') and self._silent_update_checker:
            self._silent_update_checker.deleteLater()
            self._silent_update_checker = None

        # 只在发现新版本时弹出对话框
        if result.has_update and not result.error:
            from views.update_dialog import UpdateDialog
            dlg = UpdateDialog(result, self)
            dlg.exec()

    # ---- Settings ----
    def _on_open_settings(self):
        dlg = SettingsDialog(self._settings, self)
        if dlg.exec() == SettingsDialog.DialogCode.Accepted:
            old_quality = self._settings.get("thumbnail_quality", DEFAULT_THUMBNAIL_QUALITY)
            new_settings = dlg.get_settings()
            self._settings = new_settings
            self._undo_manager.max_steps = new_settings.get("undo_steps", DEFAULT_UNDO_STEPS)
            self._setup_shortcuts()

            # 持久化设置
            self._save_user_preferences()

            # 更新素材库截图按钮上的快捷键文字
            screenshot_key = new_settings.get("shortcuts", {}).get("screenshot", "Alt+D")
            self._library_panel.update_screenshot_shortcut_label(screenshot_key)

            # 如果缩略图清晰度变更，清除缓存并刷新
            new_quality = new_settings.get("thumbnail_quality", DEFAULT_THUMBNAIL_QUALITY)
            if new_quality != old_quality:
                from services.image_service import ImageService
                ImageService.clear_thumbnail_cache()
                # 清除所有素材的缩略图缓存路径，下次显示时重新生成
                for tex in self._project.library:
                    tex.thumbnail_path = None
                self._library_panel.refresh()

    def _on_clear_screenshot_cache(self):
        """清理截图缓存"""
        from services.screenshot_service import ScreenshotService
        count = ScreenshotService.get_screenshot_count()
        size_mb = ScreenshotService.get_screenshot_size_mb()

        if count == 0:
            QMessageBox.information(self, "清理截图缓存", "截图缓存已为空，无需清理。")
            return

        ret = QMessageBox.warning(
            self, "清理截图缓存",
            f"将删除 ScreenShot 文件夹中的所有 {count} 个截图文件（共 {size_mb:.1f} MB）。\n\n"
            f"⚠️ 注意：如果素材库中仍有引用这些截图的贴图，它们的缩略图将显示为「缺失」。\n\n"
            f"确定要清理吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret == QMessageBox.StandardButton.Yes:
            deleted = ScreenshotService.clear_screenshots()
            QMessageBox.information(
                self, "清理完成", f"已删除 {deleted} 个截图文件。"
            )

    # ---- Atlas selection ----
    def _on_atlas_selected(self, atlas_id: str):
        atlas = self._project.find_atlas(atlas_id)
        if atlas:
            self._editor_view.set_atlas(atlas)

    def _on_project_changed(self):
        self._project.mark_dirty()
        self._update_title()
        self._update_stats()
        self._outline_panel.refresh()
        # 避免素材库内部操作触发二次刷新
        if not getattr(self._library_panel, '_skip_external_refresh', False):
            self._library_panel.refresh()

    def _update_title(self):
        name = "未命名"
        if self._current_file_path:
            name = os.path.basename(self._current_file_path)
        dirty = " *" if self._project.dirty else ""
        self.setWindowTitle(f"TexturesAtlasView - {name}{dirty}")

    def _update_stats(self):
        self._toolbar.update_stats(
            len(self._project.atlas_list),
            len(self._project.library),
        )

    def _check_save(self) -> bool:
        if not self._project.dirty:
            return True
        ret = QMessageBox.question(
            self, "保存更改",
            "当前项目有未保存的更改，是否保存？",
            QMessageBox.StandardButton.Save |
            QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel,
        )
        if ret == QMessageBox.StandardButton.Save:
            return self._on_save()
        elif ret == QMessageBox.StandardButton.Cancel:
            return False
        return True

    def _on_new(self):
        if not self._check_save():
            return
        self._project.reset()
        self._current_file_path = None
        self._editor_view.clear()
        self._outline_panel.set_project(self._project)
        self._library_panel.set_project(self._project)
        self._undo_manager.set_initial_state(self._project.to_dict())
        self._update_title()
        self._update_stats()

    def _on_open(self):
        if not self._check_save():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "打开项目", "", PROJECT_FILE_FILTER
        )
        if not path:
            return
        self._load_project(path)

    def _load_project(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            project = ProjectModel.from_dict(data)
            self._project = project
            self._current_file_path = path

            self._outline_panel.set_project(self._project)
            self._editor_view.set_project(self._project)
            self._library_panel.set_project(self._project)

            if self._project.atlas_list:
                first = self._project.atlas_list[0]
                self._outline_panel.select_atlas(first.id)
                self._editor_view.set_atlas(first)

            self._project.mark_clean()
            self._undo_manager.set_initial_state(self._project.to_dict())
            self._update_title()
            self._update_stats()
            self._add_recent_file(path)
        except Exception as e:
            QMessageBox.critical(self, "打开失败", f"无法加载项目文件:\n{e}")

    def _on_save(self) -> bool:
        if self._current_file_path:
            return self._save_to(self._current_file_path)
        return self._on_save_as()

    def _on_save_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self, "另存为", "", PROJECT_FILE_FILTER
        )
        if not path:
            return False
        if not path.endswith(".tatlas"):
            path += ".tatlas"
        return self._save_to(path)

    def _save_to(self, path: str) -> bool:
        try:
            data = self._project.to_dict()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._current_file_path = path
            self._project.mark_clean()
            self._update_title()
            self._add_recent_file(path)
            return True
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"无法保存项目:\n{e}")
            return False

    # ---- Recent Files ----
    MAX_RECENT_FILES = 10

    def _get_recent_files(self) -> list:
        """从 QSettings 读取最近打开的文件列表"""
        settings = self._get_settings()
        files = settings.value("recent_files", [])
        if isinstance(files, str):
            files = [files] if files else []
        # 过滤掉不存在的文件
        return [f for f in files if os.path.isfile(f)]

    def _add_recent_file(self, path: str):
        """将文件路径添加到最近打开列表（去重、置顶）"""
        path = os.path.normpath(path)
        recent = self._get_recent_files()
        # 去除重复
        recent = [f for f in recent if os.path.normpath(f) != path]
        recent.insert(0, path)
        # 最多保留 MAX_RECENT_FILES 条
        recent = recent[:self.MAX_RECENT_FILES]
        settings = self._get_settings()
        settings.setValue("recent_files", recent)
        self._update_recent_menu()

    def _update_recent_menu(self):
        """刷新'最近打开'子菜单"""
        self._recent_menu.clear()
        recent = self._get_recent_files()
        if not recent:
            empty_action = QAction("(无)", self)
            empty_action.setEnabled(False)
            self._recent_menu.addAction(empty_action)
            return

        for i, path in enumerate(recent):
            display = os.path.basename(path)
            action = QAction(f"{i + 1}. {display}", self)
            action.setToolTip(path)
            action.setData(path)
            action.triggered.connect(self._on_open_recent)
            self._recent_menu.addAction(action)

        self._recent_menu.addSeparator()
        clear_action = QAction("清除最近打开记录", self)
        clear_action.triggered.connect(self._on_clear_recent)
        self._recent_menu.addAction(clear_action)

    def _on_open_recent(self):
        """点击最近打开的文件"""
        action = self.sender()
        if action:
            path = action.data()
            if path and os.path.isfile(path):
                if not self._check_save():
                    return
                self._load_project(path)
            else:
                QMessageBox.warning(self, "文件不存在", f"文件已被移除或删除:\n{path}")
                self._update_recent_menu()

    def _on_clear_recent(self):
        """清除最近打开记录"""
        settings = self._get_settings()
        settings.setValue("recent_files", [])
        self._update_recent_menu()

    def _on_export_excel(self, full_mode: bool = False):
        if not self._project.atlas_list:
            QMessageBox.information(self, "导出", "没有合图数据可以导出")
            return

        mode_text = "完整模式" if full_mode else "预览模式"
        path, _ = QFileDialog.getSaveFileName(
            self, f"导出 Excel ({mode_text})", "", EXCEL_FILE_FILTER
        )
        if not path:
            return
        if not path.endswith(".xlsx"):
            path += ".xlsx"

        if full_mode:
            # 提醒用户完整模式较慢
            ret = QMessageBox.information(
                self, "完整模式导出",
                "完整模式会在表格中嵌入原图，生成过程较慢。\n"
                "导出期间可以继续操作，进度会在底部工具栏显示。\n\n"
                "确定要使用完整模式导出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if ret != QMessageBox.StandardButton.Yes:
                return

        # 异步导出
        self._start_async_export(path, full_mode)

    def _start_async_export(self, file_path: str, full_mode: bool):
        """启动异步Excel导出"""
        self._export_worker = _ExcelExportWorker(self._project, file_path, full_mode)
        self._export_thread = QThread()
        self._export_worker.moveToThread(self._export_thread)

        self._export_worker.progress.connect(self._on_export_progress)
        self._export_worker.finished.connect(self._on_export_finished)
        self._export_worker.error.connect(self._on_export_error)
        self._export_thread.started.connect(self._export_worker.run)

        self._export_thread.start()

    def _on_export_progress(self, current: int, total: int, msg: str):
        """导出进度回调"""
        self._toolbar.set_export_progress(current, total)

    def _on_export_finished(self, file_path: str):
        """导出完成"""
        self._cleanup_export_thread()
        self._toolbar.set_export_finished()

    def _on_export_error(self, error_msg: str):
        """导出失败"""
        self._cleanup_export_thread()
        self._toolbar.set_export_error()
        QMessageBox.critical(self, "导出失败", f"导出 Excel 失败:\n{error_msg}")

    def _cleanup_export_thread(self):
        """清理导出线程"""
        if hasattr(self, '_export_thread') and self._export_thread:
            self._export_thread.quit()
            self._export_thread.wait(3000)
            self._export_thread.deleteLater()
            self._export_thread = None
        if hasattr(self, '_export_worker') and self._export_worker:
            self._export_worker.deleteLater()
            self._export_worker = None

    # ---- Window State Persistence ----
    def _get_settings(self) -> QSettings:
        """获取 QSettings 实例"""
        return QSettings("TexturesAtlasView", "MainWindow")

    def _save_window_state(self):
        """保存窗口几何尺寸、最大化状态和 splitter 比例"""
        settings = self._get_settings()
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        settings.setValue("maximized", self.isMaximized())
        settings.setValue("splitter_sizes", self._splitter.sizes())

    def _save_user_preferences(self):
        """将用户偏好设置（快捷键等）持久化到 QSettings"""
        settings = self._get_settings()
        settings.setValue("user_preferences", json.dumps(self._settings, ensure_ascii=False))

    def _restore_user_preferences(self):
        """从 QSettings 恢复用户偏好设置"""
        settings = self._get_settings()
        raw = settings.value("user_preferences")
        if raw:
            try:
                saved = json.loads(raw)
                # 合并到当前 _settings（保留新增的默认值）
                for key, val in saved.items():
                    if key == "shortcuts":
                        # 确保所有默认快捷键都存在
                        merged = DEFAULT_SHORTCUTS.copy()
                        merged.update(val)
                        self._settings["shortcuts"] = merged
                    elif key == "width_compress_map":
                        # JSON key 反序列化后可能是字符串，转回 int
                        self._settings["width_compress_map"] = {
                            int(k): v for k, v in val.items()
                        }
                    elif key == "width_color_map":
                        self._settings["width_color_map"] = {
                            int(k): v for k, v in val.items()
                        }
                    else:
                        self._settings[key] = val
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                print(f"[Settings] 恢复用户设置失败: {e}")

    def _restore_window_state(self):
        """恢复上次保存的窗口状态"""
        settings = self._get_settings()

        geometry = settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

            state = settings.value("windowState")
            if state is not None:
                self.restoreState(state)

            maximized = settings.value("maximized", False, type=bool)
            if maximized:
                self.showMaximized()

            splitter_sizes = settings.value("splitter_sizes")
            if splitter_sizes is not None:
                try:
                    sizes = [int(s) for s in splitter_sizes]
                    if len(sizes) == 3 and all(s > 0 for s in sizes):
                        self._splitter.setSizes(sizes)
                except (TypeError, ValueError):
                    pass
        else:
            # 首次启动，默认最大化
            self.showMaximized()

    def closeEvent(self, event: QCloseEvent):
        if self._check_save():
            # 停止全局热键服务
            if self._global_hotkey is not None:
                self._global_hotkey.stop()
                self._global_hotkey = None
            self._save_window_state()
            self._save_user_preferences()
            event.accept()
        else:
            event.ignore()

    # ================================================================
    #                      检查模式相关方法
    # ================================================================

    def _toggle_mode(self):
        """切换规划模式 / 检查模式"""
        if self._current_mode == "plan":
            self._switch_to_reverse_mode()
        else:
            self._switch_to_plan_mode()

    def _switch_to_reverse_mode(self):
        """切换到检查模式"""
        self._current_mode = "reverse"
        self._mode_stack.setCurrentIndex(1)

        # 更新按钮样式和文字
        self._mode_switch_btn.setText("⇄ 规划模式")
        self._mode_switch_btn.setToolTip("切换到规划模式 - 合图规划")
        self._mode_switch_btn.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 3px 12px;
                font-size: 11px;
                font-weight: 500;
                margin: 2px 6px;
            }
            QPushButton:hover {
                background-color: #444444;
            }
            QPushButton:pressed {
                background-color: #222222;
            }
        """)

        # 切换主题
        from main import load_stylesheet
        qss = load_stylesheet("light")
        QApplication.instance().setStyleSheet(qss)

        # 隐藏规划模式特有的菜单项
        self._auto_plan_action.setVisible(False)
        self._export_excel_action.setVisible(False)
        self._undo_action.setVisible(False)
        self._redo_action.setVisible(False)

        # 检查模式下隐藏规划模式文件菜单和编辑菜单，显示检查模式文件菜单
        self._file_menu.menuAction().setVisible(False)
        self._edit_menu.menuAction().setVisible(False)
        self._reverse_file_menu.menuAction().setVisible(True)

        # 更新窗口标题
        if self._reverse_file_path:
            name = os.path.basename(self._reverse_file_path)
            self.setWindowTitle(f"TexturesAtlasView - 检查模式 - {name}")
        else:
            self.setWindowTitle("TexturesAtlasView - 检查模式")

        # 同步后缀设置
        suffix = self._settings.get("atlas_suffix", DEFAULT_ATLAS_SUFFIX)
        self._reverse_import_panel.set_atlas_suffix(suffix)

    def _switch_to_plan_mode(self):
        """切换到规划模式"""
        self._current_mode = "plan"
        self._mode_stack.setCurrentIndex(0)

        # 更新按钮样式和文字
        self._mode_switch_btn.setText("⇄ 检查模式")
        self._mode_switch_btn.setToolTip("切换到检查模式 - 分析图集重复内容")
        self._mode_switch_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {REVERSE_COLOR_PRIMARY};
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 3px 12px;
                font-size: 11px;
                font-weight: 500;
                margin: 2px 6px;
            }}
            QPushButton:hover {{
                background-color: {REVERSE_COLOR_PRIMARY_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {REVERSE_COLOR_PRIMARY_PRESSED};
            }}
        """)

        # 切换主题
        from main import load_stylesheet
        qss = load_stylesheet("dark")
        QApplication.instance().setStyleSheet(qss)

        # 恢复规划模式菜单项
        self._auto_plan_action.setVisible(True)
        self._export_excel_action.setVisible(True)
        self._undo_action.setVisible(True)
        self._redo_action.setVisible(True)

        # 恢复文件菜单和编辑菜单，隐藏检查模式文件菜单
        self._file_menu.menuAction().setVisible(True)
        self._edit_menu.menuAction().setVisible(True)
        self._reverse_file_menu.menuAction().setVisible(False)

        # 更新窗口标题
        self._update_title()

    # ---- 检查模式 - 图集选中 ----
    def _on_reverse_atlas_selected(self, atlas_id: str):
        """检查模式 - 左侧图集选中"""
        atlas = self._reverse_atlas_list.find_atlas(atlas_id)
        if atlas:
            self._reverse_viewer.show_atlas(atlas)

    def _on_reverse_list_changed(self):
        """检查模式 - 图集列表变更"""
        atlas_count = len(self._reverse_atlas_list.get_atlas_items())
        self._reverse_toolbar.update_stats(atlas_count, 0)
        self._reverse_toolbar.set_analysis_enabled(atlas_count >= 1)
        # 列表变更后清空旧的分析结果（需重新分析）
        self._reverse_viewer.set_duplicate_result(None)
        self._reverse_import_panel.clear_results()
        self._reverse_atlas_list.set_duplicate_result(None)
        self._reverse_toolbar.set_export_enabled(False)

    # ---- 检查模式 - 文件导入 ----
    def _on_reverse_files_imported(self, file_paths: list):
        """检查模式 - 处理导入的文件（增量添加，不清空现有列表）"""
        from services.atlas_segmenter import AtlasSegmenter

        suffix = self._settings.get("atlas_suffix", DEFAULT_ATLAS_SUFFIX)

        # 去重：排除已导入的文件路径
        existing_items = self._reverse_atlas_list.get_atlas_items()
        existing_paths = {item.file_path for item in existing_items}
        new_paths = [p for p in file_paths if os.path.normpath(p) not in
                     {os.path.normpath(ep) for ep in existing_paths}]

        if not new_paths:
            QMessageBox.information(self, "导入", "所选文件已全部存在于图集列表中。")
            return

        # 增量导入时清空旧的分析结果（需要重新分析）
        if existing_items:
            self._reverse_viewer.set_duplicate_result(None)
            self._reverse_import_panel.clear_results()
            self._reverse_atlas_list.set_duplicate_result(None)
            self._reverse_toolbar.set_export_enabled(False)

        # 创建进度对话框
        progress = QProgressDialog("正在分割图集...", "取消", 0, len(new_paths), self)
        progress.setWindowTitle("导入图集")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(300)

        items = []
        errors = []
        for i, path in enumerate(new_paths):
            if progress.wasCanceled():
                break
            progress.setValue(i)
            progress.setLabelText(f"正在分割: {os.path.basename(path)}")
            QApplication.processEvents()

            try:
                item = AtlasSegmenter.build_atlas_item(path, suffix)
                if item:
                    items.append(item)
                else:
                    errors.append(os.path.basename(path))
            except Exception as e:
                errors.append(f"{os.path.basename(path)} ({e})")

        progress.setValue(len(new_paths))
        progress.close()

        if items:
            self._reverse_atlas_list.add_atlas_items(items)
            # 自动选中第一个新导入的图集
            target_row = self._reverse_atlas_list._list.count() - len(items)
            if target_row >= 0:
                self._reverse_atlas_list._list.setCurrentRow(target_row)

        if errors:
            QMessageBox.warning(
                self, "导入警告",
                f"以下 {len(errors)} 个文件导入失败:\n" + "\n".join(errors[:10])
            )

    # ---- 检查模式 - 开始分析（后台线程） ----
    def _on_start_analysis(self, mode: str):
        """检查模式 - 开始重复检测分析（后台线程 + 进度对话框）

        检测器直接在图集原图上做梯次网格像素比对，不需要预先分割。
        """
        atlases = self._reverse_atlas_list.get_atlas_items()
        if not atlases:
            QMessageBox.information(self, "分析", "请先导入图集文件。")
            return

        if len(atlases) < 2:
            QMessageBox.information(self, "分析", "至少需要 2 个图集才能进行跨图集比较。")
            return

        self._reverse_toolbar.set_analyzing(True)

        # 直接启动后台检测（不再需要分割阶段）
        self._detect_progress = QProgressDialog("正在分析...", "取消", 0, 100, self)
        self._detect_progress.setWindowTitle("分析进度")
        self._detect_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._detect_progress.setMinimumDuration(0)
        self._detect_progress.setMinimumWidth(480)
        self._detect_progress.setValue(0)

        # 创建后台线程
        min_tier = self._settings.get("min_tier_size", DEFAULT_MIN_TIER_SIZE)
        self._analysis_worker = _AnalysisWorker(atlases, "exact", min_tier_size=min_tier)
        self._analysis_thread = QThread()
        self._analysis_worker.moveToThread(self._analysis_thread)

        # 连接信号
        self._analysis_worker.progress.connect(self._on_analysis_progress)
        self._analysis_worker.finished.connect(self._on_analysis_finished)
        self._analysis_worker.error.connect(self._on_analysis_error)
        self._analysis_thread.started.connect(self._analysis_worker.run)

        # 取消按钮
        self._detect_progress.canceled.connect(self._on_analysis_cancel)

        self._analysis_thread.start()

    def _on_analysis_progress(self, current: int, total: int, msg: str):
        """后台线程进度回调"""
        if hasattr(self, '_detect_progress') and self._detect_progress:
            self._detect_progress.setMaximum(max(total, 1))
            self._detect_progress.setValue(min(current, total))
            self._detect_progress.setLabelText(msg)

    def _on_analysis_cancel(self):
        """取消分析"""
        if self._analysis_worker:
            self._analysis_worker.cancel()

    def _on_analysis_finished(self, result):
        """分析完成回调（在主线程执行）"""
        self._cleanup_analysis_thread()

        if result is None:
            # 被取消了
            self._reverse_toolbar.set_analyzing(False)
            return

        atlases = self._reverse_atlas_list.get_atlas_items()

        # 刷新图集列表（检测器可能更新了 sub_regions）
        self._reverse_atlas_list.refresh()

        # 更新所有面板（结果卡片由 reverse_import_panel 分批渲染，不会卡顿）
        self._reverse_import_panel.set_atlas_items(atlases)
        self._reverse_import_panel.set_duplicate_result(result)
        self._reverse_viewer.set_duplicate_result(result)
        self._reverse_atlas_list.set_duplicate_result(result)
        self._reverse_toolbar.update_stats(
            len(atlases), result.group_count, result
        )
        self._reverse_toolbar.set_export_enabled(result.group_count > 0)

        # 刷新当前选中图集的标记
        current_id = self._reverse_atlas_list.get_current_atlas_id()
        if current_id:
            atlas = self._reverse_atlas_list.find_atlas(current_id)
            if atlas:
                self._reverse_viewer.show_atlas(atlas)
                self._reverse_viewer.set_duplicate_result(result)

        self._reverse_toolbar.set_analyzing(False)

    def _on_analysis_error(self, error_msg: str):
        """分析出错回调"""
        self._cleanup_analysis_thread()
        self._reverse_toolbar.set_analyzing(False)
        QMessageBox.critical(self, "分析失败", f"重复检测过程中出错:\n{error_msg}")

    def _cleanup_analysis_thread(self):
        """清理分析线程"""
        if hasattr(self, '_detect_progress') and self._detect_progress:
            self._detect_progress.close()
            self._detect_progress = None

        if hasattr(self, '_analysis_thread') and self._analysis_thread:
            self._analysis_thread.quit()
            self._analysis_thread.wait(3000)
            self._analysis_thread.deleteLater()
            self._analysis_thread = None

        if self._analysis_worker:
            self._analysis_worker.deleteLater()
            self._analysis_worker = None

    def _on_reverse_group_selected(self, group_id: int, atlas_id: str, region_id: str):
        """检查模式 - 右侧面板选中重复组时，跳转到对应图集并定位区域。"""
        if atlas_id:
            self._reverse_atlas_list.select_atlas(atlas_id)

        self._reverse_viewer.highlight_group(group_id)

        if region_id:
            self._reverse_viewer.focus_region(region_id)

    def _on_reverse_mark_clicked(self, group_id: int):
        """检查模式 - 用户点击视口中的标记矩形，右侧面板跳转到对应组"""
        self._reverse_import_panel.scroll_to_group(group_id)

    def _on_populate_progress(self, current: int, total: int):
        """分批渲染结果卡片的进度 → 底部工具栏进度条"""
        self._reverse_toolbar.set_populate_progress(current, total)

    def _on_populate_finished(self):
        """分批渲染结果卡片完成 → 隐藏底部进度条"""
        self._reverse_toolbar.set_populate_finished()


    # ---- 检查模式 - 导出报告 ----
    def _on_reverse_new(self):
        """检查模式 - 新建（清空所有数据）"""
        if self._reverse_atlas_list.get_atlas_items():
            ret = QMessageBox.question(
                self, "新建",
                "当前有已导入的图集数据，新建将清空所有内容。\n确定要新建吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                return
        self._reverse_atlas_list.clear_all()
        self._reverse_viewer.set_duplicate_result(None)
        self._reverse_viewer.clear()
        self._reverse_import_panel.clear_results()
        self._reverse_toolbar.update_stats(0, 0)
        self._reverse_toolbar.set_export_enabled(False)
        self._reverse_toolbar.set_analysis_enabled(False)
        self._reverse_file_path = None
        self.setWindowTitle("TexturesAtlasView - 检查模式")

    def _on_reverse_open(self):
        """检查模式 - 打开存档"""
        path, _ = QFileDialog.getOpenFileName(
            self, "打开检查存档", "", REVERSE_FILE_FILTER
        )
        if not path:
            return
        self._load_reverse_project(path)

    def _load_reverse_project(self, path: str):
        """加载检查模式存档"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            from models.reverse_atlas_item import ReverseAtlasItem

            # 清空现有数据
            self._reverse_atlas_list.clear_all()
            self._reverse_viewer.set_duplicate_result(None)
            self._reverse_viewer.clear()
            self._reverse_import_panel.clear_results()

            # 恢复图集列表
            atlas_data_list = data.get("atlas_items", [])
            items = [ReverseAtlasItem.from_dict(d) for d in atlas_data_list]
            if items:
                self._reverse_atlas_list.add_atlas_items(items)

            self._reverse_file_path = path
            self._add_reverse_recent_file(path)

            atlas_count = len(items)
            self._reverse_toolbar.update_stats(atlas_count, 0)
            self._reverse_toolbar.set_analysis_enabled(atlas_count >= 1)
            self._reverse_toolbar.set_export_enabled(False)

            name = os.path.basename(path)
            self.setWindowTitle(f"TexturesAtlasView - 检查模式 - {name}")

        except Exception as e:
            QMessageBox.critical(self, "打开失败", f"无法加载检查存档:\n{e}")

    def _on_reverse_save(self) -> bool:
        """检查模式 - 保存"""
        if self._reverse_file_path:
            return self._save_reverse_to(self._reverse_file_path)
        return self._on_reverse_save_as()

    def _on_reverse_save_as(self) -> bool:
        """检查模式 - 另存为"""
        path, _ = QFileDialog.getSaveFileName(
            self, "另存为", "", REVERSE_FILE_FILTER
        )
        if not path:
            return False
        if not path.endswith(REVERSE_FILE_EXTENSION):
            path += REVERSE_FILE_EXTENSION
        return self._save_reverse_to(path)

    def _save_reverse_to(self, path: str) -> bool:
        """保存检查模式存档到文件"""
        try:
            items = self._reverse_atlas_list.get_atlas_items()
            data = {
                "version": REVERSE_MODE_VERSION,
                "atlas_items": [item.to_dict() for item in items],
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._reverse_file_path = path
            self._add_reverse_recent_file(path)
            name = os.path.basename(path)
            self.setWindowTitle(f"TexturesAtlasView - 检查模式 - {name}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"无法保存检查存档:\n{e}")
            return False

    # ---- 检查模式 - 最近打开 ----
    def _get_reverse_recent_files(self) -> list:
        """从 QSettings 读取检查模式最近打开的文件列表"""
        settings = self._get_settings()
        files = settings.value("reverse_recent_files", [])
        if isinstance(files, str):
            files = [files] if files else []
        return [f for f in files if os.path.isfile(f)]

    def _add_reverse_recent_file(self, path: str):
        """将文件路径添加到检查模式最近打开列表"""
        path = os.path.normpath(path)
        recent = self._get_reverse_recent_files()
        recent = [f for f in recent if os.path.normpath(f) != path]
        recent.insert(0, path)
        recent = recent[:self.MAX_RECENT_FILES]
        settings = self._get_settings()
        settings.setValue("reverse_recent_files", recent)
        self._update_reverse_recent_menu()

    def _update_reverse_recent_menu(self):
        """刷新检查模式'最近打开'子菜单"""
        self._reverse_recent_menu.clear()
        recent = self._get_reverse_recent_files()
        if not recent:
            empty_action = QAction("(无)", self)
            empty_action.setEnabled(False)
            self._reverse_recent_menu.addAction(empty_action)
            return

        for i, path in enumerate(recent):
            display = os.path.basename(path)
            action = QAction(f"{i + 1}. {display}", self)
            action.setToolTip(path)
            action.setData(path)
            action.triggered.connect(self._on_reverse_open_recent)
            self._reverse_recent_menu.addAction(action)

        self._reverse_recent_menu.addSeparator()
        clear_action = QAction("清除最近打开记录", self)
        clear_action.triggered.connect(self._on_reverse_clear_recent)
        self._reverse_recent_menu.addAction(clear_action)

    def _on_reverse_open_recent(self):
        """检查模式 - 点击最近打开的文件"""
        action = self.sender()
        if action:
            path = action.data()
            if path and os.path.isfile(path):
                self._load_reverse_project(path)
            else:
                QMessageBox.warning(self, "文件不存在", f"文件已被移除或删除:\n{path}")
                self._update_reverse_recent_menu()

    def _on_reverse_clear_recent(self):
        """检查模式 - 清除最近打开记录"""
        settings = self._get_settings()
        settings.setValue("reverse_recent_files", [])
        self._update_reverse_recent_menu()

    # ---- 检查模式 - 导出报告（异步） ----
    def _on_export_reverse_report(self, detailed: bool = False):
        """检查模式 - 导出分析报告（异步后台线程 + 底部进度条）

        Args:
            detailed: True=详细报告（含图集标注），False=粗略报告
        """
        result = self._reverse_import_panel._duplicate_result
        if not result or not result.groups:
            QMessageBox.information(self, "导出", "没有分析结果可以导出。")
            return

        report_type = "详细报告" if detailed else "粗略报告"
        default_name = f"检查分析_{report_type}"

        path, _ = QFileDialog.getSaveFileName(
            self, f"导出{report_type}", default_name,
            "Excel 文件 (*.xlsx);;所有文件 (*.*)"
        )
        if not path:
            return
        if not path.endswith(".xlsx"):
            path += ".xlsx"

        atlases = self._reverse_atlas_list.get_atlas_items()

        # 序列化数据用于跨线程传递
        from models.reverse_atlas_item import ReverseAtlasItem
        atlas_dicts = [a.to_dict() for a in atlases]
        result_dict = result.to_dict()

        self._reverse_report_worker = _ReverseReportWorker(
            atlas_dicts, result_dict, path, detailed
        )
        self._reverse_report_thread = QThread()
        self._reverse_report_worker.moveToThread(self._reverse_report_thread)

        self._reverse_report_worker.progress.connect(self._on_reverse_export_progress)
        self._reverse_report_worker.finished.connect(self._on_reverse_export_finished)
        self._reverse_report_worker.error.connect(self._on_reverse_export_error)
        self._reverse_report_thread.started.connect(self._reverse_report_worker.run)

        self._reverse_report_thread.start()

    def _on_reverse_export_progress(self, current: int, total: int, msg: str):
        """检查模式导出进度回调 → 底部工具栏进度条"""
        self._reverse_toolbar.set_export_progress(current, total)

    def _on_reverse_export_finished(self, file_path: str, detailed: bool):
        """检查模式导出完成"""
        self._cleanup_reverse_report_thread()
        self._reverse_toolbar.set_export_finished()
        report_type = "详细报告" if detailed else "粗略报告"
        QMessageBox.information(
            self, "导出成功",
            f"{report_type}已导出到:\n{file_path}"
        )

    def _on_reverse_export_error(self, error_msg: str):
        """检查模式导出失败"""
        self._cleanup_reverse_report_thread()
        self._reverse_toolbar.set_export_error()
        QMessageBox.critical(self, "导出失败", f"导出报告失败:\n{error_msg}")

    def _cleanup_reverse_report_thread(self):
        """清理检查模式导出线程"""
        if hasattr(self, '_reverse_report_thread') and self._reverse_report_thread:
            self._reverse_report_thread.quit()
            self._reverse_report_thread.wait(3000)
            self._reverse_report_thread.deleteLater()
            self._reverse_report_thread = None
        if hasattr(self, '_reverse_report_worker') and self._reverse_report_worker:
            self._reverse_report_worker.deleteLater()
            self._reverse_report_worker = None


class _ExcelExportWorker(QObject):
    """后台 Excel 导出 Worker（运行在 QThread 中）"""

    progress = Signal(int, int, str)   # current, total, message
    finished = Signal(str)             # file_path
    error = Signal(str)                # error message

    def __init__(self, project, file_path: str, full_mode: bool, parent=None):
        super().__init__(parent)
        self._project_data = project.to_dict()  # 序列化项目数据，避免跨线程访问
        self._file_path = file_path
        self._full_mode = full_mode

    def run(self):
        """在后台线程执行 Excel 导出"""
        try:
            from models.project_model import ProjectModel
            from services.excel_exporter import ExcelExporter

            # 从序列化数据重建项目（线程安全）
            project = ProjectModel.from_dict(self._project_data)

            def _progress_cb(current, total, msg):
                self.progress.emit(current, total, msg)

            ExcelExporter.export(
                project, self._file_path,
                full_mode=self._full_mode,
                progress_callback=_progress_cb,
            )
            self.finished.emit(self._file_path)
        except Exception as e:
            self.error.emit(str(e))


class _ReverseReportWorker(QObject):
    """检查模式报告异步导出 Worker（运行在 QThread 中）"""

    progress = Signal(int, int, str)   # current, total, message
    finished = Signal(str, bool)       # file_path, detailed
    error = Signal(str)                # error message

    def __init__(self, atlas_dicts: list, result_dict: dict,
                 file_path: str, detailed: bool, parent=None):
        super().__init__(parent)
        self._atlas_dicts = atlas_dicts
        self._result_dict = result_dict
        self._file_path = file_path
        self._detailed = detailed

    def run(self):
        """在后台线程执行检查模式报告导出"""
        try:
            from models.reverse_atlas_item import ReverseAtlasItem
            from models.duplicate_result import DuplicateResult
            from services.reverse_excel_exporter import ReverseExcelExporter

            # 从序列化数据重建对象（线程安全）
            atlases = [ReverseAtlasItem.from_dict(d) for d in self._atlas_dicts]
            result = DuplicateResult.from_dict(self._result_dict)

            def _progress_cb(current, total, msg):
                self.progress.emit(current, total, msg)

            ReverseExcelExporter.export(
                atlases, result, self._file_path,
                detailed=self._detailed,
                progress_callback=_progress_cb,
            )
            self.finished.emit(self._file_path, self._detailed)
        except Exception as e:
            self.error.emit(str(e))


class _AnalysisWorker(QObject):
    """重复检测后台 Worker（运行在 QThread 中）"""

    progress = Signal(int, int, str)   # current, total, message
    finished = Signal(object)          # DuplicateResult or None (if cancelled)
    error = Signal(str)                # error message

    def __init__(self, atlases, mode, min_tier_size=64, parent=None):
        super().__init__(parent)
        self._atlases = atlases
        self._mode = mode
        self._min_tier_size = min_tier_size
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        """在后台线程执行重复检测"""
        try:
            from services.duplicate_detector import DuplicateDetector

            def _progress_cb(current, total, msg):
                self.progress.emit(current, total, msg)

            def _cancel_check():
                return self._cancelled

            result = DuplicateDetector.detect(
                atlases=self._atlases,
                mode=self._mode,
                min_tier_size=self._min_tier_size,
                progress_callback=_progress_cb,
                cancel_check=_cancel_check,
            )

            if self._cancelled:
                self.finished.emit(None)
            else:
                self.finished.emit(result)

        except Exception as e:
            self.error.emit(str(e))
