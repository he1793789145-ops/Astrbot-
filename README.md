# 怪物猎人配装器 - AstrBot 插件

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-Plugin-green.svg)](https://github.com/AstrBotOpen/AstrBot)

怪物猎人崛起：曙光自动配装器，支持通过 QQ 聊天进行自动配装。

## 功能特性

- 🎯 **智能配装**：基于搜索引擎，自动计算最优配装方案
- 🖼️ **图片卡片**：Playwright 渲染精美配装卡片
- 📊 **合并转发**：多套方案折叠发送，不刷屏
- 🌈 **模板预设**：常用配装模板一键调用
- ⚡ **快速响应**：异步执行，不阻塞 Bot 响应

## 安装

### 1. 克隆插件

```bash
git clone https://github.com/yourusername/mhrice-astrbot-plugin.git
cd mhrice-astrbot-plugin
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. 复制数据文件

将原项目的 `data/build_data.json` 复制到插件的 `data/` 目录：

```bash
cp ../怪猎配装器/data/build_data.json data/
```

### 4. 配置管理员 QQ（可选）

编辑 `config.yaml`，设置管理员 QQ：

```yaml
admin_qq: "你的QQ号"
```

### 5. 部署到 AstrBot

将插件文件复制到 AstrBot 的插件目录：

```bash
# 假设 AstrBot 安装在 /opt/astrbot
cp -r plugin.py config.yaml templates/ data/ /opt/astrbot/plugins/mhrice_builder/
```

## 使用

### 基本配装

```
/配装 攻击=4 看破=3 弱点特效=3 超会心=3
```

### 自定义武器孔位

```
/配装 攻击=4 看破=3 --weapon 4,2,0
```

### 使用护石

```
/配装 攻击=4 看破=3 --charm 攻击=2 --charm-slots 3,1
```

### 返回更多方案

```
/配装 攻击=4 看破=3 --top 5
```

### 防御优先排序

```
/配装 攻击=4 看破=3 --sort defense
```

### 使用预设模板

```
/配装模板 物理输出
/配装模板 生存向
/配装模板 属性异常
```

### 查看帮助

```
/帮助
```

## 命令参数

| 参数 | 说明 | 示例 |
|---|---|---|
| `技能=等级` | 目标技能（必填） | `攻击=4` |
| `--weapon` | 武器孔位 | `--weapon 4,2,0` |
| `--charm` | 护石技能 | `--charm 攻击=2` |
| `--charm-slots` | 护石孔位 | `--charm-slots 3,1` |
| `--top` | 返回 Top N | `--top 5` |
| `--sort` | 排序方式 | `--sort defense` |
| `--min-rarity` | 最低稀有度 | `--min-rarity 3` |
| `--gender` | 性别 | `--gender male` |
| `--exclude` | 排除装备 | `--exclude 炎火装束【头巾】` |

## 预设模板

| 模板名 | 目标技能 | 武器孔位 |
|---|---|---|
| `物理输出` | 攻击=4, 看破=3, 弱点特效=3, 超会心=3 | 4,2,0 |
| `生存向` | 体力强化=3, 防御强化=3, 耐性强化=3 | 0,0,0 |
| `属性异常` | 属性强化=4, 属性攻击=4, 异常状态强化=3 | 2,2,0 |

## 错误处理

- **参数错误**：直接回复用户，指出问题
- **环境错误**：回复错误信息 + 通知管理员
- **截图失败**：自动降级为纯文本卡片

## 架构

```
mhrice-astrbot-plugin/
├── plugin.py          # 单文件插件（核心逻辑）
├── config.yaml        # 全局配置
├── templates/
│   └── build_card.html  # 配装卡片模板
├── data/
│   └── build_data.json  # 游戏数据
├── requirements.txt   # 依赖
├── README.md          # 使用说明
└── LICENSE            # MIT 协议
```

## 开发

### 调试

```bash
# 本地测试引擎
python -c "
import sys
sys.path.insert(0, '.')
import engine as E
from engine import SearchOptions, Optimizer

ds = E.load_dataset('data')
opt = Optimizer(ds)
res = opt.search(SearchOptions(
    targets={E.name2id['攻击']: 4, E.name2id['看破']: 3},
    top_n=3,
))
for b in res.builds:
    print(E.fmt_build(b, ds['skills'], res.targets))
"
```

### 截图测试

```bash
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.set_content(open('templates/build_card.html').read())
    page.screenshot('test.png')
    browser.close()
"
```

## 许可证

MIT License - 开源免费使用

## 贡献

欢迎提交 Issue 和 Pull Request！

## 致谢

- [AstrBot](https://github.com/AstrBotOpen/AstrBot) - OneBot v11 机器人框架
- [Playwright](https://playwright.dev/) - 浏览器自动化
- 怪物猎人崛起：曙光 游戏数据
