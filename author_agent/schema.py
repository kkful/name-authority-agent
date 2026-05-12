"""字段定义 —— 与 dedup-librecord 输入 schema 对齐

定义名称规范记录的全部字段、优先级、来源权重。

使用:
    from author_agent.schema import FIELDS, OUTPUT_COLUMNS, SOURCE_PRIORITY
"""

# (字段名, 中文标签, RDA区分特征优先级, 网页获取方式)
FIELDS = [
    ("name",            "姓名",           "基础",   "论文署名/官网"),
    ("aliases",         "别名",           "低",     "论文署名变体/拼音/曾用名"),
    ("gender",          "性别",           "中",     "论文简介/官网（男/女）"),
    ("ethnicity",       "民族",           "低",     "论文简介/官网"),
    ("education",       "学历",           "中",     "论文简介/官网（学位:博士/硕士/学士）"),
    ("nationality",     "国籍",           "低",     "默认为中国，外籍才标注"),
    ("birth_death",     "生卒年或个人活动日期", "极高", "论文简介/百科/期刊官网 格式:1979- 或 1920-2010"),
    ("hometown",        "籍贯",           "高",     "论文简介/官网（省+市/县）"),
    ("field_of_activity","活动领域",      "高",     "官网研究方向/论文关键词（分号分隔）"),
    ("edu_institutions","受教育机构",     "中",     "官网学历经历（毕业院校，分号分隔）"),
    ("affiliation",     "在职单位",       "极高",   "论文署名单位/官网（全称）"),
    ("occupation",      "职业",           "中",     "官网职称/职务（教授;博导）"),
    ("academic_title",  "职称",           "中",     "论文简介/官网（教授/副教授/讲师/研究员等）"),
    ("email",           "电子邮箱",       "低",     "论文简介/官网联系方式"),
    ("works",           "发表的著作实体",  "高",     "官网成果/知网论文列表（分号分隔）"),
    ("control_id",      "控制号",         "—",      "外部系统ID，用于合并已有记录"),
]

OUTPUT_COLUMNS = [label for _, label, _, _ in FIELDS]

EXCLUDE_FROM_MATCHING = {"控制号"}

SOURCE_PRIORITY = {
    "官网个人页": 10,
    "期刊官网作者档案": 9,
    "百度百科": 8,
    "论文HTML全文_作者简介": 7,
    "论文摘要页": 5,
    "搜索引擎摘要": 3,
}

def high_priority_fields():
    return [label for _, label, priority, _ in FIELDS if priority in ("极高", "高")]

def field_descriptions():
    """返回给 LLM 提取用的字段说明"""
    lines = []
    for _, label, priority, hint in FIELDS:
        if priority == "—":
            continue
        lines.append(f"- {label}（{priority}优先级）: {hint}")
    return "\n".join(lines)
