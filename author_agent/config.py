"""全局配置 - 路径、模型、API Key

配置文件: config.yaml (项目根目录)
环境变量: DEEPSEEK_API_KEY, AUTHOR_AGENT_LLM, AUTHOR_AGENT_DIR
"""
import os
from pathlib import Path

WORK_DIR = Path(os.environ.get("AUTHOR_AGENT_DIR", r"E:\规范文档"))
OUTPUT_DIR = Path(os.environ.get("AUTHOR_AGENT_OUTPUT", str(WORK_DIR / "entity_matching2")))
DEDUP_DIR = Path(os.environ.get("AUTHOR_AGENT_DEDUP", r"E:\dedup-librecord"))

LLM_PROVIDER = os.environ.get("AUTHOR_AGENT_LLM", "deepseek")
LLM_MODEL = os.environ.get("AUTHOR_AGENT_MODEL", "deepseek-chat")

SEARCH_SOURCES = ["cnki", "official_site", "baidu_baike", "journal_site"]
MAX_PAPERS_PER_AUTHOR = 5
REQUEST_DELAY = 2.0
CDP_PROXY = "http://localhost:3456"

# Load config.yaml
_config_path = WORK_DIR / "config.yaml"
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
if not DEEPSEEK_API_KEY and _config_path.exists():
    try:
        import yaml
        with open(_config_path, "r", encoding="utf-8") as f:
            _cfg = yaml.safe_load(f) or {}
        DEEPSEEK_API_KEY = _cfg.get("DEEPSEEK_API_KEY", "")
        for k, v in _cfg.items():
            if k.isupper() and k in globals():
                globals()[k] = v
    except ImportError:
        pass
