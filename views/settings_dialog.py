"""设置对话框：撤销步数、快捷键管理、自动映射压缩、排除后缀"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QPushButton, QFrame, QGridLayout, QKeySequenceEdit,
    QTabWidget, QWidget, QScrollArea, QCheckBox, QComboBox,
    QGroupBox, QLineEdit, QColorDialog,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QColor

from utils.constants import (
    DEFAULT_UNDO_STEPS, DEFAULT_SHORTCUTS, SHORTCUT_NAMES,
    COLOR_PRIMARY, VALID_TEXTURE_SIZES, DEFAULT_WIDTH_COMPRESS_MAP,
    DEFAULT_EXCLUDE_SUFFIXES, DEFAULT_WIDTH_COLOR_MAP,
    DEFAULT_THUMBNAIL_QUALITY, DEFAULT_SMOOTH_MODE,
    DEFAULT_ATLAS_SUFFIX, DEFAULT_FUZZY_THRESHOLD, APP_VERSION,
    DEFAULT_MIN_TIER_SIZE, REVERSE_COLOR_PRIMARY,
    GITHUB_OWNER, GITHUB_REPO,
)

import os as _os
from utils.constants import get_base_dir

_CHECK_SVG = _os.path.join(
    get_base_dir(), "styles", "check.svg"
).replace("\\", "/")

_CHECKBOX_STYLE = f"""
    QCheckBox {{ font-size: 12px; font-weight: 500; spacing: 6px; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px; border-radius: 3px;
    }}
    QCheckBox::indicator:checked {{
        image: url({_CHECK_SVG});
    }}
"""


class SettingsDialog(QDialog):
    """设置对话框"""

    settings_changed = Signal(dict)
    check_update_requested = Signal()  # 检查更新信号

    def __init__(self, current_settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setFixedSize(720, 780)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._settings = current_settings.copy()
        self._shortcut_edits = {}
        self._width_combos = {}
        self._color_buttons = {}  # {width: QPushButton} 宽度配色按钮
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        tabs = QTabWidget()
        # 不设置内联样式，由全局 QSS 主题控制

        # 通用设置
        general_tab = QWidget()
        g_layout = QVBoxLayout(general_tab)
        g_layout.setSpacing(12)

        undo_label = QLabel("撤销步数上限")
        undo_label.setStyleSheet("font-size: 12px; font-weight: 500;")
        g_layout.addWidget(undo_label)

        undo_row = QHBoxLayout()
        self._undo_spin = QSpinBox()
        self._undo_spin.setRange(10, 1000)
        self._undo_spin.setValue(self._settings.get("undo_steps", DEFAULT_UNDO_STEPS))
        self._undo_spin.setSuffix(" 步")
        # SpinBox 样式由全局 QSS 控制
        undo_row.addWidget(self._undo_spin)
        undo_row.addStretch()
        g_layout.addLayout(undo_row)

        # 缩略图清晰度
        thumb_label = QLabel("缩略图清晰度")
        thumb_label.setStyleSheet("font-size: 12px; font-weight: 500;")
        g_layout.addWidget(thumb_label)

        thumb_row = QHBoxLayout()
        self._thumb_quality_combo = QComboBox()
        self._thumb_quality_combo.addItem("标准（默认，加载更快）", "standard")
        self._thumb_quality_combo.addItem("高清（更清晰，占用更多内存）", "hd")
        self._thumb_quality_combo.setStyleSheet("""
            QComboBox {
                font-size: 11px;
            }
        """)
        current_quality = self._settings.get("thumbnail_quality", DEFAULT_THUMBNAIL_QUALITY)
        idx = self._thumb_quality_combo.findData(current_quality)
        if idx >= 0:
            self._thumb_quality_combo.setCurrentIndex(idx)
        thumb_row.addWidget(self._thumb_quality_combo)
        thumb_row.addStretch()
        g_layout.addLayout(thumb_row)

        thumb_hint = QLabel("切换清晰度后将清除缩略图缓存，下次打开项目时重新生成")
        thumb_hint.setStyleSheet("font-size: 10px;")
        thumb_hint.setProperty("class", "subtext")
        thumb_hint.setWordWrap(True)
        g_layout.addWidget(thumb_hint)

        # 流畅模式
        smooth_label = QLabel("流畅模式")
        smooth_label.setStyleSheet("font-size: 12px; font-weight: 500;")
        g_layout.addWidget(smooth_label)

        self._smooth_mode_check = QCheckBox("启用流畅模式（60~120fps 丝滑动效）")
        self._smooth_mode_check.setChecked(
            self._settings.get("smooth_mode", DEFAULT_SMOOTH_MODE)
        )
        self._smooth_mode_check.setStyleSheet(_CHECKBOX_STYLE)
        g_layout.addWidget(self._smooth_mode_check)

        smooth_hint = QLabel(
            "⚠ 开启后将启用 OpenGL 硬件加速、高帧率动画及渲染优化，\n"
            "动效更加丝滑流畅，但会占用更多 GPU 和内存资源。\n"
            "低配置设备上可能反而降低性能，请酌情开启。"
        )
        smooth_hint.setStyleSheet("font-size: 10px; color: #FF9800;")
        smooth_hint.setProperty("class", "subtext")
        smooth_hint.setWordWrap(True)
        g_layout.addWidget(smooth_hint)

        # 导入排除后缀
        exclude_group = QGroupBox("导入排除后缀")
        exclude_group.setStyleSheet("QGroupBox { font-size: 11px; }")
        ex_layout = QVBoxLayout(exclude_group)
        ex_hint = QLabel("文件名以这些后缀结尾的图片将被跳过（用逗号分隔，如 _NS,_AM）")
        ex_hint.setStyleSheet("font-size: 10px;")
        ex_hint.setProperty("class", "subtext")
        ex_hint.setWordWrap(True)
        ex_layout.addWidget(ex_hint)

        self._exclude_input = QLineEdit()
        current_excludes = self._settings.get("exclude_suffixes", DEFAULT_EXCLUDE_SUFFIXES)
        self._exclude_input.setText(",".join(current_excludes))
        self._exclude_input.setStyleSheet("QLineEdit { font-size: 11px; }")
        ex_layout.addWidget(self._exclude_input)
        g_layout.addWidget(exclude_group)

        g_layout.addStretch()
        tabs.addTab(general_tab, "通用")

        # 快捷键设置
        shortcuts_tab = QWidget()
        s_layout = QVBoxLayout(shortcuts_tab)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QWidget()
        grid = QGridLayout(scroll_content)
        grid.setSpacing(8)
        grid.setContentsMargins(4, 4, 4, 4)

        grid.addWidget(QLabel("功能"), 0, 0)
        grid.addWidget(QLabel("快捷键"), 0, 1)

        current_shortcuts = self._settings.get("shortcuts", DEFAULT_SHORTCUTS.copy())
        row = 1
        for key, default_seq in DEFAULT_SHORTCUTS.items():
            name = SHORTCUT_NAMES.get(key, key)
            name_label = QLabel(name)
            name_label.setStyleSheet("font-size: 11px;")
            grid.addWidget(name_label, row, 0)

            edit = QKeySequenceEdit(QKeySequence(current_shortcuts.get(key, default_seq)))
            edit.setStyleSheet("QKeySequenceEdit { min-height: 22px; }")
            grid.addWidget(edit, row, 1)
            self._shortcut_edits[key] = edit

            reset_btn = QPushButton("重置")
            reset_btn.setFixedWidth(50)
            reset_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none; font-size: 10px;
                }
            """)
            _default = default_seq
            reset_btn.clicked.connect(
                lambda _, e=edit, d=_default: e.setKeySequence(QKeySequence(d))
            )
            grid.addWidget(reset_btn, row, 2)
            row += 1

        grid.setRowStretch(row, 1)
        scroll.setWidget(scroll_content)
        s_layout.addWidget(scroll)
        tabs.addTab(shortcuts_tab, "快捷键")

        # 自动映射压缩设置
        compress_tab = QWidget()
        ct_layout = QVBoxLayout(compress_tab)
        ct_layout.setSpacing(10)

        self._auto_compress_check = QCheckBox("✓ 启用导入时自动映射压缩")
        self._auto_compress_check.setChecked(self._settings.get("auto_compress", True))
        self._auto_compress_check.setStyleSheet(_CHECKBOX_STYLE)
        ct_layout.addWidget(self._auto_compress_check)

        hint = QLabel("导入图片时将根据下方映射表自动设置规划尺寸\n宽度按表映射，高度默认等比例缩放")
        hint.setStyleSheet("font-size: 10px;")
        hint.setProperty("class", "subtext")
        hint.setWordWrap(True)
        ct_layout.addWidget(hint)

        # 宽度映射表
        w_group = QGroupBox("宽度压缩映射")
        w_group.setStyleSheet("QGroupBox { font-size: 11px; }")
        w_grid = QGridLayout(w_group)
        w_grid.setSpacing(6)

        w_grid.addWidget(QLabel("原始宽度"), 0, 0)
        w_grid.addWidget(QLabel("→"), 0, 1)
        w_grid.addWidget(QLabel("压缩到"), 0, 2)

        current_wmap = self._settings.get("width_compress_map", dict(DEFAULT_WIDTH_COMPRESS_MAP))
        source_sizes = [2048, 1024, 512, 256, 128, 64, 32, 16]

        for i, src in enumerate(source_sizes):
            src_label = QLabel(f"{src}")
            src_label.setStyleSheet("font-size: 11px;")
            src_label.setFixedWidth(50)
            w_grid.addWidget(src_label, i + 1, 0)

            arrow = QLabel("→")
            arrow.setFixedWidth(20)
            w_grid.addWidget(arrow, i + 1, 1)

            combo = QComboBox()
            combo.setFixedWidth(90)
            combo.setStyleSheet("QComboBox { font-size: 11px; }")
            for s in VALID_TEXTURE_SIZES:
                if s <= src:
                    combo.addItem(f"{s}", s)
            target = current_wmap.get(src, src)
            idx = combo.findData(target)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            self._width_combos[src] = combo
            w_grid.addWidget(combo, i + 1, 2)

        ct_layout.addWidget(w_group)

        # 宽度配色设置
        color_group = QGroupBox("宽度配色（用于素材库底色区分）")
        color_group.setStyleSheet("QGroupBox { font-size: 11px; }")
        c_grid = QGridLayout(color_group)
        c_grid.setSpacing(6)

        current_color_map = self._settings.get("width_color_map", dict(DEFAULT_WIDTH_COLOR_MAP))
        # JSON key 可能是字符串，统一转 int
        normalized_color_map = {}
        for k, v in current_color_map.items():
            normalized_color_map[int(k)] = v

        color_widths = [512, 256, 128, 64, 32, 16]
        for i, w in enumerate(color_widths):
            w_label = QLabel(f"{w}")
            w_label.setStyleSheet("font-size: 11px;")
            w_label.setFixedWidth(40)
            c_grid.addWidget(w_label, i // 3, (i % 3) * 2)

            color_hex = normalized_color_map.get(w, DEFAULT_WIDTH_COLOR_MAP.get(w, "#2D2D30"))
            btn = QPushButton()
            btn.setFixedSize(60, 24)
            btn.setStyleSheet(self._color_btn_style(color_hex))
            btn.setProperty("color_hex", color_hex)
            btn.clicked.connect(lambda _, b=btn, width=w: self._pick_color(b, width))
            self._color_buttons[w] = btn
            c_grid.addWidget(btn, i // 3, (i % 3) * 2 + 1)

        # 重置默认按钮
        reset_color_btn = QPushButton("重置默认配色")
        reset_color_btn.setFixedWidth(120)
        reset_color_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #999; border-radius: 4px;
                font-size: 10px; padding: 3px 8px;
            }
        """)
        reset_color_btn.clicked.connect(self._reset_default_colors)
        c_grid.addWidget(reset_color_btn, 2, 4, 1, 2, Qt.AlignmentFlag.AlignRight)

        ct_layout.addWidget(color_group)

        # 高度模式
        h_row = QHBoxLayout()
        h_label = QLabel("高度模式:")
        h_label.setStyleSheet("font-size: 11px;")
        h_row.addWidget(h_label)

        self._height_mode_combo = QComboBox()
        self._height_mode_combo.addItem("等比例（跟随宽度缩放比）", "proportional")
        self._height_mode_combo.addItem("使用独立映射表", "custom")
        self._height_mode_combo.setStyleSheet("QComboBox { font-size: 11px; }")
        current_h_mode = self._settings.get("height_compress_mode", "proportional")
        idx = self._height_mode_combo.findData(current_h_mode)
        if idx >= 0:
            self._height_mode_combo.setCurrentIndex(idx)
        h_row.addWidget(self._height_mode_combo)
        h_row.addStretch()
        ct_layout.addLayout(h_row)

        ct_layout.addStretch()
        tabs.addTab(compress_tab, "自动压缩")

        # ===== 检查模式设置 =====
        reverse_tab = QWidget()
        rv_layout = QVBoxLayout(reverse_tab)
        rv_layout.setSpacing(12)

        rv_title = QLabel("检查模式配置")
        rv_title.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {REVERSE_COLOR_PRIMARY};")
        rv_layout.addWidget(rv_title)

        # 图集后缀过滤
        suffix_group = QGroupBox("图集文件后缀过滤")
        suffix_group.setStyleSheet("QGroupBox { font-size: 11px; }")
        sf_layout = QVBoxLayout(suffix_group)
        sf_hint = QLabel("导入图集时，仅识别文件名以此后缀结尾的图片（不含扩展名）")
        sf_hint.setStyleSheet("font-size: 10px;")
        sf_hint.setProperty("class", "subtext")
        sf_hint.setWordWrap(True)
        sf_layout.addWidget(sf_hint)

        self._atlas_suffix_input = QLineEdit()
        self._atlas_suffix_input.setText(
            self._settings.get("atlas_suffix", DEFAULT_ATLAS_SUFFIX)
        )
        self._atlas_suffix_input.setPlaceholderText("例如: _MainTex")
        self._atlas_suffix_input.setStyleSheet("QLineEdit { font-size: 11px; }")
        sf_layout.addWidget(self._atlas_suffix_input)
        rv_layout.addWidget(suffix_group)

        # 模糊判定阈值
        fuzzy_group = QGroupBox("模糊判定参数")
        fuzzy_group.setStyleSheet("QGroupBox { font-size: 11px; }")
        fz_layout = QVBoxLayout(fuzzy_group)
        fz_hint = QLabel(
            "感知哈希(pHash)汉明距离阈值，值越大越容易判定为相似。\n"
            "推荐范围: 5-12，默认为 8"
        )
        fz_hint.setStyleSheet("font-size: 10px;")
        fz_hint.setProperty("class", "subtext")
        fz_hint.setWordWrap(True)
        fz_layout.addWidget(fz_hint)

        fz_row = QHBoxLayout()
        self._fuzzy_threshold_spin = QSpinBox()
        self._fuzzy_threshold_spin.setRange(1, 32)
        self._fuzzy_threshold_spin.setValue(
            self._settings.get("fuzzy_threshold", DEFAULT_FUZZY_THRESHOLD)
        )
        # SpinBox 样式由全局 QSS 控制
        fz_row.addWidget(self._fuzzy_threshold_spin)
        fz_row.addStretch()
        fz_layout.addLayout(fz_row)
        rv_layout.addWidget(fuzzy_group)

        # 最低检测档位
        tier_group = QGroupBox("重复检测最低档位")
        tier_group.setStyleSheet("QGroupBox { font-size: 11px; }")
        tier_layout = QVBoxLayout(tier_group)
        tier_hint = QLabel(
            "梯次网格检测的最小尺寸级别。档位越小检测越精细，但耗时也更长。\n"
            "默认 64×64，适合多数场景。"
        )
        tier_hint.setStyleSheet("font-size: 10px;")
        tier_hint.setProperty("class", "subtext")
        tier_hint.setWordWrap(True)
        tier_layout.addWidget(tier_hint)

        tier_row = QHBoxLayout()
        self._min_tier_combo = QComboBox()
        tier_options = [2048, 1024, 512, 256, 128, 64, 32, 16]
        for ts in tier_options:
            self._min_tier_combo.addItem(f"{ts}×{ts}", ts)
        current_min_tier = self._settings.get("min_tier_size", DEFAULT_MIN_TIER_SIZE)
        idx = self._min_tier_combo.findData(current_min_tier)
        if idx >= 0:
            self._min_tier_combo.setCurrentIndex(idx)
        self._min_tier_combo.setStyleSheet("QComboBox { font-size: 11px; }")
        tier_row.addWidget(self._min_tier_combo)
        tier_row.addStretch()
        tier_layout.addLayout(tier_row)
        rv_layout.addWidget(tier_group)

        rv_layout.addStretch()
        tabs.addTab(reverse_tab, "检查模式")

        # 关于页面
        about_tab = QWidget()
        a_layout = QVBoxLayout(about_tab)
        a_layout.setSpacing(12)
        a_layout.setContentsMargins(20, 20, 20, 20)

        # 工具名称 + 版本
        title_label = QLabel(f"合图规划工具 V{APP_VERSION}")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet(
            "font-size: 22px; font-weight: bold; padding-bottom: 4px;"
        )
        title_label.setProperty("class", "heading")
        a_layout.addWidget(title_label)

        # 开发者
        dev_label = QLabel("开发者：Euanliang")
        dev_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dev_label.setStyleSheet("font-size: 13px;")
        dev_label.setProperty("class", "subtext")
        a_layout.addWidget(dev_label)

        # 检查更新按钮
        update_row = QHBoxLayout()
        update_row.addStretch()
        self._check_update_btn = QPushButton("🔄 检查更新")
        self._check_update_btn.setFixedWidth(140)
        self._check_update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._check_update_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_PRIMARY}; color: #FFFFFF;
                border: none; border-radius: 6px;
                padding: 6px 16px; font-size: 12px; font-weight: 500;
            }}
            QPushButton:hover {{ background-color: #106EBE; }}
            QPushButton:disabled {{ background-color: #555555; color: #999999; }}
        """)
        self._check_update_btn.clicked.connect(self._on_check_update)
        update_row.addWidget(self._check_update_btn)
        update_row.addStretch()
        a_layout.addLayout(update_row)

        self._update_status_label = QLabel("")
        self._update_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_status_label.setStyleSheet("font-size: 11px; color: #999999;")
        self._update_status_label.setVisible(False)
        a_layout.addWidget(self._update_status_label)

        # 分割线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        a_layout.addWidget(separator)

        # 功能简介（可滚动）
        about_scroll = QScrollArea()
        about_scroll.setWidgetResizable(True)
        about_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        about_content = QWidget()
        about_inner = QVBoxLayout(about_content)
        about_inner.setContentsMargins(4, 4, 4, 4)
        about_inner.setSpacing(10)

        # 简短说明
        desc_label = QLabel(
            "合图规划工具用于在合图打包前对贴图素材进行可视化布局规划，\n"
            "支持拖拽排列、尺寸压缩映射、多合图管理等功能，\n"
            "帮助美术和技术同学高效完成贴图合图的前期规划工作。"
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(
            "font-size: 12px; line-height: 1.6; padding: 4px 8px;"
        )
        about_inner.addWidget(desc_label)

        # 规划模式 + 检查模式 左右并排
        modes_row = QHBoxLayout()
        modes_row.setSpacing(12)

        # 左侧 - 规划模式
        plan_frame = QFrame()
        plan_frame.setStyleSheet("""
            QFrame {
                border: 1px solid #3C3C3C;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        plan_layout_inner = QVBoxLayout(plan_frame)
        plan_layout_inner.setContentsMargins(10, 8, 10, 8)
        plan_layout_inner.setSpacing(4)

        plan_title = QLabel("📐 规划模式")
        plan_title.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {COLOR_PRIMARY}; "
            "border: none; padding: 0;"
        )
        plan_layout_inner.addWidget(plan_title)

        plan_desc = QLabel(
            "· 导入贴图素材，拖拽排列到合图画布\n"
            "· 截图添加贴图（Alt+D），快速创建占位贴图\n"
            "· 自动映射压缩、自动规划合图、撤销/重做\n"
            "· 宽度配色区分、Excel 导出（预览/完整模式）\n"
            "· 异步导出 + 进度条，导出不阻塞主界面"
        )
        plan_desc.setWordWrap(True)
        plan_desc.setStyleSheet(
            "font-size: 11px; line-height: 1.5; border: none; padding: 0;"
        )
        plan_layout_inner.addWidget(plan_desc)
        plan_layout_inner.addStretch()

        # 右侧 - 检查模式
        check_frame = QFrame()
        check_frame.setStyleSheet("""
            QFrame {
                border: 1px solid #3C3C3C;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        check_layout_inner = QVBoxLayout(check_frame)
        check_layout_inner.setContentsMargins(10, 8, 10, 8)
        check_layout_inner.setSpacing(4)

        check_title = QLabel("🔍 检查模式")
        check_title.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {REVERSE_COLOR_PRIMARY}; "
            "border: none; padding: 0;"
        )
        check_layout_inner.addWidget(check_title)

        check_desc = QLabel(
            "· 导入已合成的 Atlas 图集，梯次网格扫描\n"
            "· 跨图集重复内容检测（哈希分桶 O(N) 算法）\n"
            "· 多档位检测粒度（2048~16），自动合并同质结果\n"
            "· 彩色边框可视化标记 + Excel 分析报告导出\n"
            "· 异步导出报告 + 底部进度条，导出不阻塞界面\n"
            "· 图集列表多选、右键菜单、增量导入\n"
            "· 独立存档系统（.tcheck），与规划模式互不干扰"
        )
        check_desc.setWordWrap(True)
        check_desc.setStyleSheet(
            "font-size: 11px; line-height: 1.5; border: none; padding: 0;"
        )
        check_layout_inner.addWidget(check_desc)
        check_layout_inner.addStretch()

        modes_row.addWidget(plan_frame, 1)
        modes_row.addWidget(check_frame, 1)
        about_inner.addLayout(modes_row)

        # 分割线
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        about_inner.addWidget(sep2)

        # 更新日志
        changelog_title = QLabel("📋 更新日志")
        changelog_title.setStyleSheet("font-size: 14px; font-weight: bold; padding-top: 4px;")
        changelog_title.setProperty("class", "heading")
        about_inner.addWidget(changelog_title)

        changelog_text = QLabel(
            f"V{APP_VERSION}（2026-03-12）\n"
            "  · 修复：自动更新重启 Failed to load Python DLL 报错\n"
            "  · 根因：PyInstaller 6.x 使用 _PYI_APPLICATION_HOME_DIR\n"
            "    而非旧版 _MEIPASS2，之前清错了变量\n"
            "  · 改进：启动时自动清理残留 _MEI 临时目录\n\n"
            "V1.8.1（2026-03-12）\n"
            "  · 新增：编辑窗口点击贴图时素材库自动跳转选中\n"
            "  · 新增：素材库移除图片时编辑窗口图集同步移除\n"
            "  · 改进：拖入贴图智能放置（原位→最近空位→自动整理）\n\n"
            "V1.8.0（2026-03-12）\n"
            "  · 修复：竖条贴图设置尺寸失效 / 框选后右键移除只移除一张\n\n"
            "V1.7.0（2026-03-11）\n"
            "  · 重写：检查更新不再依赖 GitHub API（彻底解决 403 限流）"
        )
        changelog_text.setWordWrap(True)
        changelog_text.setStyleSheet(
            "font-size: 11px; line-height: 1.5; padding: 4px 8px;"
        )
        about_inner.addWidget(changelog_text)

        about_inner.addStretch()
        about_scroll.setWidget(about_content)
        a_layout.addWidget(about_scroll, 1)

        tabs.addTab(about_tab, "关于")

        layout.addWidget(tabs, 1)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("确认")
        ok_btn.setFixedWidth(80)
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_PRIMARY}; color: #FFFFFF;
                border: none; border-radius: 6px;
                padding: 6px 16px; font-weight: 500;
            }}
            QPushButton:hover {{ background-color: #106EBE; }}
        """)
        ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

    def _on_ok(self):
        shortcuts = {}
        for key, edit in self._shortcut_edits.items():
            seq = edit.keySequence().toString()
            shortcuts[key] = seq if seq else DEFAULT_SHORTCUTS[key]

        width_map = {}
        for src, combo in self._width_combos.items():
            width_map[src] = combo.currentData()

        # 解析排除后缀
        exclude_text = self._exclude_input.text().strip()
        if exclude_text:
            exclude_suffixes = [s.strip() for s in exclude_text.split(",") if s.strip()]
        else:
            exclude_suffixes = []

        # 收集宽度配色
        width_color_map = {}
        for w, btn in self._color_buttons.items():
            width_color_map[w] = btn.property("color_hex")

        result = {
            "undo_steps": self._undo_spin.value(),
            "shortcuts": shortcuts,
            "auto_compress": self._auto_compress_check.isChecked(),
            "width_compress_map": width_map,
            "height_compress_mode": self._height_mode_combo.currentData(),
            "height_compress_map": None,
            "exclude_suffixes": exclude_suffixes,
            "width_color_map": width_color_map,
            "thumbnail_quality": self._thumb_quality_combo.currentData(),
            "smooth_mode": self._smooth_mode_check.isChecked(),
            "atlas_suffix": self._atlas_suffix_input.text().strip() or DEFAULT_ATLAS_SUFFIX,
            "fuzzy_threshold": self._fuzzy_threshold_spin.value(),
            "min_tier_size": self._min_tier_combo.currentData(),
        }
        self._settings.update(result)
        self.settings_changed.emit(result)
        self.accept()

    def _pick_color(self, btn: QPushButton, width: int):
        """弹出颜色选择器让用户自定义配色"""
        current = QColor(btn.property("color_hex"))
        color = QColorDialog.getColor(current, self, f"选择宽度 {width} 的配色")
        if color.isValid():
            hex_color = color.name()
            btn.setProperty("color_hex", hex_color)
            btn.setStyleSheet(self._color_btn_style(hex_color))

    def _reset_default_colors(self):
        """重置所有配色为默认值"""
        for w, btn in self._color_buttons.items():
            default_hex = DEFAULT_WIDTH_COLOR_MAP.get(w, "#2D2D30")
            btn.setProperty("color_hex", default_hex)
            btn.setStyleSheet(self._color_btn_style(default_hex))

    @staticmethod
    def _color_btn_style(hex_color: str) -> str:
        """生成颜色按钮的样式"""
        # 根据背景亮度选择文字颜色
        c = QColor(hex_color)
        lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        text_color = "#000000" if lum > 128 else "#FFFFFF"
        return f"""
            QPushButton {{
                background-color: {hex_color}; color: {text_color};
                border: 1px solid #555555; border-radius: 4px;
                font-size: 10px;
            }}
            QPushButton:hover {{ border-color: #FFFFFF; }}
        """

    def get_settings(self) -> dict:
        return self._settings

    def _on_check_update(self):
        """点击检查更新按钮"""
        self._check_update_btn.setEnabled(False)
        self._check_update_btn.setText("检查中...")
        self._update_status_label.setVisible(True)
        self._update_status_label.setText("正在连接 GitHub...")

        from services.update_service import UpdateChecker
        from PySide6.QtCore import QThread

        self._update_checker = UpdateChecker(GITHUB_OWNER, GITHUB_REPO, APP_VERSION)
        self._update_thread = QThread()
        self._update_checker.moveToThread(self._update_thread)

        self._update_checker.check_finished.connect(self._on_check_result)
        self._update_thread.started.connect(self._update_checker.run)

        self._update_thread.start()

    def _on_check_result(self, result):
        """检查更新结果回调"""
        # 清理线程
        if hasattr(self, '_update_thread') and self._update_thread:
            self._update_thread.quit()
            self._update_thread.wait(3000)
            self._update_thread.deleteLater()
            self._update_thread = None
        if hasattr(self, '_update_checker') and self._update_checker:
            self._update_checker.deleteLater()
            self._update_checker = None

        self._check_update_btn.setEnabled(True)
        self._check_update_btn.setText("🔄 检查更新")

        if result.error:
            self._update_status_label.setText(f"❌ 检查失败: {result.error}")
            self._update_status_label.setStyleSheet("font-size: 11px; color: #F44336;")
        elif result.has_update:
            self._update_status_label.setText(
                f"🎉 发现新版本 V{result.latest_version}！"
            )
            self._update_status_label.setStyleSheet("font-size: 11px; color: #4CAF50;")
            # 弹出更新对话框
            from views.update_dialog import UpdateDialog
            dlg = UpdateDialog(result, self)
            dlg.exec()
        else:
            self._update_status_label.setText(f"✅ 当前已是最新版本 V{APP_VERSION}")
            self._update_status_label.setStyleSheet("font-size: 11px; color: #4CAF50;")
