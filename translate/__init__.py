"""翻译阶段统一入口 — 按 config.TRANSLATE_ENGINE 分发引擎。

引擎可选:
    llm   = 大模型翻译（core/llm_client，默认 MiniMax，可切 SiliconFlow）
    baidu = 百度机器翻译
两个引擎的 translate_article(ws, num, force) 接口完全一致，可无缝替换。

试错机制: 当 TRANSLATE_ENGINE=llm 时，若 LLM 翻译因敏感词/异常失败，
自动回退到百度机器翻译，保证整期不因单篇内容问题中断。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

from core.contract import Workspace


def translate_article(ws: Workspace, num: int, force: bool = False):
    """按配置引擎翻译一篇文章，返回输出路径；跳过返回 None。

    配置为 llm 时，LLM 失败自动回退百度机翻（试错机制）。
    """
    engine = config.TRANSLATE_ENGINE.lower()
    if engine == "llm":
        from translate.llm_translate import translate_article as fn
        try:
            return fn(ws, num, force=force)
        except Exception as exc:
            print(f"  ⚠ LLM 翻译失败 ({type(exc).__name__}): {exc}")
            print("     → 回退百度逐句翻译（单句失败则跳过保留原文）")
            from translate.baidu_translate import translate_article_sentences as baidu_fn
            return baidu_fn(ws, num, force=force)
    elif engine == "baidu":
        from translate.baidu_translate import translate_article as fn
        return fn(ws, num, force=force)
    else:
        raise SystemExit(f"未知翻译引擎: {config.TRANSLATE_ENGINE}（可选: llm, baidu）")
