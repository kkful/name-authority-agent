"""author_agent v1.2.0 - 名称规范记录智能体
v1.2: DeepSeek LLM自适应提取
"""
from .schema import FIELDS, OUTPUT_COLUMNS, SOURCE_PRIORITY
from .record import AuthorRecord, merge_records, save_to_excel
from .extractor import extract_from_text, LLMExtractor
from .pipeline import Pipeline
__version__ = "1.2.0"
