"""文件服务：项目文件的新建/保存/加载"""

import json
from typing import Tuple, Optional

from models.project_model import ProjectModel


class FileService:
    """项目文件管理服务"""

    @staticmethod
    def new_project() -> ProjectModel:
        """创建空白项目"""
        return ProjectModel()

    @staticmethod
    def save_project(project: ProjectModel, path: str) -> Tuple[bool, str]:
        """保存项目到指定路径，返回 (成功, 消息)"""
        try:
            data = project.to_dict()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True, "保存成功"
        except Exception as e:
            return False, f"保存失败: {e}"

    @staticmethod
    def load_project(path: str) -> Tuple[Optional[ProjectModel], str]:
        """加载项目文件，返回 (项目对象或None, 消息)"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return None, "文件格式错误：根节点不是字典"

            project = ProjectModel.from_dict(data)
            return project, "加载成功"
        except json.JSONDecodeError as e:
            return None, f"JSON 解析失败: {e}"
        except Exception as e:
            return None, f"加载失败: {e}"
