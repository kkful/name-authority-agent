"""作者记录 — 多来源字段提取、合并、输出 Excel

核心类:
    AuthorRecord: 单条名称规范记录，支持从中文作者简介/官网页面中提取16个字段

提取策略:
    - 论文简介: 仅从目标姓名所在句子提取（防合著者污染）
    - 官网页面: 从全文提取（官网结构化格式，各字段分行）
    - 教育经历/工作经历分离: 不互相污染

使用:
    from author_agent.record import AuthorRecord, save_to_excel

    rec = AuthorRecord(name="陈辰")
    rec.extract_from_text(bio_text, "论文HTML全文_作者简介")
    rec.extract_from_text(profile_text, "官网个人页")  # 官网数据会覆盖论文脏数据
    save_to_excel([rec])
"""

import re
import os
import pandas as pd
from .schema import FIELDS, OUTPUT_COLUMNS, SOURCE_PRIORITY
from .config import OUTPUT_DIR


class AuthorRecord:
    """单条名称规范记录，支持多来源增量填充 + 规则预提取"""

    def __init__(self, name: str, control_id: str = None):
        self.fields = {label: "" for _, label, _, _ in FIELDS}
        self.fields["姓名"] = name
        if control_id:
            self.fields["控制号"] = control_id
        self.sources = {}
        self._merge_log = []

    # ── 基本操作 ──

    def set_field(self, label: str, value: str, source: str, force: bool = False):
        if not value or not str(value).strip():
            return
        value = str(value).strip()
        old = self.fields.get(label, "")
        old_src = self.sources.get(label, "")

        if not old:
            self.fields[label] = value
            self.sources[label] = source
        elif force:
            self.fields[label] = value
            self.sources[label] = source
        elif SOURCE_PRIORITY.get(source, 0) > SOURCE_PRIORITY.get(old_src, 0):
            self.fields[label] = value
            self.sources[label] = source
            self._merge_log.append(f"[覆盖] {label}: 旧[{old_src}]{old[:30]} → 新[{source}]{value[:30]}")
        elif SOURCE_PRIORITY.get(source, 0) == SOURCE_PRIORITY.get(old_src, 0) and len(value) > len(old):
            self.fields[label] = value
            self.sources[label] = source

    def set_fields_from_dict(self, data: dict, source: str):
        for label, value in data.items():
            if label in self.fields:
                self.set_field(label, value, source)

    # ── 规则预提取 ──

    def extract_from_text(self, text: str, source: str):
        """从中文作者简介/官网页面中提取所有可用字段"""
        text = str(text)

        # 找到所有简介区域——兼容论文HTML和官网两种格式
        bio_sections = []
        for m in re.finditer(r'(?:作者简介|个人简介|姓名)\s*[：:]\s*([^\n]+)', text):
            bio_sections.append(m.group(1))
        if not bio_sections:
            bio_sections.append(text[:500])

        # 全文本用于搜索教育经历、著作等
        all_text = text[:10000]
        # 目标姓名相关片段——取每句中包含目标名的句子
        target_sentences = []
        for sent in re.split(r'[。；\n]', all_text):
            if self.fields["姓名"] in sent:
                target_sentences.append(sent.strip())
        if not target_sentences:
            target_sentences = [all_text[:500]]
        target_text = "。".join(target_sentences)

        # 出生年：仅在目标姓名所在句中提取
        if not self.fields["生卒年或个人活动日期"] or source in ("官网个人页",):
            # 找包含目标姓名的句子中的年份
            name_positions = [m.start() for m in re.finditer(self.fields["姓名"], all_text)]
            found_valid_year = False
            for pos in name_positions:
                # 取姓名前后各100字符
                ctx = all_text[max(0,pos-50):pos+150]
                for pat in [r'[（(]\s*(\d{4})\s*[-–—年]\s*\d{0,4}\s*[）)]', r'(\d{4})\s*年\s*生']:
                    m = re.search(pat, ctx)
                    if m:
                        y = int(m.group(1))
                        if 1960 <= y <= 2000:
                            self.set_field("生卒年或个人活动日期", str(y)+"-", source)
                            found_valid_year = True
                            break
                if found_valid_year:
                    break
            # 如果官网没找到生年，清空论文的脏数据
            if source in ("官网个人页",) and not found_valid_year:
                self.fields["生卒年或个人活动日期"] = ""
            # 备用："1985年生"
            if not self.fields["生卒年或个人活动日期"]:
                m = re.search(r'(\d{4})\s*年\s*生', target_text)
                if m and 1960 <= int(m.group(1)) <= 2000:
                    self.set_field("生卒年或个人活动日期", m.group(1)+"-", source)

        # 性别
        if not self.fields["性别"]:
            m = re.search(r'[，,]\s*([男女])\s*[，,。]', target_text[:100])
            if m:
                self.set_field("性别", m.group(1), source)

        # 籍贯
        if not self.fields["籍贯"]:
            m = re.search(r'([一-鿿]{2,4})\s*人[，,\s]', target_text[:300])
            if m:
                self.set_field("籍贯", m.group(1)+"人", source)

        # 在职单位 — 官网数据优先覆盖论文数据
        if not self.fields["在职单位"] or source in ("官网个人页",):
            if source == "官网个人页":
                self.fields["在职单位"] = ""
            work_insts = []
            # 工作经历中的机构
            work_section = re.search(r'(?:工作经历|工作单位)[：:\s]*([\s\S]+?)(?:\n\n|\n(?:讲授|研究|著作|论文|获奖|（|\d{4}))', all_text)
            if work_section:
                for m in re.finditer(r'[：:]\s*([一-鿿]{2,30}(?:大学|学院|金融学院)[一-鿿]{0,20})', work_section.group(1)):
                    inst = m.group(1)
                    if len(inst) >= 6 and "博士" not in inst and "硕士" not in inst and "学位" not in inst:
                        if inst not in work_insts:
                            work_insts.append(inst)
            # 设置在职单位
            all_work = []
            current = re.search(r'(?:现为|现任|至今[：:]\s*)([一-龥]{2,30}(?:大学|学院)[一-龥]{0,20})', all_text)
            if current:
                all_work.append(current.group(1))
            all_work.extend(work_insts)
            if all_work:
                self.set_field("在职单位", "; ".join(all_work[:5]), source)

        # 学历 — 全文本搜，官网数据可覆盖
        if not self.fields["学历"] or source in ("官网个人页",):
            edu = re.findall(r'(博士|硕士|学士|本科|访问学者|博士后)', all_text)
            if edu:
                if "博士" in edu:
                    self.set_field("学历", "博士", source)
                elif "硕士" in edu:
                    self.set_field("学历", "硕士", source)
                elif "学士" in edu or "本科" in edu:
                    self.set_field("学历", "学士", source)

        # 受教育机构 — 只从教育经历提取（不混工作经历）
        if not self.fields["受教育机构"] or source == "官网个人页":
            schools = []
            edu_section2 = re.search(r'(?:教育经历|教育背景)[：:\s]*([\s\S]+?)(?:\n\n|\n(?:工[作经]|讲授|研究|著作|论文|获奖|（|\d{4}))', all_text)
            search_area = edu_section2.group(1) if edu_section2 else ""
            # 模式1: "获XXX大学博士学位" "毕业于XXX大学"
            for m in re.finditer(r'(?:获|毕业于|就读于)\s*([一-龥]+大学)', search_area if search_area else all_text):
                s = m.group(1); schools.append(s)
            # 模式2: 教育经历section中的所有大学
            if not schools and search_area:
                for m in re.finditer(r'([一-龥]+大学)', search_area):
                    s = m.group(1)
                    if s not in schools: schools.append(s)
            # 模式3: "XXX大学博士/硕士"
            if not schools:
                for m in re.finditer(r'([一-龥]+大学)\s*(?:管理学|文学|理学|工学|法学|经济学|农学)?(?:博士|硕士|学士)', all_text):
                    s = m.group(1)
                    if s not in schools: schools.append(s)
            if schools:
                self.set_field("受教育机构", "; ".join(schools[:5]), source)

        # 发表的著作实体 — 著作+论文列表
        if not self.fields["发表的著作实体"]:
            works = []
            # 著作: 从"著作"section或《书名》中提取
            work_section = re.search(r'(?:著作|专著|出版物)[：:\s]*([\s\S]+?)(?:\n\n|\n(?:论文|讲授|科研|获奖|\d{4}))', all_text)
            search_area = work_section.group(1) if work_section else all_text
            for m in re.finditer(r'《([^》]+)》', search_area):
                title = m.group(1).strip()
                if len(title) > 3 and title not in works:
                    works.append(f"《{title}》")
            # 论文: 从"论文"section或【数字】标记提取
            paper_section = re.search(r'(?:论文|发表论文|学术论文)[：:\s]*([\s\S]+?)(?:\n\n|\n(?:讲授|科研|获奖|\d{4}\s*$))', all_text)
            search_papers = paper_section.group(1) if paper_section else all_text
            for m in re.finditer(r'(?:【\d+】|\[\d+\])\s*([^。\n]{10,80}?)(?:[Jj]\.|[Jj]ournal|[，,]\s*\d{4})', search_papers):
                p = m.group(1).strip()
                if len(p) > 10 and p not in works:
                    works.append(p)
            if works:
                self.set_field("发表的著作实体", "; ".join(works[:10]), source)

        # 研究方向 — 论文从目标句取，官网从全文取
        if not self.fields["活动领域"] or source in ("官网个人页",):
            if source in ("官网个人页",):
                self.fields["活动领域"] = ""
            search_a = all_text[:3000] if source in ("官网个人页",) else target_text
            m = re.search(r'(?:研究方向|研究领域|主要从事|主要研究方向)[是为]?\s*[:：]?\s*([^。\n]+)', search_a)
            if m:
                val = m.group(1).strip()
                # 去掉 E-mail:xxx 和 邮编, 河北xxx 等杂质
                val = re.sub(r',?\s*E-mail\s*[:：]\s*\S+', '', val)
                val = re.sub(r',?\s*\d{6}', '', val)
                val = re.sub(r',?\s*[一-鿿]{2,3}\s*\d{6}', '', val)
                val = val.strip(';,， ')
                if len(val) > 2 and len(val) < 100:
                    self.set_field("活动领域", val, source)

        # Email — 论文从目标句提取，官网从全文提取
        if not self.fields["电子邮箱"] or source in ("官网个人页",):
            if source in ("官网个人页",):
                self.fields["电子邮箱"] = ""
            # 官网：全文搜索 邮箱/E-mail
            search_area = all_text if source in ("官网个人页",) else target_text
            for line in search_area.replace("；", "\n").split("\n"):
                if self.fields["姓名"] in line:
                    m = re.search(r'(?:E-?mail|邮箱|电子邮箱|联系方式)\s*[:：]\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', line, re.IGNORECASE)
                    if m:
                        self.set_field("电子邮箱", m.group(1), source)
                        break
            # fallback: 全文本搜，但必须是邮箱标注紧跟目标姓名
            if not self.fields["电子邮箱"]:
                m = re.search(rf'{self.fields["姓名"]}[^@]{{0,50}}(?:E-?mail|邮箱|电子邮箱)\s*[:：]\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{{2,}})', all_text, re.IGNORECASE)
                if m:
                    self.set_field("电子邮箱", m.group(1), source)

        # 职称 — 论文从目标句取，官网从全文取
        if not self.fields["职称"] or not self.fields["职业"] or source in ("官网个人页",):
            if source == "官网个人页":
                self.fields["职称"] = ""; self.fields["职业"] = ""
            search_t = all_text[:3000] if source in ("官网个人页",) else target_text
            titles = re.findall(r'(教授|副教授|讲师|研究员|副研究员|博导|硕导|硕士生导师|博士生导师|博士后|工程师|高级工程师)', search_t)
            seen = set(); deduped = []
            for t in titles:
                if t not in seen: seen.add(t); deduped.append(t)
            if deduped:
                self.set_field("职称", "; ".join(deduped[:3]), source)
                self.set_field("职业", "; ".join(deduped[:3]), source)

    # ── 输出 ──

    def to_dict(self) -> dict:
        return dict(self.fields)

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([self.fields], columns=OUTPUT_COLUMNS)

    def report(self) -> str:
        lines = [f"姓名: {self.fields['姓名']}"]
        for _, label, _, _ in FIELDS:
            val = self.fields.get(label, "")
            src = self.sources.get(label, "")
            if val:
                lines.append(f"  {label}: {val[:80]}  [{src}]")
            else:
                lines.append(f"  {label}: (缺失)")
        return "\n".join(lines)

    def missing_high_priority(self) -> list:
        from .schema import high_priority_fields
        return [f for f in high_priority_fields() if not self.fields.get(f, "")]


# ── 批量操作 ──

def merge_records(records: list, primary_name: str) -> AuthorRecord:
    """合并多条记录为一条"""
    if not records:
        return AuthorRecord(name=primary_name)
    base = records[0]
    for rec in records[1:]:
        for _, label, _, _ in FIELDS:
            val = rec.fields.get(label, "")
            src = rec.sources.get(label, "")
            if val:
                base.set_field(label, val, src)
    return base


def save_to_excel(records: list, output_dir: str = None):
    """保存为 dedup-librecord 格式 Excel，按姓名分组"""
    if output_dir is None:
        output_dir = str(OUTPUT_DIR)
    os.makedirs(output_dir, exist_ok=True)

    groups = {}
    for rec in records:
        name = rec.fields["姓名"]
        groups.setdefault(name, []).append(rec)

    saved = []
    for name, recs in groups.items():
        df = pd.DataFrame([r.to_dict() for r in recs], columns=OUTPUT_COLUMNS)
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', name)
        path = os.path.join(output_dir, f"{safe_name}.xlsx")
        df.to_excel(path, index=False)
        saved.append(path)

    return saved
