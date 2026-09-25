# -*- coding: utf-8 -*-
"""
怪物猎人配装器 - AstrBot 插件

AstrBot 插件入口文件。
实际逻辑在 plugin.py 中。
"""

from pathlib import Path

# 确保插件目录在 sys.path 中
_PLUGIN_DIR = Path(__file__).parent
if str(_PLUGIN_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_PLUGIN_DIR))

# 导入核心插件类
from plugin import MHRicePlugin, plugin  # noqa: E402, F401

__all__ = ["plugin"]
