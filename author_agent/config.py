"""全局配置 — 路径、模型、来源设置

可通过环境变量或 config.yaml 覆盖默认值。

环境变量:
    AUTHOR_AGENT_DIR: 工作目录（默认 E:\规范文档）
    AUTHOR_AGENT_OUTPUT: 输出目录（默认 entity_matching2）
    AUTHOR_AGENT_LLM: LLM 提供商（claude/openai/local）

使用:
    from author_agent.config import OUTPUT_DIR, WORK_DIR
"""

import os
import json
from pathlib import Path

# 工作目录
WORK_DIR = Path(os.environ.get("AUTHOR_AGENT_DIR", r"E:\规范文档"))

# 输出目录 — dedup-librecord 匹配管道读取的目录
OUTPUT_DIR = Path(os.environ.get("AUTHOR_AGENT_OUTPUT", str(WORK_DIR / "entity_matching2")))

# dedup-librecord 路径（用于直接调用匹配）
DEDUP_DIR = Path(os.environ.get("AUTHOR_AGENT_DEDUP", r"E:\dedup-librecord"))

# LLM 配置 — 提取非结构化文本时的模型
LLM_PROVIDER = os.environ.get("AUTHOR_AGENT_LLM", "claude")  # claude | openai | local
LLM_MODEL = os.environ.get("AUTHOR_AGENT_MODEL", "claude-sonnet-4-6")

# 爬取配置
SEARCH_SOURCES = ["cnki", "official_site", "baidu_baike", "journal_site"]
MAX_PAPERS_PER_AUTHOR = 5  # 每人最多打开几篇论文HTML
REQUEST_DELAY = 2.0        # 请求间隔（秒），防反爬

# CDP Proxy 地址（web-access 模式）
CDP_PROXY = "http://localhost:3456"

# 尝试从 config.yaml 加载覆盖
_config_path = WORK_DIR / "config.yaml"
if _config_path.exists():
    try:
        import yaml
        with open(_config_path, "r", encoding="utf-8") as f:
            _cfg = yaml.safe_load(f) or {}
        for k, v in _cfg.items():
            if k.isupper() and k in globals():
                globals()[k] = v
    except ImportError:
        pass
