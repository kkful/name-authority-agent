"""LLM 提取器 — 将非结构化网页文本转为结构化字段

两种模式:
  1. extract_from_text(): 给定原始文本 + 已知字段描述，返回结构化 dict
     可在 Claude Code 会话中直接使用（LLM=Claude本身）
  2. LLMExtractor: API 后端封装，用于独立运行
"""
import re
import json
from .schema import field_descriptions


EXTRACTION_PROMPT = """你是一位学术人员信息提取专家。请从以下网页文本中，提取目标学者的结构化信息。

## 需要提取的字段
{field_desc}

## 规则
1. 只提取目标学者的信息，不要混入合著者、引用者的信息
2. 缺失的字段留空字符串 ""
3. 多值字段用分号（;）分隔（如多个机构、多部著作）
4. 生卒年格式: "1979-" 表示1979年出生仍在世，"1920-2010" 表示已故
5. 籍贯格式: "安徽庐江人" 或省份+县市
6. 性别只填 "男" 或 "女"
7. 不要编造信息，只提取文本中明确出现的内容

## 输出格式
严格返回 JSON，键名用中文标签:
```json
{{
  "姓名": "",
  "别名": "",
  "性别": "",
  "民族": "",
  "学历": "",
  "国籍": "",
  "生卒年或个人活动日期": "",
  "籍贯": "",
  "活动领域": "",
  "受教育机构": "",
  "在职单位": "",
  "职业": "",
  "发表的著作实体": "",
  "控制号": ""
}}
```

## 目标学者
姓名: {target_name}

## 网页文本
{text}"""


def extract_from_text(text: str, target_name: str = "", source: str = "") -> dict:
    """生成提取 prompt，供 LLM 调用。

    在 Claude Code 会话中使用时，将 prompt 展示给 Claude 即可完成提取。
    在独立脚本中使用时，结合 LLMExtractor 调用 API。

    返回: {field_label: value, ...}
    """
    prompt = EXTRACTION_PROMPT.format(
        field_desc=field_descriptions(),
        target_name=target_name or "待确认",
        text=text[:8000]  # 限制长度
    )
    return {"_prompt": prompt, "_source": source}


class LLMExtractor:
    """独立运行的 LLM 提取器（需要 API key）"""

    def __init__(self, provider: str = None, model: str = None, api_key: str = None):
        from .config import LLM_PROVIDER, LLM_MODEL
        self.provider = provider or LLM_PROVIDER
        self.model = model or LLM_MODEL
        self.api_key = api_key

    def extract(self, text: str, target_name: str) -> dict:
        prompt = EXTRACTION_PROMPT.format(
            field_desc=field_descriptions(),
            target_name=target_name,
            text=text[:8000]
        )

        if self.provider == "claude":
            return self._call_claude(prompt)
        elif self.provider == "openai":
            return self._call_openai(prompt)
        else:
            # 本地模式：返回 prompt 等待外部 LLM 处理
            return extract_from_text(text, target_name)

    def _call_claude(self, prompt: str) -> dict:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            resp = client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            return _parse_json_response(resp.content[0].text)
        except ImportError:
            raise ImportError("需要 pip install anthropic")
        except Exception as e:
            return {"_error": str(e), "_prompt": prompt}

    def _call_openai(self, prompt: str) -> dict:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            resp = client.chat.completions.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            return _parse_json_response(resp.choices[0].message.content)
        except ImportError:
            raise ImportError("需要 pip install openai")
        except Exception as e:
            return {"_error": str(e), "_prompt": prompt}


def _parse_json_response(text: str) -> dict:
    """从 LLM 回复中提取 JSON"""
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试提取 ```json 代码块
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 尝试提取 {} 包裹的内容
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {"_raw": text}
