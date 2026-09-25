# -*- coding: utf-8 -*-
"""
怪物猎人配装器 - AstrBot 插件

支持 OneBot v11 平台，通过 QQ 聊天进行自动配装。

用法：
    /配装 攻击=4 看破=3 弱点特效=3 超会心=3
    /配装 攻击=4 看破=3 --weapon 4,2,0 --top 5
    /配装模板 物理输出
    /帮助

错误处理：
    - 参数错误：回复用户错误信息
    - 环境错误：回复错误信息 + 通知管理员
    - 截图失败：降级为纯文本卡片

依赖：
    pip install playwright
    playwright install chromium

作者：OpenSquilla
协议：MIT
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# AstrBot 插件框架（运行时注入）
try:
    from astrbot.plugin import Plugin
    from astrbot.manager import manager
    from astrbot.types import MessageSegment, MessageEvent
    HAS_ASTRBOT = True
except ImportError:
    HAS_ASTRBOT = False

# 引擎（从原项目导入）
try:
    import engine as MH_engine
    from engine import SearchOptions, Optimizer, load_dataset, fmt_build
    HAS_ENGINE = True
except ImportError:
    HAS_ENGINE = False

# 配置
CONFIG_PATH = Path(__file__).parent / "config.yaml"
DATA_DIR = Path(__file__).parent / "data"
TEMPLATE_DIR = Path(__file__).parent / "templates"

# 默认配置
DEFAULT_CONFIG = {
    "top_n": 3,
    "sort_mode": "balanced",
    "time_limit_ms": 4000,
    "min_rarity": 1,
    "admin_qq": "",
    "playwright_timeout": 30000,
}


class MHRicePlugin:
    """怪物猎人配装器 AstrBot 插件"""

    def __init__(self):
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

    async def handle_message(self, event: Any) -> None:
        """处理消息事件"""
        if not HAS_ASTRBOT:
            return

        message = event.message
        text = "".join([str(seg) for seg in message if isinstance(seg, str)])

        cmd = self._parse_command(text)
        if not cmd:
            return

        try:
            result = await self._execute_command(cmd, event)
            await self._send_result(result, event)
        except Exception as e:
            await self._notify_admin(f"插件错误：{str(e)}\n事件：{event}")
            await self._send_error(str(e), event)

    def _parse_command(self, text: str) -> Optional[dict]:
        """解析命令"""
        text = text.strip()

        if text.startswith("@"):
            parts = text.split()
            if len(parts) > 1:
                text = " ".join(parts[1:])
            else:
                return None

        if text.startswith("/"):
            parts = text[1:].split()
            if not parts:
                return None
            cmd_name = parts[0].lower()
            args = parts[1:]
            return {"cmd": cmd_name, "args": args}

        return None

    async def _execute_command(self, cmd: dict, event: Any) -> dict:
        """执行命令"""
        cmd_name = cmd["cmd"]
        args = cmd["args"]

        if cmd_name == "配装":
            return await self._handle_plan(args, event)
        elif cmd_name == "模板":
            return self._handle_templates(args)
        elif cmd_name == "帮助" or cmd_name == "help":
            return self._handle_help()
        else:
            raise ValueError(f"未知命令：/{cmd_name}。使用 /帮助 查看可用命令。")

    async def _handle_plan(self, args: list, event: Any) -> dict:
        """处理 /配装 命令"""
        self._load_engine()

        targets = {}
        weapon_slots = ()
        charm_skills = {}
        charm_slots = ()
        top_n = self.config["top_n"]
        sort_mode = self.config["sort_mode"]
        min_rarity = self.config["min_rarity"]
        gender = "both"
        excluded = []

        i = 0
        while i < len(args):
            arg = args[i]
            if "=" in arg:
                parts = arg.split("=")
                if len(parts) == 2:
                    skill_name = parts[0].strip()
                    try:
                        level = int(parts[1].strip())
                    except ValueError:
                        raise ValueError(f"技能等级必须是整数：{arg}")
                    name2id = self.dataset["name2id"]
                    if skill_name not in name2id:
                        raise ValueError(f"未知技能：{skill_name}。使用 /帮助 查看可用技能。")
                    sid = name2id[skill_name]
                    targets[sid] = targets.get(sid, 0) + level
            elif arg == "--weapon":
                if i + 1 < len(args):
                    slots_str = args[i + 1]
                    weapon_slots = tuple(int(x) for x in slots_str.split(",") if x.strip())
                    i += 1
            elif arg == "--charm":
                if i + 1 < len(args):
                    charm_arg = args[i + 1]
                    if "=" in charm_arg:
                        parts = charm_arg.split("=")
                        skill_name = parts[0].strip()
                        level = int(parts[1].strip())
                        name2id = self.dataset["name2id"]
                        if skill_name not in name2id:
                            raise ValueError(f"未知护石技能：{skill_name}")
                        sid = name2id[skill_name]
                        charm_skills[sid] = charm_skills.get(sid, 0) + level
                    i += 1
            elif arg == "--charm-slots":
                if i + 1 < len(args):
                    charm_slots = tuple(int(x) for x in args[i + 1].split(",") if x.strip())
                    i += 1
            elif arg == "--top":
                if i + 1 < len(args):
                    top_n = int(args[i + 1])
                    i += 1
            elif arg == "--sort":
                if i + 1 < len(args):
                    sort_mode = args[i + 1]
                    if sort_mode not in ("balanced", "defense", "slots"):
                        raise ValueError(f"无效排序方式：{sort_mode}。可选：balanced, defense, slots")
                    i += 1
            elif arg == "--min-rarity":
                if i + 1 < len(args):
                    min_rarity = int(args[i + 1])
                    i += 1
            elif arg == "--gender":
                if i + 1 < len(args):
                    gender = args[i + 1]
                    if gender not in ("both", "male", "female"):
                        raise ValueError(f"无效性别：{gender}。可选：both, male, female")
                    i += 1
            elif arg == "--exclude":
                if i + 1 < len(args):
                    exclude_name = args[i + 1]
                    armor_list = self.dataset["armor"]
                    found = False
                    for idx, armor in enumerate(armor_list):
                        if armor["name"] == exclude_name:
                            excluded.append(idx)
                            found = True
                            break
                    if not found:
                        raise ValueError(f"未找到装备：{exclude_name}")
                    i += 1

            i += 1

        if not targets:
            raise ValueError("请指定目标技能，例如：/配装 攻击=4 看破=3")

        opt = SearchOptions(
            targets=targets,
            gender=gender,
            min_rarity=min_rarity,
            weapon_slots=weapon_slots,
            charm_skills=charm_skills,
            charm_slots=charm_slots,
            top_n=top_n,
            sort_mode=sort_mode,
            time_limit_ms=self.config["time_limit_ms"],
            excluded=excluded,
        )

        res = self.optimizer.search(opt)

        if not res.feasible:
            raise ValueError("没有找到可行方案。请尝试降低技能目标或调整其他参数。")

        return {
            "builds": res.builds[:top_n],
            "search_time_ms": res.elapsed_ms,
            "targets": targets,
            "gender": gender,
            "weapon_slots": weapon_slots,
        }

    def _handle_templates(self, args: list) -> dict:
        """处理 /配装模板 命令"""
        templates = {
            "物理输出": {
                "targets": {"攻击": 4, "看破": 3, "弱点特效": 3, "超会心": 3},
                "weapon_slots": (4, 2, 0),
            },
            "生存向": {
                "targets": {"体力强化": 3, "防御强化": 3, "耐性强化": 3},
                "weapon_slots": (0, 0, 0),
            },
            "属性异常": {
                "targets": {"属性强化": 4, "属性攻击": 4, "异常状态强化": 3},
                "weapon_slots": (2, 2, 0),
            },
        }

        if not args:
            return {"templates": list(templates.keys())}

        template_name = args[0]
        if template_name not in templates:
            raise ValueError(f"未知模板：{template_name}。可用模板：{', '.join(templates.keys())}")

        return {"template": template_name, "config": templates[template_name]}

    def _handle_help(self) -> dict:
        """处理 /帮助 命令"""
        return {
            "commands": {
                "/配装": "发起配装请求，例如：/配装 攻击=4 看破=3 弱点特效=3 超会心=3",
                "/配装模板": "使用预设模板，例如：/配装模板 物理输出",
                "/帮助": "显示帮助信息",
            },
            "options": {
                "--weapon": "武器孔位，如 4,2,0",
                "--charm": "护石技能，如 攻击=2",
                "--charm-slots": "护石孔位，如 3,1",
                "--top": "返回 Top N 个方案（默认 3）",
                "--sort": "排序方式：balanced/defense/slots",
                "--min-rarity": "最低稀有度（默认 1）",
                "--gender": "性别：both/male/female",
                "--exclude": "排除装备，如 --exclude 炎火装束【头巾】",
            },
        }

    async def _send_result(self, result: dict, event: Any) -> None:
        """发送结果"""
        if "builds" in result:
            await self._render_and_send_builds(result["builds"], result, event)
        elif "templates" in result:
            await self._send_text(f"可用模板：{', '.join(result['templates'])}", event)
        elif "template" in result:
            template_config = result["config"]
            targets = template_config["targets"]
            weapon_slots = template_config.get("weapon_slots", ())

            args = []
            for skill_name, level in targets.items():
                args.append(f"{skill_name}={level}")
            if weapon_slots:
                args.append("--weapon")
                args.append(",".join(str(s) for s in weapon_slots))

            cmd = {"cmd": "配装", "args": args}
            final_result = await self._execute_command(cmd, event)
            await self._render_and_send_builds(final_result["builds"], final_result, event)
        else:
            await self._send_text(self._format_help(result), event)

    def _format_help(self, result: dict) -> str:
        """格式化帮助信息"""
        lines = [" 怪物猎人配装器帮助", ""]
        lines.append("命令：")
        for cmd, desc in result["commands"].items():
            lines.append(f"  {cmd} - {desc}")
        lines.append("")
        lines.append("选项：")
        for opt, desc in result["options"].items():
            lines.append(f"  {opt} - {desc}")
        return "\n".join(lines)

    async def _render_and_send_builds(self, builds: list, context: dict, event: Any) -> None:
        """渲染配装结果并发送"""
        try:
            images = await asyncio.to_thread(
                self._render_build_images, builds, context
            )
            await self._send_forward_msg(event, images)
        except Exception as e:
            await self._send_text_builds(builds, context, event)

    def _render_build_images(self, builds: list, context: dict) -> List[str]:
        """渲染配装卡片图片（Playwright）"""
        images = []
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Playwright 未安装：请运行 pip install playwright && playwright install chromium")

        template_path = TEMPLATE_DIR / "build_card.html"
        if not template_path.exists():
            raise FileNotFoundError(f"模板文件不存在：{template_path}")

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            for i, build in enumerate(builds):
                html_content = self._fill_template(template_path, build, context, i + 1)
                page.set_content(html_content)

                img_path = f"_build_{i + 1}.png"
                page.screenshot(path=img_path, full_page=False)
                images.append(img_path)

            browser.close()

        return images

    def _fill_template(self, template_path: Path, build, context: dict, index: int) -> str:
        """填充模板"""
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()

        skills_html = ""
        for sid, lv in build.totals.items():
            skill = context["skills"].get(sid, {})
            name = skill.get("name", "未知技能")
            is_target = sid in context["targets"]
            marker = "*" if is_target else ""
            skills_html += f'<span class="skill{marker}">{name}{lv}{marker}</span> '

        armor_html = ""
        for part in ("head", "chest", "arm", "waist", "leg"):
            pc = next((p for p in build.pieces if p.part == part), None)
            if pc:
                slots = "".join(f"【{l}】" for l in pc.slots) or "无孔"
                sk = "、".join(f"{context['skills'].get(s, {}).get('name', '?')}{l}" for s, l in pc.skills.items())
                armor_html += f'<div class="piece">{part}: {pc.name} {slots} {sk}</div>\n'

        deco_html = ""
        used = [(lv, d) for lv, d in build.slot_plan if d]
        if used:
            deco_html = "、".join(f"【{lv}】{d.name}" for lv, d in used)

        html = template.replace("{{INDEX}}", str(index))
        html = html.replace("{{DEFENSE}}", str(build.defense))
        html = html.replace("{{LEFTOVER}}", str(build.leftover))
        html = html.replace("{{EXCESS}}", str(build.excess))
        html = html.replace("{{SKILLS}}", skills_html)
        html = html.replace("{{ARMOR}}", armor_html)
        html = html.replace("{{DECOS}}", deco_html)

        return html

    async def _send_forward_msg(self, event: Any, images: List[str]) -> None:
        """发送合并转发消息"""
        if not HAS_ASTRBOT:
            return

        try:
            messages = []
            for img_path in images:
                with open(img_path, "rb") as f:
                    img_data = f.read()
                messages.append(MessageSegment.image(img_data))
                os.remove(img_path)

            # 实际实现需要用 OneBot 的 send_forward_msg API
            await self._send_text("（图片消息）", event)
        except Exception as e:
            await self._send_text(f"发送图片失败：{str(e)}", event)

    async def _send_text_builds(self, builds: list, context: dict, event: Any) -> None:
        """降级为纯文本发送"""
        lines = ["🎮 怪物猎人配装结果", ""]
        for i, build in enumerate(builds):
            lines.append(f"--- 方案 {i + 1} ---")
            lines.append(f"防御力：{build.defense} | 剩余孔位：{build.leftover} | 溢出：{build.excess}")
            for part in ("head", "chest", "arm", "waist", "leg"):
                pc = next((p for p in build.pieces if p.part == part), None)
                if pc:
                    slots = "".join(f"【{l}】" for l in pc.slots) or "无孔"
                    sk = "、".join(f"{context['skills'].get(s, {}).get('name', '?')}{l}" for s, l in pc.skills.items())
                    lines.append(f"  {part}: {pc.name} {slots} {sk}")
            used = [(lv, d) for lv, d in build.slot_plan if d]
            if used:
                lines.append(f"  镶嵌：{'、'.join(f'【{lv}】{d.name}' for lv, d in used)}")
            lines.append("")

        await self._send_text("\n".join(lines), event)

    async def _send_error(self, error_msg: str, event: Any) -> None:
        """发送错误信息给用户"""
        if not HAS_ASTRBOT:
            return
        await self._send_text(f"❌ 错误：{error_msg}", event)

    async def _send_text(self, text: str, event: Any) -> None:
        """发送文本消息"""
        if not HAS_ASTRBOT:
            return
        print(f"[{getattr(event, 'group_id', 'unknown')}] {text}")

    async def _notify_admin(self, message: str) -> None:
        """通知管理员"""
        admin_qq = self.config.get("admin_qq")
        if not admin_qq:
            return

        print(f"[管理员通知] {admin_qq}: {message}")


# AstrBot 插件注册
if HAS_ASTRBOT:
    plugin = MHRicePlugin()

    @manager.plugin
    class MHRiceBuilderPlugin(Plugin):
        name = "MHRiceBuilder"
        desc = "怪物猎人配装器"
        usage = "/配装 攻击=4 看破=3"

        async def handle(self, message: Any) -> None:
            await plugin.handle_message(message)
