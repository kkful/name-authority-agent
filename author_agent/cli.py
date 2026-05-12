"""CLI 入口 — 命令行 + Claude Code 集成"""

import sys
import json
import os
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        _usage()
        return

    cmd = sys.argv[1]

    if cmd == "init":
        _cmd_init()
    elif cmd == "extract":
        _cmd_extract()
    elif cmd == "check":
        _cmd_check()
    elif cmd == "export":
        _cmd_export()
    elif cmd == "pipeline":
        _cmd_pipeline()
    elif cmd == "batch":
        _cmd_batch(sys.argv[2:])
    else:
        print(f"未知命令: {cmd}")
        _usage()


def _usage():
    print("""author_agent — 名称规范记录智能体

用法:
  python -m author_agent.cli init              初始化工作目录和配置文件
  python -m author_agent.cli extract <文本>    从文本提取结构化字段（返回prompt）
  python -m author_agent.cli check             检查质量（扫描待补全的记录）
  python -m author_agent.cli export            导出 Excel（dedup-librecord 就绪）
  python -m author_agent.cli pipeline          交互式流水线
  python -m author_agent.cli batch <姓名>:<机构> [<姓名>:<机构> ...]  批量搜捕
""")


def _cmd_init():
    from .config import WORK_DIR, OUTPUT_DIR
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 生成默认 config.yaml
    config_path = WORK_DIR / "config.yaml"
    if not config_path.exists():
        import yaml
        cfg = {
            "LLM_PROVIDER": "claude",
            "LLM_MODEL": "claude-sonnet-4-6",
            "SEARCH_SOURCES": ["cnki", "official_site", "baidu_baike", "journal_site"],
            "MAX_PAPERS_PER_AUTHOR": 5,
            "REQUEST_DELAY": 2.0,
        }
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, allow_unicode=True)
        print(f"已创建: {config_path}")
    else:
        print(f"已存在: {config_path}")

    print(f"输出目录: {OUTPUT_DIR}")
    print("初始化完成。")


def _cmd_extract():
    """从管道或参数读入文本，输出提取 prompt"""
    from .extractor import extract_from_text

    text = sys.stdin.read() if len(sys.argv) < 3 else " ".join(sys.argv[2:])
    target = os.environ.get("AUTHOR_NAME", "")
    result = extract_from_text(text, target)
    print(result["_prompt"])


def _cmd_check():
    """扫描输出目录，报告各记录完整度"""
    from .record import AuthorRecord
    from .config import OUTPUT_DIR
    import pandas as pd

    output = Path(OUTPUT_DIR)
    if not output.exists():
        print("输出目录为空。")
        return

    for f in sorted(output.glob("*.xlsx")):
        if f.name.startswith("_"):
            continue
        df = pd.read_excel(f)
        name = f.stem
        for _, row in df.iterrows():
            rec = AuthorRecord(name=name)
            for col in df.columns:
                val = row.get(col, "")
                if pd.notna(val) and str(val).strip():
                    rec.fields[col] = str(val).strip()
            missing = rec.missing_high_priority()
            filled = sum(1 for v in rec.fields.values() if v)
            print(f"{name}: {filled}/{len(rec.fields)} 已填, 缺高优先级: {missing or '无'}")


def _cmd_export():
    """将 _pipeline_log.json 转为 Excel"""
    from .record import save_to_excel, AuthorRecord

    log_path = Path(os.environ.get("AUTHOR_AGENT_DIR", ".")) / "entity_matching2" / "_pipeline_log.json"
    if not log_path.exists():
        print(f"未找到日志: {log_path}")
        return

    with open(log_path, "r", encoding="utf-8") as f:
        log = json.load(f)

    records = []
    for name, fields in log.get("records", {}).items():
        rec = AuthorRecord(name=name)
        for label, val in fields.items():
            if val:
                rec.fields[label] = val
        records.append(rec)

    paths = save_to_excel(records)
    print(f"已导出 {len(paths)} 个文件:")
    for p in paths:
        print(f"  {p}")


def _cmd_pipeline():
    """交互式流水线 — Claude Code 模式"""
    from .pipeline import Pipeline

    pipeline = Pipeline(mode="claude")
    print("=== 名称规范记录搜捕流水线 ===")
    print("输入 'done' 结束采集，'save' 保存退出\n")

    while True:
        cmd = input("\n> ").strip()
        if cmd == "done":
            break
        elif cmd == "save":
            pipeline.save()
            pipeline.save_log()
            print(f"已保存到 {pipeline.output_dir}")
        elif cmd == "check":
            needs = pipeline.check_completeness()
            if needs:
                for name, missing in needs.items():
                    print(f"  {name}: 还缺 {missing}")
            else:
                print("  所有记录完整")
        elif cmd == "tasks":
            for t in pipeline.get_pending_tasks():
                print(f"[{t['name']}] [{t['source']}]")
                print(t['prompt'][:300])
                print("---")
        elif cmd == "summary":
            print(pipeline.summary())
        elif cmd.startswith("feed "):
            # feed 张伟;论文HTML全文_作者简介;文本内容...
            parts = cmd[5:].split(";", 2)
            if len(parts) >= 3:
                pipeline.feed_text(parts[0].strip(), parts[2].strip(), parts[1].strip())
                print(f"  已喂入: {parts[0]} ({parts[1]})")
        elif cmd.startswith("apply "):
            # apply 张伟;来源;{"姓名":"张伟","性别":"男",...}
            parts = cmd[6:].split(";", 2)
            if len(parts) >= 3:
                try:
                    fields = json.loads(parts[2].strip())
                    pipeline.apply_extraction_result(parts[0].strip(), fields, parts[1].strip())
                    print(f"  已应用: {parts[0]}")
                except json.JSONDecodeError as e:
                    print(f"  JSON 解析错误: {e}")
        elif cmd == "help":
            print("  feed <姓名>;<来源>;<文本>   — 喂入原始文本")
            print("  apply <姓名>;<来源>;<JSON> — 应用LLM提取结果")
            print("  tasks                      — 查看待提取任务")
            print("  check                      — 检查完整度")
            print("  summary                    — 流水线摘要")
            print("  save                       — 保存 Excel + 日志")
            print("  done                       — 结束")

    # 结束时保存
    if pipeline.records:
        pipeline.save()
        pipeline.save_log()
        print(pipeline.summary())
        print("完成。")


def _cmd_batch(args):
    """批量搜捕模式：接收 "姓名:机构" 列表，生成搜捕计划"""
    print("=== 批量搜捕计划 ===")
    targets = []
    for arg in args:
        if ":" in arg:
            name, inst = arg.split(":", 1)
            targets.append({"name": name.strip(), "institution": inst.strip()})
        else:
            targets.append({"name": arg.strip(), "institution": ""})

    for i, t in enumerate(targets):
        inst_info = f" ({t['institution']})" if t['institution'] else ""
        print(f"{i+1}. {t['name']}{inst_info}")

    print(f"\n共 {len(targets)} 个目标。")
    print("下一步：对每个目标执行搜捕流程：")
    for t in targets:
        search_query = f"{t['name']} {t['institution']}".strip()
        print(f"  1. 知网作者发文检索: {search_query}")
        print(f"  2. HTML全文提取作者简介")
        print(f"  3. 搜索引擎 → 官网个人页")
        print(f"  4. LLM提取 → 结构化字段")
        print(f"  5. 质量检查 → 补全 → 输出Excel")


if __name__ == "__main__":
    main()
