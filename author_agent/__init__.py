"""author_agent v1.2.0 - 名称规范记录智能体

从网页/论文/官网多来源搜捕作者信息,结构化提取,输出 dedup-librecord 就绪的 Excel
v1.2: 集成DeepSeek LLM自适应提取
"""

from .schema import FIELDS, OUTPUT_COLUMNS, SOURCE_PRIORITY
from .record import AuthorRecord, merge_records, save_to_excel
from .extractor import extract_from_text, LLMExtractor
from .pipeline import Pipeline

__version__ = "1.2.0"
