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
from core.llm_client import LLMError, chat_with_retry, provider_info
from core.markdown_utils import build_zh_md, parse_article_doc
from core.text_utils import split_into_chunks

TRANSLATE_SYSTEM = (
    "你是严格的英文杂志翻译引擎，只输出中文译文。"
    "你的全部输出必须是纯中文译文，不得出现任何英文单词、句子或段落，"
    "不得复述或对照原文，不得给出任何解释、序言或评论。"
    "这是铁律，违反即失败。"
)

TRANSLATE_PROMPT = """把下面一段英文 Markdown 翻译成严格、纯净的中文译文。这是机器翻译任务，必须逐条遵守：

1.【只输出译文】你的输出必须完全是中文译文，禁止出现任何英文原文单词、句子或段落。
   即使是专有名词（人名、作品名、机构名）也一律只用中文译名，禁止附带英文。
2.【零附加】禁止复述原文、禁止中英文对照、禁止评论、禁止任何解释或见解。
3.【零标签】禁止输出"原文""译文""翻译如下""注："等任何标签或引导语，直接给出译文本体。
4.【结构不变】空行分隔的段落一一对应，不合并、不拆分、不增删段落；保留 Markdown 标记（# * - > 等）与文内超链接地址。
5.【忠实流畅】忠实原意，语句通顺，符合中文杂志出版水准。

铁律：最终输出 = 与输入段落数相同的中文译文。除中文译文外，一个多余的英文字母、一个多余单词，都不准出现。

英文原文：

{text}"""


def _clean(text: str) -> str:
    """去掉模型偶发的包裹（代码围栏/引号）与首尾空白。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


# 译文里 ASCII 英文字母占比超过该阈值即判定为“夹带英文原文”
_EN_MAX_ASCII_RATIO = 0.20


def _is_clean(text: str) -> bool:
    """校验译文纯度：剔除超链接后，英文（ASCII）字符占比须远低于中文。

    中文译文中的英文主要来自 URL 等链接，先剔除再统计，避免误判。
    """
    body = re.sub(r"\(https?://[^)\s]+\)", "", text)       # 去掉 [x](url)
    body = re.sub(r"https?://[^\s)]+", "", body)           # 去掉裸 url
    ascii_n = len(re.findall(r"[A-Za-z]", body))
    zh_n = len(re.findall(r"[\u4e00-\u9fff]", body))
    total = ascii_n + zh_n
    if total == 0:
        return True
    return ascii_n / total < _EN_MAX_ASCII_RATIO


def translate_chunk(text: str) -> str:
    """翻译单个文本块：LLM 调用 + 纯度校验（含重试）。"""
    result = _clean(chat_with_retry(
        TRANSLATE_PROMPT.format(text=text), system=TRANSLATE_SYSTEM))
    # if not _is_clean(result):
        # 输出仍夹杂英文 → 抛错，交由 chat_with_retry 重试
        # raise LLMError("译文夹带过多英文原文，重试")
    return result


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
