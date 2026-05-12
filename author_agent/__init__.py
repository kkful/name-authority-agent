"""author_agent — 名称规范记录智能体

从网页/论文/官网多来源搜捕作者信息，结构化提取，输出 dedup-librecord 就绪的 Excel。

用法:
    from author_agent import Pipeline, AuthorRecord, extract_from_text
"""

from .schema import FIELDS, OUTPUT_COLUMNS, SOURCE_PRIORITY
from .record import AuthorRecord, merge_records, save_to_excel
from .extractor import extract_from_text, LLMExtractor
from .pipeline import Pipeline

__version__ = "0.1.0"
