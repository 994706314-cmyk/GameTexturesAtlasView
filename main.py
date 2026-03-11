"""TexturesAtlasView - 游戏合图规划工具"""

import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QPixmap

from utils.constants import get_base_dir


def load_stylesheet(theme: str = "dark") -> str:
    """加载全局 QSS 样式表
    
    Args:
        theme: 主题名称，"dark" 为规划模式深色主题，"light" 为检查模式浅色主题
    """
    styles_dir = os.path.join(get_base_dir(), "styles")
    qss_file = "dark_theme.qss" if theme == "dark" else "light_theme.qss"
    qss_path = os.path.join(styles_dir, qss_file)
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            qss = f.read()
        qss = qss.replace("{STYLES_DIR}", styles_dir.replace("\\", "/"))
        return qss
    return ""


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("TexturesAtlasView")
    app.setOrganizationName("TexturesAtlasView")

    # 设置应用图标（优先使用 PNG 以获得更好的透明度支持）
    base_dir = get_base_dir()
    icon = QIcon()
    png_path = os.path.join(base_dir, "assets", "icon.png")
    ico_path = os.path.join(base_dir, "assets", "icon.ico")
    if os.path.exists(png_path):
        pixmap = QPixmap(png_path)
        # 添加多种尺寸以确保 Windows 任务栏 / 标题栏 / Alt+Tab 都正常显示
        for sz in [16, 24, 32, 48, 64, 128, 256]:
            icon.addPixmap(pixmap.scaled(sz, sz, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        app.setWindowIcon(icon)
    elif os.path.exists(ico_path):
        app.setWindowIcon(QIcon(ico_path))

    font = QFont("PingFang SC", 10)
    font.setFamilies(["PingFang SC", "Microsoft YaHei UI", "Segoe UI"])
    app.setFont(font)

    stylesheet = load_stylesheet()
    if stylesheet:
        app.setStyleSheet(stylesheet)

    from views.main_window import MainWindow
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
