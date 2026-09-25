# -*- coding: utf-8 -*-
"""
快速验证插件是否可被 AstrBot 加载
"""
import sys
import os
from pathlib import Path

# 设置插件目录
PLUGIN_DIR = Path(__file__).parent
sys.path.insert(0, str(PLUGIN_DIR))

print("=" * 60)
print("怪物猎人配装器 - AstrBot 插件 - 快速验证")
print("=" * 60)
print()

# 1. 检查必要文件
print("=== 1. 检查必要文件 ===")
required_files = [
    "__init__.py",
    "plugin.py",
    "config.yaml",
    "templates/build_card.html",
    "data/build_data.json",
]

all_ok = True
for f in required_files:
    path = PLUGIN_DIR / f
    exists = path.exists()
    status = "✓" if exists else "✗"
    size = f"{path.stat().st_size / 1024:.1f} KB" if exists else "0 KB"
    print(f"  {status} {f} ({size})")
    if not exists:
        all_ok = False

print()

# 2. 测试导入
print("=== 2. 测试插件导入 ===")
try:
    from __init__ import plugin
    print(f"  ✓ 插件导入成功")
    print(f"  插件类型：{type(plugin).__name__}")
    print(f"  插件实例：{plugin}")
except Exception as e:
    print(f"  ✗ 插件导入失败：{e}")
    import traceback
    traceback.print_exc()
    all_ok = False

print()

# 3. 测试配置加载
print("=== 3. 测试配置加载 ===")
try:
    from plugin import DEFAULT_CONFIG, CONFIG_PATH
    config = DEFAULT_CONFIG.copy()
    
    if CONFIG_PATH.exists():
        try:
            import yaml
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
            config.update(user_config)
            print(f"  ✓ 配置文件加载：{CONFIG_PATH}")
        except ImportError:
            try:
                import json
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
                config.update(user_config)
                print(f"  ⚠ yaml 未安装，使用 json 解析")
            except Exception as e:
                print(f"  ⚠ 配置文件加载失败：{e}")
    
    print(f"  top_n: {config['top_n']}")
    print(f"  sort_mode: {config['sort_mode']}")
    print(f"  admin_qq: {config['admin_qq']}")
except Exception as e:
    print(f"  ✗ 配置加载失败：{e}")
    all_ok = False

print()

# 4. 测试命令解析
print("=== 4. 测试命令解析 ===")
try:
    p = plugin if hasattr(plugin, '_parse_command') else None
    if p is None:
        from plugin import MHRicePlugin
        p = MHRicePlugin()
    
    tests = [
        ("/配装 攻击=4 看破=3", {"cmd": "配装", "args": ["攻击=4", "看破=3"]}),
        ("/配装 攻击=4 看破=3 --weapon 4,2,0", {"cmd": "配装", "args": ["攻击=4", "看破=3", "--weapon", "4,2,0"]}),
        ("@Bot /配装 攻击=4", {"cmd": "配装", "args": ["攻击=4"]}),
        ("随便聊", None),
    ]
    
    for text, expected in tests:
        result = p._parse_command(text)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{text}' → {result}")
        if result != expected:
            all_ok = False
except Exception as e:
    print(f"  ✗ 命令解析测试失败：{e}")
    all_ok = False

print()

# 5. 总结
print("=" * 60)
if all_ok:
    print("✓ 插件验证通过！可以部署到 AstrBot")
    print()
    print("部署步骤：")
    print("  1. 复制整个目录到 AstrBot 插件目录")
    print("  2. 确保有 __init__.py 文件")
    print("  3. 配置 config.yaml 中的 admin_qq")
    print("  4. 重启 AstrBot")
    print("  5. 在 QQ 群发送 /配装 攻击=4 看破=3 测试")
else:
    print("✗ 插件验证失败，请检查上述错误")

print("=" * 60)
