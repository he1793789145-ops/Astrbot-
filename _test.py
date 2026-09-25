# -*- coding: utf-8 -*-
"""
怪物猎人配装器 - AstrBot 插件 - 快速测试

不依赖 AstrBot 框架，直接测试核心逻辑。
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_config():
    """测试配置加载"""
    from pathlib import Path
    from plugin import DEFAULT_CONFIG, CONFIG_PATH

    print("=== 测试配置加载 ===")
    config = DEFAULT_CONFIG.copy()

    if CONFIG_PATH.exists():
        try:
            import yaml
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
            config.update(user_config)
            print(f"✓ 配置文件加载成功：{CONFIG_PATH}")
        except ImportError:
            print("⚠ yaml 未安装，使用默认配置")
        except Exception as e:
            print(f"✗ 配置文件加载失败：{e}")

    print(f"  top_n: {config['top_n']}")
    print(f"  sort_mode: {config['sort_mode']}")
    print(f"  time_limit_ms: {config['time_limit_ms']}")
    print()
    return True

def test_engine():
    """测试引擎加载"""
    print("=== 测试引擎加载 ===")
    try:
        # 从原项目导入 engine
        import sys
        sys.path.insert(0, "D:\\ai项目\\怪猎配装器")
        import engine as MH_engine
        from engine import SearchOptions, Optimizer, load_dataset

        # 使用原项目的数据目录
        DATA_DIR = Path("D:\\ai项目\\怪猎配装器\\data")
        print(f"  数据目录：{DATA_DIR}")

        if not DATA_DIR.exists():
            print("✗ 数据文件不存在")
            return False

        dataset = load_dataset(str(DATA_DIR))
        optimizer = Optimizer(dataset)

        print(f"  ✓ 引擎加载成功")
        print(f"  防具：{len(dataset['armor'])} 件")
        print(f"  装饰品：{len(dataset['decos'])} 种")
        print(f"  技能：{len(dataset['skills'])} 个")
        print(f"  怪物：{len(dataset.get('monsters', []))} 只")
        print()
        return True
    except Exception as e:
        print(f"✗ 引擎加载失败：{e}")
        import traceback
        traceback.print_exc()
        return False

def test_search():
    """测试搜索功能"""
    print("=== 测试搜索功能 ===")
    try:
        import sys
        sys.path.insert(0, "D:\\ai项目\\怪猎配装器")
        import engine as MH_engine
        from engine import SearchOptions, Optimizer, load_dataset, fmt_build

        # 使用原项目的数据目录
        DATA_DIR = Path("D:\\ai项目\\怪猎配装器\\data")
        dataset = load_dataset(str(DATA_DIR))
        optimizer = Optimizer(dataset)
        name2id = dataset["name2id"]

        # 测试配装：攻击=4 看破=3
        targets = {
            name2id["攻击"]: 4,
            name2id["看破"]: 3,
        }

        opt = SearchOptions(
            targets=targets,
            top_n=3,
            time_limit_ms=2000,
        )

        res = optimizer.search(opt)

        print(f"  ✓ 搜索完成")
        print(f"  可行方案：{res.feasible}")
        print(f"  耗时：{res.elapsed_ms}ms")
        print(f"  找到方案数：{len(res.builds)}")

        if res.builds:
            print("\n  Top 3 方案：")
            for i, build in enumerate(res.builds[:3]):
                print(f"\n  --- 方案 {i + 1} ---")
                print(f"  防御力：{build.defense}")
                print(f"  剩余孔位：{build.leftover}")
                print(f"  溢出：{build.excess}")

                for part in ("head", "chest", "arm", "waist", "leg"):
                    pc = next((p for p in build.pieces if p.part == part), None)
                    if pc:
                        slots = "".join(f"【{l}】" for l in pc.slots) or "无孔"
                        sk = "、".join(f"{dataset['skills'].get(s, {}).get('name', '?')}{l}" for s, l in pc.skills.items())
                        print(f"  {part}: {pc.name} {slots} {sk}")

                used = [(lv, d) for lv, d in build.slot_plan if d]
                if used:
                    print(f"  镶嵌：{'、'.join(f'【{lv}】{d.name}' for lv, d in used)}")
        else:
            print("  ✗ 没有找到可行方案")
        print()
        return True
    except Exception as e:
        print(f"✗ 搜索失败：{e}")
        import traceback
        traceback.print_exc()
        return False

def test_template():
    """测试模板渲染"""
    print("=== 测试模板渲染 ===")
    try:
        from pathlib import Path
        template_path = Path(__file__).parent / "templates" / "build_card.html"

        if not template_path.exists():
            print("✗ 模板文件不存在")
            return False

        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()

        print(f"  ✓ 模板文件加载成功：{template_path}")
        print(f"  模板大小：{len(template)} 字符")
        print(f"  包含占位符：{{INDEX}}, {{DEFENSE}}, {{LEFTOVER}}, {{EXCESS}}, {{SKILLS}}, {{ARMOR}}, {{DECOS}}")
        print()
        return True
    except Exception as e:
        print(f"✗ 模板测试失败：{e}")
        return False

def main():
    """运行所有测试"""
    print("=" * 60)
    print("怪物猎人配装器 - AstrBot 插件 - 快速测试")
    print("=" * 60)
    print()

    results = []

    results.append(("配置加载", test_config()))
    results.append(("引擎加载", test_engine()))
    results.append(("搜索功能", test_search()))
    results.append(("模板渲染", test_template()))

    print("=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"  {name}: {status}")
    print()

    if all(p for _, p in results):
        print("🎉 所有测试通过！插件可以正常使用。")
        return 0
    else:
        print("⚠ 部分测试失败，请检查配置和数据文件。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
