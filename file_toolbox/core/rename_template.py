"""重命名操作模板管理服务。持久化为 rename_templates.json,支持保存/加载常用操作组合。"""

import json
from datetime import datetime
from pathlib import Path


class RenameTemplateService:
    """重命名模板服务"""

    def __init__(self, config_path: str = "rename_templates.json"):
        """
        初始化模板服务

        Args:
            config_path: 配置文件路径
        """
        self.config_path = Path(config_path)
        self._templates = None  # 延迟加载，使用时才读取

    @property
    def templates(self) -> dict[str, dict]:
        """延迟加载模板"""
        if self._templates is None:
            self._templates = self._load_templates()
        return self._templates

    @templates.setter
    def templates(self, value: dict[str, dict]):
        """设置模板"""
        self._templates = value

    def _load_templates(self) -> dict[str, dict]:
        """加载模板配置"""
        if not self.config_path.exists():
            return {}

        try:
            with open(self.config_path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_templates(self):
        """保存模板配置"""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.templates, f, ensure_ascii=False, indent=2)
        except OSError as e:
            raise Exception(f"保存模板失败: {e!s}") from e

    def add_template(self, name: str, operations: list[dict], description: str = "") -> bool:
        """
        添加模板

        Args:
            name: 模板名称
            operations: 操作列表
            description: 描述

        Returns:
            是否成功
        """
        if not name or not operations:
            return False

        if name in self.templates:
            return False  # 模板已存在

        self.templates[name] = {
            "operations": operations,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        self._save_templates()
        return True

    def update_template(self, name: str, operations: list[dict], description: str = "") -> bool:
        """
        更新模板

        Args:
            name: 模板名称
            operations: 操作列表
            description: 描述

        Returns:
            是否成功
        """
        if name not in self.templates:
            return False

        self.templates[name]["operations"] = operations
        self.templates[name]["description"] = description
        self.templates[name]["updated_at"] = datetime.now().isoformat()

        self._save_templates()
        return True

    def delete_template(self, name: str) -> bool:
        """
        删除模板

        Args:
            name: 模板名称

        Returns:
            是否成功
        """
        if name not in self.templates:
            return False

        del self.templates[name]
        self._save_templates()
        return True

    def get_template(self, name: str) -> dict | None:
        """
        获取模板

        Args:
            name: 模板名称

        Returns:
            模板数据或None
        """
        return self.templates.get(name)

    def get_all_templates(self) -> list[dict]:
        """
        获取所有模板

        Returns:
            模板列表
        """
        result = []
        for name, data in self.templates.items():
            result.append(
                {
                    "name": name,
                    "operations": data["operations"],
                    "description": data.get("description", ""),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                }
            )

        # 按更新时间倒序排序
        result.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return result

    def template_exists(self, name: str) -> bool:
        """检查模板是否存在"""
        return name in self.templates

    def rename_template(self, old_name: str, new_name: str) -> bool:
        """
        重命名模板

        Args:
            old_name: 原名称
            new_name: 新名称

        Returns:
            是否成功
        """
        if old_name not in self.templates or new_name in self.templates:
            return False

        self.templates[new_name] = self.templates.pop(old_name)
        self.templates[new_name]["updated_at"] = datetime.now().isoformat()

        self._save_templates()
        return True

    def clear_all(self):
        """清空所有模板"""
        self.templates = {}
        self._save_templates()

    def export_template(self, name: str, file_path: str) -> bool:
        """
        导出单个模板到文件

        Args:
            name: 模板名称
            file_path: 导出文件路径

        Returns:
            是否成功
        """
        template = self.get_template(name)
        if not template:
            return False

        try:
            export_data = {"template_name": name, "template_data": template}
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            return True
        except OSError:
            return False

    def import_template(self, file_path: str) -> str | None:
        """
        从文件导入模板

        Args:
            file_path: 导入文件路径

        Returns:
            导入的模板名称或None
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)

            name = data.get("template_name")
            template_data = data.get("template_data")

            if not name or not template_data:
                return None

            # 如果模板已存在，添加后缀
            original_name = name
            counter = 1
            while name in self.templates:
                name = f"{original_name}_{counter}"
                counter += 1

            self.templates[name] = template_data
            self.templates[name]["updated_at"] = datetime.now().isoformat()
            self._save_templates()

            return name
        except (OSError, json.JSONDecodeError):
            return None
