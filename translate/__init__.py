"""翻译阶段统一入口 — 按 config.TRANSLATE_ENGINE 分发引擎。

引擎可选:
    llm   = 大模型翻译（core/llm_client，默认 MiniMax，可切 SiliconFlow）
    baidu = 百度机器翻译
两个引擎的 translate_article(ws, num, force) 接口完全一致，可无缝替换。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

from core.contract import Workspace


def translate_article(ws: Workspace, num: int, force: bool = False):
    """按配置引擎翻译一篇文章，返回输出路径；跳过返回 None。"""
    engine = config.TRANSLATE_ENGINE.lower()
    if engine == "llm":
        from translate.llm_translate import translate_article as fn
    elif engine == "baidu":
        from translate.baidu_translate import translate_article as fn
    else:
        raise SystemExit(f"未知翻译引擎: {config.TRANSLATE_ENGINE}（可选: llm, baidu）")
    return fn(ws, num, force=force)
