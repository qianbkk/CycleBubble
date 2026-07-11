"""AI 记忆结构化提取服务

设计原则（见 specs/2026-07-11-ai-admin-design.md v2）：
- AI 仅输出 themes / triggers / recovery / emotions / mood / is_sensitive。
- AI 不做危机检测。危机检测由 safety.py 同步执行，独立于本服务。
- 失败/超时/Key 缺失时抛 AIUnavailable，调用方按开关决定降级或返回错误。

第一期接入 MiniMax（默认 M3），DeepSeek 提供 provider 类结构但实际请求
会抛 AIUnavailable，等接入实际凭证后启用。
"""
import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from ..config import settings
from .admin_settings import (
    KEY_DEEPSEEK_KEY,
    KEY_ENABLE_THIRD_PARTY,
    KEY_MINIMAX_KEY,
    KEY_DEFAULT_PROVIDER,
    KEY_DEFAULT_MODEL_MINIMAX,
    KEY_DEFAULT_MODEL_DEEPSEEK,
    get_setting,
)


logger = logging.getLogger("ai")


class AIUnavailable(Exception):
    """AI 服务不可用（超时、Key 缺失、payload 错误、provider 未实现）。"""


# 提供商元数据：endpoint、env 键、模型键
PROVIDERS = {
    "minimax": {
        "key_setting": KEY_MINIMAX_KEY,
        "model_setting": KEY_DEFAULT_MODEL_MINIMAX,
        "default_model": settings.ai_default_model_minimax,
        "endpoint": "https://api.minimax.chat/v1/text/chatcompletion_v2",
        "implemented": True,  # 第一期默认接入
    },
    "deepseek": {
        "key_setting": KEY_DEEPSEEK_KEY,
        "model_setting": KEY_DEFAULT_MODEL_DEEPSEEK,
        "default_model": settings.ai_default_model_deepseek,
        "endpoint": "https://api.deepseek.com/v1/chat/completions",
        "implemented": False,  # 等实际凭证到位
    },
}


SYSTEM_PROMPT = """你是一位中文情绪日记理解助手。

任务：阅读用户写下的私密情绪记录原文，输出结构化字段。

要求：
- themes（主题）：从原文中识别的主题词，2-5 个，使用简短的汉语名词或动名词短语。
- triggers（触发因素）：原文中提到的诱因，0-3 个。
- recovery（恢复方式）：原文中提到的应对方法，0-3 个。
- emotions（情绪）：原文中体现的情绪，0-3 个，包含 name（情绪名）和 intensity（1-5）。
- mood（情绪基调）：用一个最核心的词概括整体基调。
- is_sensitive（敏感标记）：如果原文涉及自伤、自杀、严重抑郁或危机信号，输出 true，否则 false。

严格按以下 JSON schema 输出，不要包含其他文本：
{
  "themes": ["string"],
  "triggers": ["string"],
  "recovery": ["string"],
  "emotions": [{"name": "string", "intensity": 1}],
  "mood": "string",
  "is_sensitive": false
}
"""


def _normalize_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """校验并规范化 AI 返回的 JSON。"""
    themes = [str(x).strip() for x in (data.get("themes") or []) if str(x).strip()]
    triggers = [str(x).strip() for x in (data.get("triggers") or []) if str(x).strip()]
    recovery = [str(x).strip() for x in (data.get("recovery") or []) if str(x).strip()]
    emotions = []
    for e in (data.get("emotions") or []):
        if isinstance(e, dict):
            name = str(e.get("name") or "").strip()
            if not name:
                continue
            try:
                intensity = max(1, min(5, int(e.get("intensity", 3))))
            except (TypeError, ValueError):
                intensity = 3
            emotions.append({"name": name, "intensity": intensity})
    mood = str(data.get("mood") or "").strip()
    is_sensitive = bool(data.get("is_sensitive", False))
    return {
        "themes": themes[:5],
        "triggers": triggers[:3],
        "recovery": recovery[:3],
        "emotions": emotions[:3],
        "mood": mood,
        "is_sensitive": is_sensitive,
    }


def _request_minimax(api_key: str, model: str, raw_text: str) -> Dict[str, Any]:
    """调用 MiniMax API 并返回归一化结果。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": raw_text},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    try:
        resp = httpx.post(
            "https://api.minimax.chat/v1/text/chatcompletion_v2",
            headers=headers,
            json=payload,
            timeout=settings.ai_request_timeout_seconds,
        )
    except httpx.HTTPError as e:
        raise AIUnavailable(f"AI request failed: {e}") from e
    if resp.status_code != 200:
        raise AIUnavailable(f"AI upstream {resp.status_code}: {resp.text[:200]}")
    body = resp.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise AIUnavailable(f"AI upstream payload invalid: {e}") from e
    try:
        data = json.loads(content)
    except (TypeError, ValueError) as e:
        raise AIUnavailable(f"AI returned non-JSON: {e}") from e
    return _normalize_payload(data)


async def extract_memory(raw_text: str) -> Dict[str, Any]:
    """异步调用 AI 提取结构化字段。

    返回：
    {
      "themes": [...], "triggers": [...], "recovery": [...],
      "emotions": [...], "mood": "...", "is_sensitive": bool
    }

    抛出 AIUnavailable。
    """
    if not raw_text or not raw_text.strip():
        raise AIUnavailable("empty text")

    if not get_setting(KEY_ENABLE_THIRD_PARTY, "true") == "true":
        raise AIUnavailable("third-party AI disabled")

    provider_name = get_setting(KEY_DEFAULT_PROVIDER, settings.ai_default_provider)
    provider = PROVIDERS.get(provider_name)
    if not provider:
        raise AIUnavailable(f"unknown provider {provider_name}")

    api_key = get_setting(provider["key_setting"])
    if not api_key:
        raise AIUnavailable(f"missing api key for {provider_name}")

    model = get_setting(provider["model_setting"]) or provider["default_model"]

    if not provider.get("implemented", False):
        raise AIUnavailable(f"provider {provider_name} not yet wired")

    if provider_name == "minimax":
        return _request_minimax(api_key, model, raw_text)

    raise AIUnavailable(f"provider {provider_name} not implemented")