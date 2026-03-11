# GameTexturesAtlasView

🎮 **游戏合图规划/检查工具** — 一站式 Atlas 贴图管理与规划可视化工具

## ✨ 功能特性

- 📦 **合图规划** — 可视化拖拽排列贴图，智能自动装箱（Bin Packing）
- 🔍 **Atlas 分割检查** — 导入已有合图，自动分割并检查子贴图
- 🔄 **逆向合图** — 从 Excel 配置表逆向还原合图结构
- 📊 **Excel 报告导出** — 一键导出合图规划/检查结果为 Excel 表
- 🖼️ **截图功能** — 框选区域截图，快速保存工作成果
- 🔁 **撤销/重做** — 完整的操作历史管理
- 📐 **多尺寸支持** — 支持 256~8192 等多种 Atlas 尺寸
- 🎨 **明暗主题** — 深色/浅色主题自由切换
- 🔄 **自动更新** — 启动时静默检查 GitHub Releases 新版本

## 📥 下载使用

前往 [Releases](https://github.com/994706314-cmyk/GameTexturesAtlasView/releases) 页面下载最新版 `TexturesAtlasView.exe`，双击即可运行（无需安装 Python 环境）。

## 🛠️ 开发环境

- Python 3.10+
- PySide6 (Qt6)
- PyInstaller（打包）

```bash
pip install -r requirements.txt
python main.py
```

## 📁 项目结构

```
├── main.py                  # 程序入口
├── models/                  # 数据模型
├── views/                   # UI 视图
├── services/                # 业务逻辑服务
├── utils/                   # 工具常量
├── styles/                  # QSS 主题样式
├── assets/                  # 图标资源
└── TexturesAtlasView.spec   # PyInstaller 打包配置
```

## 👨‍💻 开发者

**Euanliang** — V1.5
