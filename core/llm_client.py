"""统一 LLM 客户端 — 多提供商切换，翻译与解读模块共用。

提供商在 config.py 选择（LLM_PROVIDER，默认 minimax），模型/密钥按提供商
独立配置（MINIMAX_* / SILICONFLOW_*），均可通过环境变量覆盖。

所有提供商统一走 Anthropic 兼容 Messages 协议，基于 core/http（stdlib）
实现，零第三方依赖；thinking 块自动跳过，只返回正文文本。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from core.http import HTTPError, post_json


class LLMError(RuntimeError):
    """LLM 调用失败（网络 / 鉴权 / 限流配额 / 空回复）。"""


def _provider_conf(provider: str | None = None) -> dict:
    """解析提供商连接配置（endpoint、鉴权头、模型）。"""
    name = (provider or config.LLM_PROVIDER).lower()
    if name == "minimax":
        return {
            "name": name,
            "url": f"{config.MINIMAX_BASE_URL.rstrip('/')}/anthropic/v1/messages",
            "model": config.MINIMAX_MODEL,
            "headers": {"Authorization": f"Bearer {config.MINIMAX_API_KEY}"},
        }
    if name == "siliconflow":
        return {
            "name": name,
            "url": f"{config.SILICONFLOW_BASE_URL.rstrip('/')}/v1/messages",
            "model": config.SILICONFLOW_MODEL,
            "headers": {
                "x-api-key": config.SILICONFLOW_API_KEY,
                "anthropic-version": "2023-06-01",
            },
        }
    raise LLMError(f"未知 LLM 提供商: {name}（可选: minimax, siliconflow）")


def provider_info(provider: str | None = None) -> str:
    """返回 '提供商/模型' 描述，用于日志展示。"""
    conf = _provider_conf(provider)
    return f"{conf['name']}/{conf['model']}"


def chat(prompt: str, *, provider: str | None = None, system: str | None = None,
         max_tokens: int | None = None, temperature: float | None = None) -> str:
    """单次调用 LLM，返回纯文本。失败抛 LLMError。"""
    conf = _provider_conf(provider)
    payload = {
        "model": conf["model"],
        "max_tokens": max_tokens if max_tokens is not None else config.LLM_MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    if temperature is not None:
        payload["temperature"] = temperature

    try:
        data = post_json(conf["url"], payload, headers=conf["headers"],
                         timeout=config.LLM_TIMEOUT)
    except HTTPError as e:
        raise LLMError(f"HTTP {e.status}: {e.body[:200]}") from None
    except Exception as e:  # 网络超时 / DNS 等
        raise LLMError(f"请求异常: {e}") from None

    if data.get("type") == "error":
        raise LLMError(f"API 错误: {data.get('error')}")

    content = data.get("content")
    if isinstance(content, str):          # 少数兼容端点直接返回字符串
        text = content.strip()
    else:                                 # 标准块数组：跳过 thinking 块
        text = "\n".join(b.get("text", "") for b in content or []
                         if b.get("type") == "text").strip()
    if not text:
        raise LLMError("LLM 返回空文本")
    return text


def chat_with_retry(prompt: str, *, provider: str | None = None,
                    system: str | None = None, max_tokens: int | None = None,
                    temperature: float | None = None,
                    max_retries: int | None = None) -> str:
    """带退避重试的 chat（限流/网络抖动自动重试，指数退避）。"""
    retries = max_retries if max_retries is not None else config.LLM_MAX_RETRIES
    for attempt in range(retries):
        try:
            return chat(prompt, provider=provider, system=system,
                        max_tokens=max_tokens, temperature=temperature)
        except LLMError as e:
            if attempt == retries - 1:
                raise
            wait = 15 * (attempt + 1)
            print(f"    LLM 调用失败({e})，{wait}s 后重试...", flush=True)
            time.sleep(wait)
    raise LLMError("LLM 重试次数耗尽")  # 理论不可达
