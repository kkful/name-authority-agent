"""流水线编排 — 从搜捕到输出的完整流程"""

import json
import os
from datetime import datetime
from .record import AuthorRecord, merge_records, save_to_excel
from .extractor import extract_from_text, LLMExtractor
from .schema import SOURCE_PRIORITY
from .config import OUTPUT_DIR, MAX_PAPERS_PER_AUTHOR


class Pipeline:
    """名称规范记录搜捕流水线

    mode:
      - "claude": 在 Claude Code 会话中运行，提取步骤返回 prompt 让 Claude 处理
      - "api": 独立运行，通过 LLM API 提取
      - "manual": 手动输入结构化数据
    """

    def __init__(self, output_dir: str = None, mode: str = "claude"):
        self.output_dir = output_dir or str(OUTPUT_DIR)
        self.mode = mode
        self.records = {}       # name -> AuthorRecord
        self.extraction_tasks = []  # 待提取的文本队列
        self.extractor = LLMExtractor() if mode == "api" else None

    # ── 输入 — 喂入网页文本 ──

    def feed_text(self, name: str, text: str, source: str):
        """喂入一段网页原始文本，排队等待提取"""
        if name not in self.records:
            self.records[name] = AuthorRecord(name=name)

        # 先做规则预提取
        self.records[name].extract_from_text(text, source)

        # 排队 LLM 提取
        task = {
            "name": name,
            "text": text,
            "source": source,
            "prompt": extract_from_text(text, name, source)
        }
        self.extraction_tasks.append(task)

    def feed_structured(self, name: str, fields: dict, source: str):
        """直接喂入已结构化的字段"""
        if name not in self.records:
            self.records[name] = AuthorRecord(name=name)
        self.records[name].set_fields_from_dict(fields, source)

    # ── 提取 ──

    def get_pending_tasks(self) -> list:
        """返回待处理的提取 prompt 列表（Claude 模式用）"""
        return [
            {"name": t["name"], "source": t["source"], "prompt": t["prompt"]["_prompt"]}
            for t in self.extraction_tasks
        ]

    def apply_extraction_result(self, name: str, fields: dict, source: str):
        """应用一条 LLM 提取结果"""
        if name not in self.records:
            self.records[name] = AuthorRecord(name=name)
        # 清理：去除 _prompt _source 等内部键
        clean = {k: v for k, v in fields.items() if not k.startswith("_") and v}
        self.records[name].set_fields_from_dict(clean, source)

    def extract_all_api(self) -> dict:
        """API 模式：批量调用 LLM 提取所有待处理文本"""
        if not self.extractor:
            self.extractor = LLMExtractor()
        results = {}
        for task in self.extraction_tasks:
            fields = self.extractor.extract(task["text"], task["name"])
            self.apply_extraction_result(task["name"], fields, task["source"])
            results[task["name"]] = fields
        self.extraction_tasks = []
        return results

    # ── 质量检查 ──

    def check_completeness(self) -> dict:
        """检查所有记录的高优先级字段完整度，返回需继续滚雪球的列表"""
        needs_more = {}
        for name, rec in self.records.items():
            missing = rec.missing_high_priority()
            if missing:
                needs_more[name] = missing
        return needs_more

    # ── 输出 ──

    def save(self) -> list:
        """保存所有记录为 Excel"""
        all_recs = list(self.records.values())
        return save_to_excel(all_recs, self.output_dir)

    def summary(self) -> str:
        """流水线摘要"""
        lines = [
            f"=== 流水线摘要 ===",
            f"记录数: {len(self.records)}",
            f"待提取任务: {len(self.extraction_tasks)}",
            f"输出目录: {self.output_dir}",
        ]
        for name, rec in self.records.items():
            filled = sum(1 for v in rec.fields.values() if v)
            total = len(rec.fields)
            missing = rec.missing_high_priority()
            lines.append(f"  {name}: {filled}/{total} 字段, 缺: {missing or '无'}")
        return "\n".join(lines)

    # ── 日志 ──

    def save_log(self):
        """保存运行日志"""
        log = {
            "timestamp": datetime.now().isoformat(),
            "mode": self.mode,
            "records": {name: rec.to_dict() for name, rec in self.records.items()},
            "sources": {name: rec.sources for name, rec in self.records.items()},
        }
        log_path = os.path.join(self.output_dir, "_pipeline_log.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
        return log_path
