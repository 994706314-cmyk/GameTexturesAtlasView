# -*- mode: python ; coding: utf-8 -*-
"""TexturesAtlasView PyInstaller spec file"""

import os

block_cipher = None

# 项目根目录
ROOT = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(ROOT, 'main.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[
        # 样式资源
        (os.path.join(ROOT, 'styles', 'dark_theme.qss'), 'styles'),
        (os.path.join(ROOT, 'styles', 'light_theme.qss'), 'styles'),
        (os.path.join(ROOT, 'styles', 'check.svg'), 'styles'),
        # 图标资源
        (os.path.join(ROOT, 'assets', 'icon.ico'), 'assets'),
        (os.path.join(ROOT, 'assets', 'icon.png'), 'assets'),
    ],
    hiddenimports=[
        # PySide6 必要模块
        'PySide6.QtWidgets',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtSvg',
        # 项目内部模块
        'models',
        'models.texture_item',
        'models.placed_texture',
        'models.atlas_model',
        'models.project_model',
        'models.reverse_atlas_item',
        'models.duplicate_result',
        'services',
        'services.animation_engine',
        'services.atlas_segmenter',
        'services.bin_packer',
        'services.duplicate_detector',
        'services.excel_exporter',
        'services.file_service',
        'services.global_hotkey',
        'services.image_service',
        'services.reverse_excel_exporter',
        'services.screenshot_service',
        'services.undo_manager',
        'services.undo_redo',
        'services.update_service',
        'views',
        'views.main_window',
        'views.atlas_editor_view',
        'views.atlas_outline_panel',
        'views.library_panel',
        'views.reverse_atlas_list_panel',
        'views.reverse_import_panel',
        'views.reverse_toolbar',
        'views.reverse_viewer',
        'views.screenshot_overlay',
        'views.settings_dialog',
        'views.size_edit_dialog',
        'views.texture_graphics_item',
        'views.toolbar_widget',
        'views.update_dialog',
        'utils',
        'utils.constants',
        'utils.validators',
        # 第三方隐式依赖 — Pillow C 扩展
        'PIL',
        'PIL.Image',
        'PIL._imaging',
        'PIL._imagingcms',
        'PIL._imagingft',
        'PIL._imagingmath',
        'PIL._imagingmorph',
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.utils',
        'numpy',
        'cv2',
        'imagehash',
        'scipy',
        'scipy.fftpack',
        'pywt',
        'ctypes',
        'ctypes.wintypes',
        'json',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的大模块
        'tkinter',
        'matplotlib',
        'test',
        # 'unittest',  # imagehash 依赖 unittest.mock，不能排除
        'xmlrpc',
        'lib2to3',
        # 'pydoc',  # imagehash 依赖链需要 pydoc，不能排除
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='TexturesAtlasView',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI 程序不显示控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, 'assets', 'icon.ico'),
)
