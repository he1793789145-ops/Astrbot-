# -*- coding: utf-8 -*-
"""怪物猎人 自动配装器 —— 搜索引擎（Python 参考实现 / 命令行版）

数据来源（data/ 目录，用户提供的游戏数据导出）：
    armor.json        1586 件防具（头/胸/手/腰/腿），含技能、孔位、耐性
    normal_decos.json 244 种装饰品（1~4 级孔），每种提供一个技能
    equip_skills.json 147 个技能表（名称、等级上限、各级效果）

核心算法：
    1. 候选剪枝：按「目标技能贡献 + 孔位」签名对同部位去重（同签名只留防御/耐性最优的一件）
    2. 五部位 DFS，三层剪枝：单技能可达上限 / 全局技能点上限 / 孔位容量下限
    3. 叶子求解「装饰品覆盖」：把还缺的技能点用现有孔位补满（记忆化最小花费搜索）
    4. 结果按 综合 / 防御优先 / 剩余孔位优先 三种口径排序

用法示例：
    python engine.py --skill 攻击=4 --skill 看破=3 --skill 弱点特效=3 --skill 超会心=3 --top 5
    python engine.py --skill 挑战者=5 --weapon-slots 4,2,0 --charm 攻击=2 --charm-slots 3,1
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

PARTS: Tuple[str, ...] = ("head", "chest", "arm", "waist", "leg")
PART_CN = {"head": "头", "chest": "胸", "arm": "手", "waist": "腰", "leg": "腿"}
SORT_MODES = ("balanced", "defense", "slots")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
INF = 10 ** 9


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #
@dataclass
class ArmorPiece:
    idx: int                     # 在防具列表中的下标（唯一标识）
    arm_id: int
    part: str
    name: str
    gender: str                  # both / male / female
    defense: int
    rarity: int
    slots: Tuple[int, ...]       # 孔位等级，降序，如 (3, 1)
    skills: Dict[int, int]       # skill_id -> 等级
    resist: Tuple[int, ...]      # 火水冰雷龙
    series: str

    @property
    def slot_cap(self) -> int:
        return sum(self.slots)


@dataclass
class Deco:
    idx: int
    deco_id: int
    name: str
    lv: int                      # 需要的孔等级
    skill_id: int
    points: int                  # 提供的技能点数
    materials: Tuple[Tuple[str, int], ...]


@dataclass
class SearchOptions:
    targets: Dict[int, int] = field(default_factory=dict)   # skill_id -> 目标等级
    gender: str = "both"                                    # both / male / female
    min_rarity: int = 1
    excluded: Sequence[int] = ()                            # 排除的防具 idx
    weapon_slots: Tuple[int, ...] = ()                      # 武器孔位等级，如 (4, 2, 0)
    charm_skills: Dict[int, int] = field(default_factory=dict)
    charm_slots: Tuple[int, ...] = ()                       # 护石孔位等级
    top_n: int = 20
    sort_mode: str = "balanced"                             # balanced / defense / slots
    time_limit_ms: int = 4000
    pool_size: int = 0                                      # 结果池大小（0 = 按 top_n 自动）
    max_nodes: int = 1_500_000


@dataclass
class Build:
    pieces: List[ArmorPiece]
    slot_plan: List[Tuple[int, Optional[Deco]]]   # (孔等级, 装饰品 或 None=空孔)
    totals: Dict[int, int]                        # 全部技能（含非目标技能）
    defense: int
    resist: Tuple[int, ...]
    leftover: int                                 # 未使用孔位的等级和
    excess: int                                   # 目标技能溢出点数
    sort_score: float = 0.0

    @property
    def decos_used(self) -> List[Deco]:
        return [d for _, d in self.slot_plan if d is not None]

    def achieved(self, sid: int) -> int:
        return self.totals.get(sid, 0)


@dataclass
class SearchResult:
    builds: List[Build]
    feasible: bool
    nodes: int
    elapsed_ms: int
    truncated: bool
    best_effort: bool = False
    skill_caps: Dict[int, int] = field(default_factory=dict)   # 无解时单技能理论上限
    found: int = 0                                            # 搜索中命中的可行方案总数
    pool_size: int = 0                                        # 结果池大小


# --------------------------------------------------------------------------- #
# 数据加载
# --------------------------------------------------------------------------- #
def load_dataset(data_dir: str = DATA_DIR) -> Dict[str, object]:
    with open(os.path.join(data_dir, "equip_skills.json"), encoding="utf-8") as f:
        raw_skills = json.load(f)
    skills: Dict[int, Dict[str, object]] = {}
    for v in raw_skills.values():
        skills[int(v["id"])] = {
            "name": v["name"],
            "max": int(v["max_level"]),
            "category": v.get("category", ""),
            "levels": [d["description"] for d in v.get("levelDescriptions", [])],
        }

    with open(os.path.join(data_dir, "normal_decos.json"), encoding="utf-8") as f:
        raw_decos = json.load(f)
    decos: List[Deco] = []
    for _, v in sorted(raw_decos.items(), key=lambda kv: int(kv[0])):
        for sk in v["skills"]:
            decos.append(Deco(
                idx=len(decos),
                deco_id=int(v["id"]),
                name=v["name"],
                lv=int(v["decoration_lv"]),
                skill_id=int(sk["id"]),
                points=int(sk["level"]),
                materials=tuple((m["name"], int(m["count"])) for m in v.get("crafting_materials", [])),
            ))

    with open(os.path.join(data_dir, "armor.json"), encoding="utf-8") as f:
        raw_armor = json.load(f)["armor"]
    armor: List[ArmorPiece] = []
    for i, e in enumerate(raw_armor):
        r = e.get("resistances", {})
        armor.append(ArmorPiece(
            idx=i,
            arm_id=int(e["id"]),
            part=e["part"],
            name=e["name"],
            gender=e.get("gender", "both"),
            defense=int(e.get("defense", 0)),
            rarity=int(e.get("rarity", 1)),
            slots=tuple(sorted((int(x) for x in e.get("decorations", []) if int(x) > 0), reverse=True)),
            skills={int(sk["id"]): int(sk["level"]) for sk in e.get("skills", [])},
            resist=tuple(int(r.get(k2, 0)) for k2 in ("fire", "water", "ice", "thunder", "dragon")),
            series=e.get("series_name", ""),
        ))

    name2id = {v["name"]: k for k, v in skills.items()}
    return {"skills": skills, "decos": decos, "armor": armor, "name2id": name2id}


# --------------------------------------------------------------------------- #
# 搜索引擎
# --------------------------------------------------------------------------- #
class Optimizer:
    def __init__(self, dataset: Dict[str, object]):
        self.skills: Dict[int, Dict[str, object]] = dataset["skills"]        # type: ignore
        self.decos: List[Deco] = dataset["decos"]                             # type: ignore
        self.armor: List[ArmorPiece] = dataset["armor"]                       # type: ignore
        self.name2id: Dict[str, int] = dataset["name2id"]                     # type: ignore

        # 装饰品选项：skill_id -> [(孔等级, 技能点, deco_idx)]，按"每点占用孔等级"升序
        opts: Dict[int, List[Tuple[int, int, int]]] = {}
        for d in self.decos:
            opts.setdefault(d.skill_id, []).append((d.lv, d.points, d.idx))
        for lst in opts.values():
            lst.sort(key=lambda t: (-t[1] / t[0], -t[1], t[0]))
        self.deco_opts = opts

        # 某等级孔位能提供的最大技能点数
        self.max_pts_by_slot: Dict[int, int] = {
            lv: max([d.points for d in self.decos if d.lv <= lv] or [0]) for lv in range(0, 5)
        }
        # 某技能在某等级孔位中能提供的最大点数
        self._skill_slot_best: Dict[Tuple[int, int], int] = {}
        for sid, lst in opts.items():
            for lv in range(0, 5):
                self._skill_slot_best[(sid, lv)] = max([p for l, p, _ in lst if l <= lv] or [0])

        self._cover_cache: Dict[Tuple, Optional[Tuple[int, Tuple]]] = {}

    # ---------------- 装饰品覆盖求解 ----------------
    def cover(self, needs: Dict[int, int], slots: Sequence[int]) -> Optional[Tuple[int, Tuple]]:
        """用 slots（孔等级序列）补满 needs（技能 -> 还缺点数）。

        返回 (占用孔等级和, ((孔等级, deco_idx), ...))，无解返回 None。
        每个装饰品占一个孔（孔等级 >= 装饰品等级），装饰品数量不限。
        """
        need_key = tuple(sorted((k, v) for k, v in needs.items() if v > 0))
        if not need_key:
            return (0, ())
        slot_tuple = tuple(sorted((s for s in slots if s > 0), reverse=True))
        ck = (need_key, slot_tuple)
        if ck in self._cover_cache:
            return self._cover_cache[ck]

        memo: Dict[Tuple, Optional[Tuple[int, Tuple]]] = {}

        def rec(need: Tuple[Tuple[int, int], ...], avail: Tuple[int, ...]):
            if not need:
                return (0, ())
            key = (need, avail)
            if key in memo:
                return memo[key]
            # 先处理"缺口最大、可选装饰品最少"的技能
            sid, pts = max(need, key=lambda x: (x[1], -len(self.deco_opts.get(x[0], ()))))
            best: Optional[Tuple[int, Tuple]] = None
            for slvl, sp, di in self.deco_opts.get(sid, ()):
                pos = -1                          # 能放下该装饰品的最小孔
                for i in range(len(avail) - 1, -1, -1):
                    if avail[i] >= slvl:
                        pos = i
                        break
                if pos < 0:
                    continue
                used = avail[pos]
                rest = avail[:pos] + avail[pos + 1:]
                nxt = dict(need)
                nxt[sid] = pts - sp
                new_need = tuple(sorted((k, v) for k, v in nxt.items() if v > 0))
                sub = rec(new_need, rest)
                if sub is None:
                    continue
                cost = used + sub[0]
                if best is None or cost < best[0]:
                    best = (cost, ((used, di),) + sub[1])
            memo[key] = best
            return best

        out = rec(need_key, slot_tuple)
        self._cover_cache[ck] = out
        return out

    def cover_best_effort(self, needs: Dict[int, int], slots: Sequence[int]):
        """尽力覆盖（贪婪，不回溯）：返回 (方案, 剩余孔位)"""
        avail = sorted((s for s in slots if s > 0), reverse=True)
        plan: List[Tuple[int, Optional[Deco]]] = []
        for sid, _ in sorted(needs.items(), key=lambda kv: -kv[1]):
            while needs.get(sid, 0) > 0:
                placed = False
                for slvl, sp, di in self.deco_opts.get(sid, ()):
                    pos = -1
                    for i in range(len(avail) - 1, -1, -1):
                        if avail[i] >= slvl:
                            pos = i
                            break
                    if pos < 0:
                        continue
                    used = avail.pop(pos)
                    plan.append((used, self.decos[di]))
                    needs[sid] -= sp
                    placed = True
                    break
                if not placed:
                    break
        return plan, avail

    # ---------------- 主搜索 ----------------
    def search(self, opt: SearchOptions) -> SearchResult:
        t0 = time.perf_counter()
        skills = self.skills

        tgt: Dict[int, int] = {}
        for sid, lv in opt.targets.items():
            if sid in skills and int(lv) > 0:
                tgt[sid] = min(int(lv), int(skills[sid]["max"]))
        if not tgt:
            return SearchResult([], False, 0, 0, False)

        sid_list = sorted(tgt)
        m = len(sid_list)
        pos = {s: i for i, s in enumerate(sid_list)}
        tgt_vec = [tgt[s] for s in sid_list]
        max_need = max(tgt_vec)

        # 每个技能补 n 点"最少需要多少孔位容量"（无界背包放松，用于快速排除）
        min_cap: Dict[int, List[int]] = {}
        for s in sid_list:
            dp = [0] + [INF] * max_need
            for n in range(1, max_need + 1):
                best = INF
                for slvl, pts, _ in self.deco_opts.get(s, ()):
                    best = min(best, slvl + dp[max(0, n - pts)])
                dp[n] = best
            min_cap[s] = dp

        excluded = set(opt.excluded)
        base_slots = [l for l in list(opt.weapon_slots) + list(opt.charm_slots) if l > 0]
        base_vec = [0] * m
        for sid, lv in opt.charm_skills.items():
            if sid in pos and int(lv) > 0:
                base_vec[pos[sid]] += int(lv)

        # ---- 1) 候选防具：按（目标技能贡献, 孔位）签名去重 ----
        sig_best: Dict[Tuple[str, Tuple], ArmorPiece] = {}
        for piece in self.armor:
            if piece.idx in excluded:
                continue
            if piece.gender != "both" and piece.gender != opt.gender:
                continue
            if piece.rarity < opt.min_rarity:
                continue
            vec = tuple(piece.skills.get(s, 0) for s in sid_list)
            key = (piece.part, (vec, piece.slots))
            cur = sig_best.get(key)
            if cur is None or (piece.defense, sum(piece.resist)) > (cur.defense, sum(cur.resist)):
                sig_best[key] = piece
        cands: Dict[str, List[ArmorPiece]] = {p: [] for p in PARTS}
        for (part, _sig), piece in sig_best.items():
            cands[part].append(piece)

        mode = opt.sort_mode

        def cand_key(piece: ArmorPiece):
            pts = sum(piece.skills.get(s, 0) for s in sid_list)
            if mode == "defense":
                return (-piece.defense, -pts, -piece.slot_cap)
            if mode == "slots":
                return (-piece.slot_cap, -pts, -piece.defense)
            return (-(pts * 3 + piece.slot_cap * 2.5 + piece.defense * 0.05), -piece.defense)

        for p in PARTS:
            cands[p].sort(key=cand_key)

        order = sorted(PARTS, key=lambda p: len(cands[p]))
        if any(len(cands[p]) == 0 for p in PARTS):
            return SearchResult([], False, 0, int((time.perf_counter() - t0) * 1000), False,
                                skill_caps=self._skill_caps(tgt, base_slots))

        n = len(order)
        # ---- 2) 后缀上界（剪枝用） ----
        suf_pts = [0] * (n + 1)                       # 剩余部位能提供的目标技能点
        suf_slotcap = [0] * (n + 1)                   # 剩余部位能提供的孔位容量
        suf_skill = [[0] * m for _ in range(n + 1)]   # 单技能：剩余部位最高等级
        suf_slotskill = [[0] * m for _ in range(n + 1)]
        for k in range(n - 1, -1, -1):
            lst = cands[order[k]]
            suf_pts[k] = max(sum(pc.skills.get(s, 0) for s in sid_list) for pc in lst) + suf_pts[k + 1]
            suf_slotcap[k] = max(sum(pc.slots) for pc in lst) + suf_slotcap[k + 1]
            for i, s in enumerate(sid_list):
                suf_skill[k][i] = max(pc.skills.get(s, 0) for pc in lst) + suf_skill[k + 1][i]
                suf_slotskill[k][i] = max(sum(self._skill_slot_best.get((s, l), 0) for l in pc.slots)
                                          for pc in lst) + suf_slotskill[k + 1][i]

        # ---- 3) DFS ----
        # 候选扁平化成数组，并可预先算好「这件装备的孔位能给各技能补多少点」
        ssb = [[self._skill_slot_best.get((s, lv), 0) for lv in range(5)] for s in sid_list]
        part_vec: List[List[Tuple[int, ...]]] = []
        part_pot: List[List[Tuple[int, ...]]] = []
        part_cap: List[List[int]] = []
        part_pc: List[List[ArmorPiece]] = []
        for part in order:
            lst = cands[part]
            part_vec.append([tuple(pc.skills.get(s, 0) for s in sid_list) for pc in lst])
            part_pot.append([tuple(sum(ssb[i][l] for l in pc.slots) for i in range(m)) for pc in lst])
            part_cap.append([sum(pc.slots) for pc in lst])
            part_pc.append(list(lst))

        results: List[Build] = []
        pool_keys: List[Tuple] = []
        pool_size = opt.pool_size if opt.pool_size > 0 else max(200, opt.top_n * 20)
        found = [0]
        st = {"nodes": 0, "stop": False}
        time_limit = opt.time_limit_ms / 1000.0
        min_cap_i = [min_cap[s] for s in sid_list]
        rng_m = range(m)
        chosen: List[Optional[ArmorPiece]] = [None] * len(PARTS)
        tot = list(base_vec)
        avail: List[int] = list(base_slots)
        cap_now = sum(base_slots)
        pot_now = [sum(ssb[i][l] for l in base_slots) for i in rng_m]

        def make_build(plan: List[Tuple[int, Optional[Deco]]], leftover: int) -> Build:
            full: Dict[int, int] = {}
            for sid, lv in opt.charm_skills.items():
                if int(lv) > 0:
                    full[sid] = full.get(sid, 0) + int(lv)
            pieces = [pc for pc in chosen if pc is not None]
            for pc in pieces:
                for s, lv in pc.skills.items():
                    full[s] = full.get(s, 0) + lv
            for _lv, d in plan:
                if d is not None:
                    full[d.skill_id] = full.get(d.skill_id, 0) + d.points
            excess = sum(max(0, full.get(s, 0) - w) for s, w in tgt.items())
            defense = sum(pc.defense for pc in pieces)
            resist = tuple(sum(pc.resist[i] for pc in pieces) for i in range(5))
            b = Build(pieces=pieces, slot_plan=plan, totals=full, defense=defense, resist=resist,
                      leftover=leftover, excess=excess)
            b.sort_score = 0.5 * defense + 6.0 * leftover + 0.3 * sum(resist) - 2.0 * excess
            return b

        def key_of(b: Build) -> Tuple:
            if mode == "defense":
                return (-b.defense, -b.leftover, b.excess)
            if mode == "slots":
                return (-b.leftover, -b.defense, b.excess)
            return (-b.sort_score, -b.defense, b.excess)

        def push_result(b: Build) -> None:
            """按排序口径二分插入结果池（降序），只保留最优的 pool_size 个"""
            found[0] += 1
            key = key_of(b)
            lo, hi = 0, len(pool_keys)
            while lo < hi:
                mid = (lo + hi) // 2
                if pool_keys[mid] <= key:
                    lo = mid + 1
                else:
                    hi = mid
            if lo >= pool_size:
                return
            results.insert(lo, b)
            pool_keys.insert(lo, key)
            if len(results) > pool_size:
                results.pop()
                pool_keys.pop()

        def leaf() -> None:
            need: Dict[int, int] = {}
            total_need = 0
            cap_need = 0
            for i in rng_m:
                d = tgt_vec[i] - tot[i]
                if d > 0:
                    if d > pot_now[i]:
                        return
                    need[sid_list[i]] = d
                    total_need += d
                    cap_need += min_cap_i[i][d]
            if total_need > cap_now or cap_need > cap_now:
                return
            res = self.cover(need, avail) if need else (0, ())
            if res is None:
                return
            _cost, assignment = res
            free_slots = sorted(avail, reverse=True)
            plan: List[Tuple[int, Optional[Deco]]] = []
            for lv, di in assignment:
                free_slots.remove(lv)
                plan.append((lv, self.decos[di]))
            for lv in free_slots:
                plan.append((lv, None))
            plan.sort(key=lambda t: (-t[0], t[1] is not None))
            push_result(make_build(plan, sum(free_slots)))

        def dfs(k: int) -> None:
            nonlocal cap_now
            if st["stop"]:
                return
            st["nodes"] += 1
            if (st["nodes"] & 1023) == 0:
                if st["nodes"] >= opt.max_nodes or (time.perf_counter() - t0) > time_limit:
                    st["stop"] = True
                    return
            # —— 内部节点剪枝：单技能上限 + 孔位容量下限 ——
            need_total = 0
            cap_need = 0
            for i in rng_m:
                d = tgt_vec[i] - tot[i] - suf_skill[k][i]
                if d > 0:
                    if d > pot_now[i] + suf_slotskill[k][i]:
                        return
                    need_total += d
                    cap_need += min_cap_i[i][d]
            if need_total > cap_now + suf_slotcap[k] or cap_need > cap_now + suf_slotcap[k]:
                return
            slot_idx = PARTS.index(order[k])
            vecs, pots, caps, pcs = part_vec[k], part_pot[k], part_cap[k], part_pc[k]
            last = (k + 1 == n)
            for c in range(len(pcs)):
                v = vecs[c]
                for i in rng_m:
                    tot[i] += v[i]
                p = pots[c]
                for i in rng_m:
                    pot_now[i] += p[i]
                cl = caps[c]
                cap_now += cl
                for l in pcs[c].slots:
                    avail.append(l)
                chosen[slot_idx] = pcs[c]
                if last:
                    leaf()
                else:
                    dfs(k + 1)
                chosen[slot_idx] = None
                for l in pcs[c].slots:
                    avail.pop()
                cap_now -= cl
                for i in rng_m:
                    pot_now[i] -= p[i]
                for i in rng_m:
                    tot[i] -= v[i]
                if st["stop"]:
                    return

        dfs(0)

        elapsed = int((time.perf_counter() - t0) * 1000)
        truncated = st["stop"]
        if not results:
            caps = self._skill_caps(tgt, base_slots)
            be = self._best_effort(tgt, cands, order, base_vec, sid_list, base_slots, tgt_vec)
            return SearchResult([be] if be else [], False, st["nodes"], elapsed, truncated, True, caps,
                                found[0], pool_size)

        return SearchResult(results[:opt.top_n], True, st["nodes"], elapsed, truncated,
                            found=found[0], pool_size=pool_size)

    # ---------------- 无解时的诊断 / 兜底 ----------------
    def _skill_caps(self, tgt: Dict[int, int], base_slots: Sequence[int]) -> Dict[int, int]:
        """单技能理论上限：各部位该技能最高等级之和 + 孔位最多能补的点（按 4 级孔宽松估算）"""
        best_slots_n = 0
        for part in PARTS:
            best_slots_n += max((len(pc.slots) for pc in self.armor if pc.part == part), default=0)
        slots_n = best_slots_n + sum(1 for l in base_slots if l > 0)
        caps: Dict[int, int] = {}
        for s in tgt:
            armor_max = 0
            for part in PARTS:
                armor_max += max((pc.skills.get(s, 0) for pc in self.armor if pc.part == part), default=0)
            deco_max = slots_n * self._skill_slot_best.get((s, 4), 0)
            caps[s] = min(int(self.skills[s]["max"]), armor_max + deco_max)
        return caps

    def _best_effort(self, tgt, cands, order, base_vec, sid_list, base_slots, tgt_vec):
        """束搜索兜底：最大化已满足的目标等级，兼顾孔位与防御。"""
        WIDTH = 1500
        m = len(sid_list)
        beam: List[Tuple[List[int], List[int], List[ArmorPiece]]] = [(list(base_vec), list(base_slots), [])]
        for k, part in enumerate(order):
            nxt = []
            for tot_v, slots_v, picks in beam:
                for piece in cands[part][:400]:
                    nt = list(tot_v)
                    for s, lv in piece.skills.items():
                        if s in tgt:
                            nt[sid_list.index(s)] += lv
                    nxt.append((nt, slots_v + [l for l in piece.slots if l > 0], picks + [piece]))
            if len(nxt) > WIDTH:
                nxt.sort(key=lambda it: (
                    -sum(min(it[0][i], tgt_vec[i]) for i in range(m)) * 100
                    - sum(it[1]) * 3 - sum(pc.defense for pc in it[2]) * 0.05))
                nxt = nxt[:WIDTH]
            beam = nxt
        best = None
        for tot_v, slots_v, picks in beam:
            need = {s: tgt[s] - tot_v[i] for i, s in enumerate(sid_list) if tgt[s] - tot_v[i] > 0}
            plan, rest = self.cover_best_effort(dict(need), slots_v)
            full: Dict[int, int] = {}
            for pc in picks:
                for s, lv in pc.skills.items():
                    full[s] = full.get(s, 0) + lv
            for lv, d in plan:
                full[d.skill_id] = full.get(d.skill_id, 0) + d.points
            score = sum(min(full.get(s, 0), w) for s, w in tgt.items())
            if best is None or score > best[0]:
                b = Build(pieces=picks, slot_plan=plan + [(lv, None) for lv in rest], totals=full,
                          defense=sum(pc.defense for pc in picks),
                          resist=tuple(sum(pc.resist[i] for pc in picks) for i in range(5)),
                          leftover=sum(rest),
                          excess=sum(max(0, full.get(s, 0) - w) for s, w in tgt.items()))
                best = (score, b)
        return best[1] if best else None


# --------------------------------------------------------------------------- #
# 命令行
# --------------------------------------------------------------------------- #
def parse_skill_args(items: Sequence[str], name2id: Dict[str, int]) -> Dict[int, int]:
    out: Dict[int, int] = {}
    for it in items or ():
        if "=" in it:
            k, v = it.split("=", 1)
        elif ":" in it:
            k, v = it.split(":", 1)
        else:
            k, v = it, "1"
        k = k.strip()
        sid = int(k) if k.isdigit() else name2id.get(k)
        if sid is None:
            raise SystemExit(f"未知技能：{k}")
        out[sid] = out.get(sid, 0) + int(v)
    return out


def fmt_build(build: Build, skills: Dict[int, Dict[str, object]], targets: Dict[int, int]) -> str:
    lines = [f"  防御力 {build.defense}   剩余孔位容量 {build.leftover}   溢出点数 {build.excess}"
             f"   耐性 火{build.resist[0]} 水{build.resist[1]} 冰{build.resist[2]} "
             f"雷{build.resist[3]} 龙{build.resist[4]}"]
    for part in PARTS:
        pc = next((p for p in build.pieces if p.part == part), None)
        if pc is None:
            continue
        sk = "、".join(f"{skills[s]['name']}{l}" for s, l in pc.skills.items())
        slots = "".join(f"【{l}】" for l in pc.slots) or "无孔"
        lines.append(f"    {PART_CN[part]}：{pc.name}  {slots}  {sk}")
    used = [(lv, d) for lv, d in build.slot_plan if d]
    if used:
        lines.append("    镶嵌：" + "、".join(f"【{lv}】{d.name}" for lv, d in used))
    free = [lv for lv, d in build.slot_plan if not d]
    if free:
        lines.append("    空孔：" + "".join(f"【{lv}】" for lv in free))
    tot = sorted(build.totals.items(), key=lambda x: (x[0] not in targets, -x[1]))
    lines.append("    技能：" + "、".join(
        f"{skills[s]['name']}{l}{'*' if s in targets else ''}" for s, l in tot))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="怪物猎人自动配装器（命令行）")
    ap.add_argument("--skill", action="append", default=[], help="目标技能，如 攻击=4（可重复）")
    ap.add_argument("--gender", default="both", choices=["both", "male", "female"])
    ap.add_argument("--min-rarity", type=int, default=1, help="最低稀有度（9+ 基本为大师装备）")
    ap.add_argument("--weapon-slots", default="", help="武器孔位，如 4,2,0")
    ap.add_argument("--charm", action="append", default=[], help="护石技能，如 攻击=2")
    ap.add_argument("--charm-slots", default="", help="护石孔位，如 3,1")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--sort", default="balanced", choices=list(SORT_MODES))
    ap.add_argument("--time-limit", type=int, default=4000, help="搜索时间上限（毫秒）")
    ap.add_argument("--data", default=DATA_DIR)
    args = ap.parse_args(argv)

    ds = load_dataset(args.data)
    opt = Optimizer(ds)
    skills = ds["skills"]
    targets = parse_skill_args(args.skill, ds["name2id"])
    if not targets:
        print("请用 --skill 指定目标技能，例如：--skill 攻击=4 --skill 看破=3")
        return 1

    def slots(s):
        return tuple(int(x) for x in s.split(",") if x.strip()) if s else ()

    res = opt.search(SearchOptions(
        targets=targets,
        gender=args.gender,
        min_rarity=args.min_rarity,
        weapon_slots=slots(args.weapon_slots),
        charm_skills=parse_skill_args(args.charm, ds["name2id"]),
        charm_slots=slots(args.charm_slots),
        top_n=args.top,
        sort_mode=args.sort,
        time_limit_ms=args.time_limit,
    ))
    print("目标：" + "、".join(f"{skills[s]['name']}{l}" for s, l in targets.items()))
    print(f"搜索：{res.nodes} 节点 / {res.elapsed_ms} ms / 命中 {res.found} 个可行方案"
          + (f"（保留最优 {res.pool_size} 个）" if res.found > res.pool_size else "")
          + (" / 预算内截断" if res.truncated else " / 已穷尽")
          + ("" if res.feasible else " / 未找到完全满足的方案"))
    for i, b in enumerate(res.builds, 1):
        print(f"\n{'=' * 60}\n方案 {i}" + (" [尽力而为，未完全满足目标]" if res.best_effort else ""))
        print(fmt_build(b, skills, targets))
    if not res.feasible and res.skill_caps:
        print("\n当前约束下单技能理论上限：")
        for s, cap in sorted(res.skill_caps.items(), key=lambda x: -x[1]):
            print(f"    {skills[s]['name']}：最多 {cap} 级（目标 {targets[s]} 级）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
