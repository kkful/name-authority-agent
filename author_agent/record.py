"""作者记录 - 多来源字段提取、合并、输出 Excel

v1.2 修复: 移除"先清空再提取"逻辑,字段不再被官网页面格式差异清空
LLM自适应提取优先级20(最高),确保DeepSeek提取结果生效
"""

import re
import os
import pandas as pd
from .schema import FIELDS, OUTPUT_COLUMNS, SOURCE_PRIORITY
from .config import OUTPUT_DIR


class AuthorRecord:
    """单条名称规范记录,支持多来源增量填充 + 规则预提取"""

    def __init__(self, name: str, control_id: str = None):
        self.fields = {label: "" for _, label, _, _ in FIELDS}
        self.fields["姓名"] = name
        if control_id:
            self.fields["控制号"] = control_id
        self.sources = {}

    def set_field(self, label: str, value: str, source: str, force: bool = False):
        if not value or not str(value).strip():
            return
        value = str(value).strip()
        old = self.fields.get(label, "")
        old_src = self.sources.get(label, "")
        if not old:
            self.fields[label] = value; self.sources[label] = source
        elif force:
            self.fields[label] = value; self.sources[label] = source
        elif SOURCE_PRIORITY.get(source, 0) > SOURCE_PRIORITY.get(old_src, 0):
            self.fields[label] = value; self.sources[label] = source
        elif SOURCE_PRIORITY.get(source, 0) == SOURCE_PRIORITY.get(old_src, 0) and len(value) > len(old):
            self.fields[label] = value; self.sources[label] = source

    def set_fields_from_dict(self, data: dict, source: str):
        for label, value in data.items():
            if label in self.fields:
                self.set_field(label, value, source)

    def extract_from_text(self, text: str, source: str):
        """从中文作者简介/官网页面中提取字段。
        v1.2修复: 不再先清空再提取,旧值保留直到新值确实提取到。
        """
        text = str(text)
        all_text = text[:10000]

        # 目标姓名所在句子
        target_sentences = []
        for sent in re.split(r'[。；\n]', all_text):
            if self.fields["姓名"] in sent:
                target_sentences.append(sent.strip())
        if not target_sentences:
            target_sentences = [all_text[:500]]
        target_text = "。".join(target_sentences)

        # 出生年
        if not self.fields["生卒年或个人活动日期"] or source in ("官网个人页", "LLM自适应提取"):
            for pos in [m.start() for m in re.finditer(self.fields["姓名"], all_text)]:
                ctx = all_text[max(0,pos-50):pos+150]
                for pat in [r'[（(]\s*(\d{4})\s*[-–—年]\s*\d{0,4}\s*[）)]', r'(\d{4})\s*年\s*生']:
                    m = re.search(pat, ctx)
                    if m and 1960 <= int(m.group(1)) <= 2000:
                        self.set_field("生卒年或个人活动日期", m.group(1)+"-", source); break

        # 性别
        if not self.fields["性别"]:
            m = re.search(r'[，,]\s*([男女])\s*[，,。]', target_text[:100])
            if m: self.set_field("性别", m.group(1), source)

        # 籍贯
        if not self.fields["籍贯"]:
            m = re.search(r'([一-鿿]{2,4})\s*人[，,\s]', target_text[:300])
            if m: self.set_field("籍贯", m.group(1)+"人", source)

        # 在职单位 (v1.2: 不再先清空)
        if not self.fields["在职单位"] or source in ("官网个人页",):
            all_work = []
            work_section = re.search(r'(?:工作经历|工作单位)[：:\s]*([\s\S]+?)(?:\n\n|\n(?:讲授|研究|著作|论文|获奖|（|\d{4}))', all_text)
            section = work_section.group(1) if work_section else all_text
            for m in re.finditer(r'([一-龥]{2,30}(?:大学|学院)[一-龥]{0,20})', section):
                inst = m.group(1)
                if len(inst) >= 6 and "博士" not in inst and "硕士" not in inst:
                    if inst not in all_work: all_work.append(inst)
            if all_work:
                self.set_field("在职单位", "; ".join(all_work[:5]), source)

        # 学历 (v1.2: 不再先清空)
        if not self.fields["学历"] or source in ("官网个人页",):
            edu = re.findall(r'(博士|硕士|学士|本科|访问学者|博士后)', all_text)
            if "博士" in edu: self.set_field("学历", "博士", source)
            elif "硕士" in edu: self.set_field("学历", "硕士", source)

        # 受教育机构
        if not self.fields["受教育机构"] or source in ("官网个人页",):
            schools = []
            edu_section = re.search(r'(?:教育经历|教育背景)[：:\s]*([\s\S]+?)(?:\n\n|\n(?:工[作经]|讲授|研究|著作|论文))', all_text)
            search = edu_section.group(1) if edu_section else all_text
            for m in re.finditer(r'(?:获|毕业于|就读于)?\s*([一-龥]+大学)', search):
                s = m.group(1)
                if s not in schools: schools.append(s)
            if schools: self.set_field("受教育机构", "; ".join(schools[:5]), source)

        # 研究方向 (v1.2: 不再先清空)
        if not self.fields["活动领域"] or source in ("官网个人页", "LLM自适应提取"):
            search_a = all_text[:3000] if source in ("官网个人页",) else target_text
            m = re.search(r'(?:研究方向|研究领域|主要从事|主要研究方向)[是为]?\s*[:：]?\s*([^。\n]+)', search_a)
            if m:
                val = re.sub(r',?\s*E-?mail\s*[:：]\s*\S+', '', m.group(1).strip())
                val = re.sub(r',?\s*\d{6}', '', val).strip(';,， ')
                if len(val) > 2 and len(val) < 100:
                    self.set_field("活动领域", val, source)

        # 职称 (v1.2: 不再先清空)
        if not self.fields["职称"] or not self.fields["职业"] or source in ("官网个人页",):
            search_t = all_text[:3000] if source in ("官网个人页",) else target_text
            titles = re.findall(r'(教授|副教授|讲师|研究员|副研究员|博导|硕导|硕士生导师|博士生导师|博士后|工程师)', search_t)
            seen = set(); deduped = []
            for t in titles:
                if t not in seen: seen.add(t); deduped.append(t)
            if deduped:
                self.set_field("职称", "; ".join(deduped[:3]), source)
                self.set_field("职业", "; ".join(deduped[:3]), source)

        # 邮箱 (v1.2: 不再先清空)
        if not self.fields["电子邮箱"] or source in ("官网个人页",):
            search_area = all_text if source in ("官网个人页",) else target_text
            for line in search_area.replace("；", "\n").split("\n"):
                if self.fields["姓名"] in line:
                    m = re.search(r'(?:E-?mail|邮箱|邮\s*箱|电子邮箱)\s*[:：]\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', line, re.IGNORECASE)
                    if m: self.set_field("电子邮箱", m.group(1), source); break

        # 著作
        if not self.fields["发表的著作实体"]:
            works = []
            for m in re.finditer(r'《([^》]+)》', all_text):
                t = m.group(1).strip()
                if len(t) > 3 and t not in works: works.append(f"《{t}》")
            if works: self.set_field("发表的著作实体", "; ".join(works[:10]), source)

    def to_dict(self) -> dict:
        return dict(self.fields)

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([self.fields], columns=OUTPUT_COLUMNS)

    def missing_high_priority(self) -> list:
        from .schema import high_priority_fields
        return [f for f in high_priority_fields() if not self.fields.get(f, "")]


def merge_records(records: list, primary_name: str):
    if not records: return AuthorRecord(name=primary_name)
    base = records[0]
    for rec in records[1:]:
        for _, label, _, _ in FIELDS:
            val = rec.fields.get(label, ""); src = rec.sources.get(label, "")
            if val: base.set_field(label, val, src)
    return base


def save_to_excel(records: list, output_dir: str = None):
    if output_dir is None: output_dir = str(OUTPUT_DIR)
    os.makedirs(output_dir, exist_ok=True)
    groups = {}
    for rec in records:
        groups.setdefault(rec.fields["姓名"], []).append(rec)
    saved = []
    for name, recs in groups.items():
        df = pd.DataFrame([r.to_dict() for r in recs], columns=OUTPUT_COLUMNS)
        safe = re.sub(r'[\\/:*?"<>|]', '_', name)
        path = os.path.join(output_dir, f"{safe}.xlsx")
        df.to_excel(path, index=False)
        saved.append(path)
    return saved
