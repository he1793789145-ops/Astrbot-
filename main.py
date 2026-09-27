# -*- coding: utf-8 -*-
"""
怪物猎人配装器 - AstrBot 插件 (图片输出版)

支持 OneBot v11 平台，通过 QQ 聊天进行自动配装，输出精美图片卡片。

用法：
    /配装 攻击=4 看破=3 弱点特效=3 超会心=3
    /配装模板 物理输出
    /帮助

依赖：
    pip install playwright
    playwright install chromium
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ========== AstrBot 框架导入 ==========
try:
    from astrbot.api.star import Star
    from astrbot.api.event import AstrMessageEvent, MessageChain, filter
    from astrbot.api import logger, message_components as Comp
    HAS_ASTRBOT = True
except ImportError:
    Star = object  # type: ignore
    HAS_ASTRBOT = False

# ========== 引擎导入 ==========
_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

try:
    import engine as MH_engine
    from engine import SearchOptions, Optimizer, load_dataset, fmt_build
    HAS_ENGINE = True
except ImportError:
    HAS_ENGINE = False

# ========== 配置 ==========
CONFIG_PATH = Path(__file__).parent / "config.yaml"
DATA_DIR = Path(__file__).parent / "data"
TEMPLATE_DIR = Path(__file__).parent / "templates"

DEFAULT_CONFIG = {
    "top_n": 3,
    "sort_mode": "balanced",
    "time_limit_ms": 4000,
    "min_rarity": 1,
    "admin_qq": "",
    "playwright_timeout": 30000,
    "output_mode": "image",  # image / text
}

# 部位中文名
PART_CN = {"head": "头", "chest": "胸", "arm": "手", "waist": "腰", "leg": "腿"}

# 预设模板
TEMPLATES = {
    "物理输出": {"攻击": 4, "看破": 3, "弱点特效": 3, "超会心": 3},
    "生存向": {"耐性强化": 3, "防御强化": 3, "回血": 2},
    "异常状态": {"中毒": 3, "麻药": 3, "睡眠": 3},
}


class Main(Star):
    """怪物猎人配装器 AstrBot 插件"""

    def __init__(self, **kwargs):
        self.config = self._load_config()
        self.dataset = None
        self.optimizer = None

    def _load_config(self) -> dict:
        """加载配置文件"""
        config = DEFAULT_CONFIG.copy()
        if CONFIG_PATH.exists():
            try:
                import yaml
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    user_config = yaml.safe_load(f) or {}
                config.update(user_config)
            except ImportError:
                try:
                    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                        user_config = json.load(f)
                    config.update(user_config)
                except Exception:
                    pass
        return config

    def _load_engine(self):
        """懒加载引擎"""
        if self.dataset is None:
            if not HAS_ENGINE:
                raise RuntimeError("引擎未安装：请确保 engine.py 在插件目录中")
            self.dataset = load_dataset(str(DATA_DIR))
            self.optimizer = Optimizer(self.dataset)

    def _plain(self, event: AstrMessageEvent, text: str):
        """发送纯文本回复 - 返回 MessageEventResult，由调用者 yield"""
        if text is None:
            text = ""
        if event is not None:
            return event.plain_result(text)
        from astrbot.core.message.message_event_result import MessageEventResult
        return MessageEventResult().message(text)

    def _extract_args(self, event: AstrMessageEvent) -> List[str]:
        """提取命令参数"""
        text = (getattr(event, "message_str", "") or "").strip()
        if not text:
            return []
        raw = text.lstrip("/").lstrip("／").strip()
        if not raw:
            return []
        parts = raw.split(maxsplit=1)
        if len(parts) > 1:
            return parts[1].strip().split()
        return []

    # ========== 截图功能（异步 Playwright）==========

    def _check_playwright(self) -> bool:
        """检查 Playwright 是否可用"""
        try:
            from playwright.async_api import async_playwright
            return True
        except ImportError:
            logger.warning("Playwright 未安装，降级为文本输出。请运行：pip install playwright && playwright install chromium")
            return False

    def _render_build_html(self, build, index: int, targets: dict) -> str:
        """渲染单套配装的 HTML"""
        skills_html = ""
        for sid, lv in sorted(build.totals.items()):
            skill = self.dataset["skills"].get(sid, {})
            name = skill.get("name", "未知技能")
            is_target = sid in targets
            marker = "★" if is_target else ""
            cls = "target" if is_target else "non-target"
            skills_html += f'<span class="skill {cls}">{name}{lv}{marker}</span> '

        armor_html = ""
        for part_key in ("head", "chest", "arm", "waist", "leg"):
            pc = next((p for p in build.pieces if p.part == part_key), None)
            if pc:
                slots = "".join(f'<span class="slot">【{l}】</span>' for l in pc.slots) or '<span class="slot-hint">无孔</span>'
                sk_items = []
                for s, l in pc.skills.items():
                    sk_name = self.dataset["skills"].get(s, {}).get("name", "?")
                    sk_items.append(f'{sk_name}{l}')
                sk = "、".join(sk_items) if sk_items else ""
                armor_html += f'<div class="piece"><div class="part">{PART_CN[part_key]}</div><div class="name">{pc.name}</div><div class="slots">{slots}</div><div class="skills">{sk}</div></div>\n'

        deco_html = ""
        used = [(lv, d) for lv, d in build.slot_plan if d]
        if used:
            deco_items = []
            for lv, d in used:
                deco_items.append(f'<span class="deco">【{lv}】{d.name}</span>')
            deco_html = " ".join(deco_items)
        else:
            deco_html = '<span class="hint">无需镶嵌</span>'

        free_slots = [lv for lv, d in build.slot_plan if d is None]
        free_html = ""
        if free_slots:
            free_items = [f'<span class="free">【{lv}】</span>' for lv in free_slots]
            free_html = " ".join(free_items)

        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif;
    background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
    color: #e0e0e0;
    padding: 20px;
    min-width: 380px;
    max-width: 420px;
}}
.header {{
    text-align: center;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 2px solid #e94560;
}}
.header h1 {{
    font-size: 20px;
    color: #e94560;
    margin-bottom: 4px;
}}
.header .sub {{
    font-size: 12px;
    color: #888;
}}
.metrics {{
    display: flex;
    gap: 8px;
    margin-bottom: 14px;
}}
.metric {{
    flex: 1;
    text-align: center;
    background: rgba(255,255,255,0.06);
    padding: 10px 6px;
    border-radius: 8px;
}}
.metric .value {{
    font-size: 22px;
    font-weight: bold;
    color: #fff;
}}
.metric .label {{
    font-size: 11px;
    color: #999;
    margin-top: 4px;
}}
.armor-list {{ margin-bottom: 12px; }}
.piece {{
    background: rgba(255,255,255,0.04);
    padding: 8px 10px;
    margin-bottom: 6px;
    border-radius: 6px;
    border-left: 3px solid #e94560;
}}
.piece .part {{
    font-size: 11px;
    color: #e94560;
    text-transform: uppercase;
    margin-bottom: 2px;
}}
.piece .name {{
    font-size: 14px;
    font-weight: bold;
    color: #fff;
    margin-bottom: 4px;
}}
.piece .slots {{ margin-bottom: 4px; }}
.slot {{
    display: inline-block;
    background: rgba(233,69,96,0.3);
    color: #e94560;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 12px;
    margin-right: 2px;
}}
.slot-hint {{
    color: #666;
    font-size: 12px;
}}
.piece .skills {{
    font-size: 12px;
    color: #aaa;
}}
.section {{
    background: rgba(255,255,255,0.04);
    padding: 10px;
    border-radius: 6px;
    margin-bottom: 10px;
}}
.section h4 {{
    font-size: 13px;
    color: #e94560;
    margin-bottom: 8px;
}}
.deco {{
    display: inline-block;
    background: rgba(233,69,96,0.15);
    padding: 3px 8px;
    border-radius: 4px;
    margin: 2px;
    font-size: 12px;
    color: #ddd;
}}
.free {{
    display: inline-block;
    background: rgba(255,255,255,0.08);
    padding: 3px 8px;
    border-radius: 4px;
    margin: 2px;
    font-size: 12px;
    color: #888;
}}
.hint {{ color: #666; font-size: 12px; }}
.skills-grid {{
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
}}
.skill {{
    display: inline-block;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 12px;
}}
.skill.target {{
    background: #e94560;
    color: #fff;
    font-weight: bold;
}}
.skill.non-target {{
    background: rgba(255,255,255,0.08);
    color: #aaa;
}}
.footer {{
    text-align: center;
    font-size: 10px;
    color: #555;
    margin-top: 12px;
    padding-top: 8px;
    border-top: 1px solid #333;
}}
</style>
</head>
<body>
<div class="header">
    <h1>🎮 怪物猎人配装器</h1>
    <div class="sub">方案 {index} · {build.defense} 防御</div>
</div>

<div class="metrics">
    <div class="metric">
        <div class="value">{build.defense}</div>
        <div class="label">防御力</div>
    </div>
    <div class="metric">
        <div class="value">{build.leftover}</div>
        <div class="label">剩余孔位</div>
    </div>
    <div class="metric">
        <div class="value">{build.excess}</div>
        <div class="label">溢出</div>
    </div>
</div>

<div class="armor-list">
{armor_html}
</div>

<div class="section">
    <h4>🔧 镶嵌与空孔</h4>
    <div>{deco_html}</div>
    {f'<div style="margin-top:6px;">{free_html}</div>' if free_html else ''}
</div>

<div class="section">
    <h4>⚔️ 技能汇总</h4>
    <div class="skills-grid">{skills_html}</div>
</div>

<div class="footer">
    怪物猎人崛起：曙光 · 自动配装器
</div>
</body>
</html>'''
        return html

    async def _prepare_image_builds(self, event, builds, targets):
        """准备图片版配装结果，返回结果列表（文本或图片）"""
        results = []
        
        # 检查 Playwright 是否可用
        if not self._check_playwright():
            # 降级为文本
            results.append(self._plain(event, self._build_text_result(builds, targets)))
            return results

        temp_dir = tempfile.mkdtemp(prefix="mhrice_")
        image_paths = []

        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                for i, build in enumerate(builds):
                    html = self._render_build_html(build, i + 1, targets)
                    img_path = os.path.join(temp_dir, f"build_{i + 1}.png")
                    page = await browser.new_page(viewport={"width": 420, "height": 800})
                    await page.set_content(html)
                    await page.wait_for_timeout(100)
                    await page.screenshot(path=img_path, full_page=True)
                    await page.close()
                    image_paths.append(img_path)
                await browser.close()

            if not image_paths:
                results.append(self._plain(event, self._build_text_result(builds, targets)))
                return results

            # 返回图片消息结果列表
            for img_path in image_paths:
                with open(img_path, "rb") as f:
                    img_data = f.read()
                results.append(event.chain_result([Comp.Image.from_bytes(img_data)]))

        except Exception as e:
            logger.error(f"图片准备失败：{e}")
            results.append(self._plain(event, self._build_text_result(builds, targets)))
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

        return results

    async def _send_image_builds(self, event, builds, targets, elapsed_ms):
        """发送图片版配装结果（合并转发）"""
        results = await self._prepare_image_builds(event, builds, targets)
        for result in results:
            yield result

    def _build_text_result(self, builds, targets):
        """构建文本版配装结果字符串"""
        try:
            res = self.optimizer.search(SearchOptions(
                targets=targets,
                top_n=len(builds),
                sort_mode=self.config["sort_mode"],
                time_limit_ms=self.config["time_limit_ms"],
            ))
            elapsed = res.elapsed_ms
        except:
            elapsed = '?'

        lines = [f"🎮 怪物猎人配装结果（{elapsed}ms）", ""]
        for i, build in enumerate(builds):
            lines.append(f"--- 方案 {i + 1} ---")
            lines.append(f"防御力：{build.defense} | 剩余孔位：{build.leftover} | 溢出：{build.excess}")
            for part in ("head", "chest", "arm", "waist", "leg"):
                pc = next((p for p in build.pieces if p.part == part), None)
                if pc:
                    slots = "".join(f"【{l}】" for l in pc.slots) or "无孔"
                    sk = "、".join(f"{self.dataset['skills'][s]['name']}{l}" for s, l in pc.skills.items())
                    lines.append(f"  {PART_CN[part]}：{pc.name} {slots} {sk}")
            used = [(lv, d) for lv, d in build.slot_plan if d]
            if used:
                lines.append(f"  镶嵌：{'、'.join(f'【{lv}】{d.name}' for lv, d in used)}")
            free = [lv for lv, d in build.slot_plan if not d]
            if free:
                lines.append(f"  空孔：{''.join(f'【{lv}】' for lv in free)}")
            lines.append("")
        return "\n".join(lines)

    # ========== 命令注册 ==========

    @filter.command("配装")
    async def cmd_plan(self, event: AstrMessageEvent):
        """处理配装命令：/配装 攻击=4 看破=3 弱点特效=3 超会心=3"""
        try:
            self._load_engine()
        except Exception as e:
            yield self._plain(event, f"❌ 引擎加载失败：{str(e)}")
            return

        # 解析技能参数
        targets = {}
        args = self._extract_args(event)
        for arg in args:
            if "=" in arg:
                name, level = arg.split("=", 1)
                name = name.strip()
                level = int(level.strip())
                skill_id = None
                for sid, skill in self.dataset["skills"].items():
                    if skill["name"] == name:
                        skill_id = sid
                        break
                if skill_id is None:
                    yield self._plain(event, f"❌ 未知技能：{name}，可用技能请发送 /帮助")
                    return
                targets[skill_id] = targets.get(skill_id, 0) + level

        if not targets:
            yield self._plain(event, "❌ 请指定目标技能，例如：攻击=4 看破=3")
            return

        # 执行搜索
        try:
            res = self.optimizer.search(SearchOptions(
                targets=targets,
                top_n=self.config["top_n"],
                sort_mode=self.config["sort_mode"],
                time_limit_ms=self.config["time_limit_ms"],
            ))
        except Exception as e:
            yield self._plain(event, f"❌ 搜索失败：{str(e)}")
            return

        builds = res.builds[:self.config["top_n"]]

        # 生成图片
        if self.config.get("output_mode", "image") == "image":
            async for result in self._send_image_builds(event, builds, targets, res.elapsed_ms):
                yield result
        else:
            yield self._plain(event, self._build_text_result(builds, targets))

    @filter.command("配装模板", alias={"模板"})
    async def cmd_template(self, event: AstrMessageEvent):
        """处理模板命令：/配装模板 物理输出"""
        args = self._extract_args(event)
        if not args:
            yield self._plain(event, "可用模板：" + "、".join(TEMPLATES.keys()))
            return

        template_name = args[0].lower()
        if template_name not in TEMPLATES:
            yield self._plain(event, f"❌ 未知模板：{template_name}，可用模板：{'、'.join(TEMPLATES.keys())}")
            return

        targets_dict = TEMPLATES[template_name]
        yield self._plain(event, f" 模板 '{template_name}'：{' '.join(f'{n}={l}' for n, l in targets_dict.items())}")

        # 自动执行配装
        try:
            self._load_engine()
        except Exception as e:
            yield self._plain(event, f"❌ 引擎加载失败：{str(e)}")
            return

        targets_parsed = {}
        for name, level in targets_dict.items():
            skill_id = None
            for sid, skill in self.dataset["skills"].items():
                if skill["name"] == name:
                    skill_id = sid
                    break
            if skill_id is None:
                yield self._plain(event, f"❌ 未知技能：{name}，可用技能请发送 /帮助")
                return
            targets_parsed[skill_id] = level

        try:
            res = self.optimizer.search(SearchOptions(
                targets=targets_parsed,
                top_n=self.config["top_n"],
                sort_mode=self.config["sort_mode"],
                time_limit_ms=self.config["time_limit_ms"],
            ))
        except Exception as e:
            yield self._plain(event, f"❌ 搜索失败：{str(e)}")
            return

        builds = res.builds[:self.config["top_n"]]

        if self.config.get("output_mode", "image") == "image":
            async for result in self._send_image_builds(event, builds, targets_parsed, res.elapsed_ms):
                yield result
        else:
            yield self._plain(event, self._build_text_result(builds, targets_parsed))

    @filter.command("帮助", alias={"help", "帮助信息"})
    async def cmd_help(self, event: AstrMessageEvent):
        """处理帮助命令：/帮助"""
        help_text = """🎮 怪物猎人配装器 帮助

命令：
/配装 攻击=4 看破=3 弱点特效=3 超会心=3  - 自定义配装（输出图片）
/配装模板 物理输出  - 使用预设模板
/帮助  - 显示帮助信息

预设模板：
- 物理输出：攻击=4 看破=3 弱点特效=3 超会心=3
- 生存向：耐性强化=3 防御强化=3 回血=2
- 异常状态：中毒=3 麻药=3 睡眠=3

配置：
- top_n: 返回方案数（默认 3）
- output_mode: 输出模式 image/text（默认 image）
"""
        yield self._plain(event, help_text)

    # ========== 辅助方法 ==========

    async def _notify_admin(self, message: str) -> None:
        """通知管理员"""
        admin_qq = self.config.get("admin_qq")
        if not admin_qq:
            return
        logger.warning(f"[管理员通知] {admin_qq}: {message}")


# AstrBot 插件注册（暴露 Main 实例）
Main = Main()
