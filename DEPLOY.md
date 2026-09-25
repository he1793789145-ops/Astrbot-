# 怪物猎人配装器 - AstrBot 插件部署指南

## 插件结构

```
mhrice-astrbot-plugin/
├── __init__.py          # AstrBot 插件入口（必须）
├── plugin.py            # 核心逻辑
├── config.yaml          # 配置文件
├── templates/
│   └── build_card.html  # 截图模板
├── data/
│   └── build_data.json  # 数据文件
├── requirements.txt     # 依赖
├── README.md            # 使用说明
└── LICENSE              # MIT 协议
```

## 部署步骤

### 1. 安装依赖

```bash
pip install playwright pyyaml
playwright install chromium
```

### 2. 复制插件到 AstrBot 插件目录

```bash
# 假设 AstrBot 安装在 D:\astrbot
Copy-Item -Recurse "D:\ai项目\mhrice-astrbot-plugin\*" "D:\astrbot\plugins\mhrice-astrbot\"
```

最终目录结构：

```
D:\astrbot\plugins\mhrice-astrbot\
├── __init__.py          # ← 必须有这个文件！
├── plugin.py
├── config.yaml
├── templates\
│   └── build_card.html
└── data\
    └── build_data.json
```

### 3. 配置管理员 QQ

编辑 `config.yaml`：

```yaml
admin_qq: "1793789145"  # 你的 QQ 号
top_n: 3
sort_mode: balanced
time_limit_ms: 4000
min_rarity: 1
playwright_timeout: 30000
```

### 4. 重启 AstrBot

```bash
# 停止 AstrBot，然后重新启动
```

### 5. 在 QQ 群测试

在群里发送：

```
/配装 攻击=4 看破=3 弱点特效=3 超会心=3
```

Bot 应该回复一张图片卡片（Top 3 套配装方案）。

## 常用命令

| 命令 | 说明 |
|---|---|
| `/配装 攻击=4 看破=3` | 自定义配装 |
| `/配装 攻击=4 看破=3 --weapon 4,2,0` | 带武器孔位 |
| `/配装模板` | 列出预设模板 |
| `/配装模板 物理输出` | 使用预设模板 |
| `/帮助` | 帮助信息 |

## 常见问题

### 插件未加载

**现象**：重启 AstrBot 后，插件未出现在已加载插件列表

**排查步骤**：

1. 检查目录结构是否有 `__init__.py` 文件
2. 检查 `__init__.py` 是否正确导入 `plugin` 对象
3. 查看 AstrBot 日志，搜索 "mhrice" 或 "MHRice" 关键字

**解决方案**：

```bash
# 验证插件文件完整性
Get-ChildItem "D:\astrbot\plugins\mhrice-astrbot\" -Recurse | Select-Object FullName
```

确保有：
- `__init__.py`
- `plugin.py`
- `config.yaml`

### Playwright 截图失败

**现象**：回复"图片生成失败"或超时

**解决方案**：

```bash
# 安装 Chromium
playwright install chromium

# 验证安装
python -c "from playwright.sync_api import sync_playwright; print('OK')"
```

### 数据加载失败

**现象**：回复"数据文件不存在"

**解决方案**：

确保 `data/build_data.json` 文件存在（约 1.9 MB）

### 引擎导入失败

**现象**：日志显示 "No module named 'engine'"

**解决方案**：

插件使用 `build_data.json`（预构建数据），不需要 `engine.py`。如果仍报错，检查 `plugin.py` 中的 `HAS_ENGINE` 标志。

## 调试

### 查看 AstrBot 日志

```bash
# 查看最新日志
Get-Content "D:\astrbot\logs\astrbot.log" -Tail 50
```

### 手动测试插件导入

```bash
cd "D:\astrbot\plugins\mhrice-astrbot"
python -c "from __init__ import plugin; print('插件加载成功:', type(plugin))"
```

### 测试命令解析

```bash
python -c "
from plugin import MHRicePlugin
p = MHRicePlugin()
print(p._parse_command('/配装 攻击=4 看破=3'))
print(p._parse_command('@Bot /配装 攻击=4'))
print(p._parse_command('随便聊'))
"
```

## 卸载

```bash
Remove-Item -Recurse "D:\astrbot\plugins\mhrice-astrbot"
```

## 更新

```bash
# 备份当前配置
Copy-Item "D:\astrbot\plugins\mhrice-astrbot\config.yaml" "D:\astrbot\plugins\mhrice-astrbot\config.yaml.bak"

# 覆盖新文件
Copy-Item -Recurse "D:\ai项目\mhrice-astrbot-plugin\*" "D:\astrbot\plugins\mhrice-astrbot\"

# 恢复配置（如果需要）
Copy-Item "D:\astrbot\plugins\mhrice-astrbot\config.yaml.bak" "D:\astrbot\plugins\mhrice-astrbot\config.yaml" -Force
```

## 技术支持

- 问题反馈：管理员 QQ 1793789145
- 开源仓库：GitHub（待创建）
- 协议：MIT
