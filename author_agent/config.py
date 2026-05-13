"""全局配置 - 路径、模型、API Key

配置文件: config.yaml (项目根目录)
环境变量: DEEPSEEK_API_KEY
"""
import os
from pathlib import Path

WORK_DIR = Path(os.environ.get("AUTHOR_AGENT_DIR", str(Path(__file__).parent.parent)))
OUTPUT_DIR = Path(os.environ.get("AUTHOR_AGENT_OUTPUT", str(WORK_DIR / "entity_matching2")))

LLM_PROVIDER = os.environ.get("AUTHOR_AGENT_LLM", "deepseek")
LLM_MODEL = os.environ.get("AUTHOR_AGENT_MODEL", "deepseek-chat")

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
