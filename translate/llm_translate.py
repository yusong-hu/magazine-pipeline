"""LLM 翻译模块 — 用大模型把英文文章 md 翻译为中文文章 md。

用法:
    python -m translate.llm_translate --num 1 [--workspace xxx]
    python -m translate.llm_translate --all

设计:
  - 走 core/llm_client（提供商/模型见 config.LLM_PROVIDER，默认 MiniMax）
  - 按段落分块（每块 <= LLM_TRANSLATE_MAX_CHARS），保留段落边界
  - 并发受 LLM_CONCURRENCY 限制；失败按 LLM_MAX_RETRIES 退避重试
  - 已存在的 zh md 默认跳过（--force 覆盖）
"""
from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from core.contract import Workspace, get_workspace
from core.llm_client import chat_with_retry, provider_info
from core.markdown_utils import build_zh_md, parse_article_doc
from core.text_utils import split_into_chunks

TRANSLATE_SYSTEM = "你是一位资深的中英翻译，擅长《经济学人》《纽约客》等英文杂志的汉译，译文达到中文出版水准。"

TRANSLATE_PROMPT = """把下面的英文 Markdown 片段翻译成中文，要求：
- 忠实原意，译文流畅自然，符合中文杂志出版水准
- 严格保持原有段落结构：空行分隔的段落一一对应，不合并、不拆分、不增删段落
- 保留 Markdown 标记（# * - > 等）与文内超链接
- 人名、机构名等专有名词首次出现时，在中文译名后用括号标注英文原文
- 只输出译文本身，不要任何解释、前言或原文复述

英文原文：

{text}"""


def _clean(text: str) -> str:
    """去掉模型偶发的包裹（代码围栏/引号）与首尾空白。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


def translate_chunk(text: str) -> str:
    """翻译单个文本块（含重试）。"""
    return _clean(chat_with_retry(
        TRANSLATE_PROMPT.format(text=text), system=TRANSLATE_SYSTEM))


def translate_text(text: str) -> str:
    """并发翻译整篇文本（含分块）。"""
    chunks = split_into_chunks(text, config.LLM_TRANSLATE_MAX_CHARS)
    if not chunks:
        return ""
    print(f"    分块: {len(chunks)} 块 (并发 {config.LLM_CONCURRENCY})", flush=True)

    def worker(idx: int) -> tuple[int, str]:
        return idx, translate_chunk(chunks[idx])

    results: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=config.LLM_CONCURRENCY) as pool:
        for idx, translated in pool.map(worker, range(len(chunks))):
            results[idx] = translated
            print(f"    [{len(results)}/{len(chunks)}] 块完成", flush=True)
    return "\n\n".join(results[i] for i in range(len(chunks)))


def translate_article(ws: Workspace, num: int, force: bool = False) -> Path | None:
    """翻译一篇英文文章，输出 zh md。返回输出路径；跳过返回 None。"""
    en_path = ws.en_md(num)
    if not en_path:
        print(f"  [{num:02d}] 未找到英文原文，跳过")
        return None
    zh_path = ws.zh_md(num)
    if zh_path.exists() and not force:
        print(f"  [{num:02d}] 中文版已存在，跳过 ({zh_path.name})")
        return zh_path

    doc = parse_article_doc(en_path.read_text(encoding="utf-8"))
    print(f"  [{num:02d}] {doc.title}  ({provider_info()})")

    title_zh = translate_text(doc.title)
    body_zh = translate_text(doc.body)
    translation = f"**{title_zh}**\n\n{body_zh}".strip()

    zh_path.write_text(build_zh_md(title_zh, doc.meta, translation), encoding="utf-8")
    print(f"  [{num:02d}] -> {zh_path}")
    return zh_path


def main():
    ap = argparse.ArgumentParser(description="LLM 翻译：英文文章 → 中文文章")
    ap.add_argument("--num", type=int, help="文章编号")
    ap.add_argument("--all", action="store_true", help="翻译全部文章")
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--force", action="store_true", help="已存在也重新翻译")
    args = ap.parse_args()

    print(f"翻译引擎: llm ({provider_info()})")
    ws = get_workspace(args.workspace)
    nums = ws.all_en_nums() if (args.all or not args.num) else [args.num]
    for num in nums:
        translate_article(ws, num, force=args.force)


if __name__ == "__main__":
    main()
