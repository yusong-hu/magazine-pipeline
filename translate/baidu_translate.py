"""百度翻译模块 — 把英文文章 md 翻译为中文文章 md。

用法:
    python -m translate.baidu_translate --num 1 --workspace economist-2026-08-22
    python -m translate.baidu_translate --all

设计:
  - 按段落分块（每块 <= BAIDU_MT_MAX_CHARS 字符），保留段落边界
  - 并发受 BAIDU_MT_CONCURRENCY 限制，避免触发限流
  - 限流/失败按 BAIDU_MT_RETRY_WAIT 秒退避重试
  - 已存在的 zh md 默认跳过（--force 覆盖）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from core.contract import Workspace, get_workspace
from core.http import HTTPError, request as http_request
from core.markdown_utils import build_zh_md, parse_article_doc
from core.text_utils import split_into_chunks


def translate_chunk(text: str, from_lang: str = "en", to_lang: str = "zh") -> str:
    """翻译单个文本块，限流时退避重试。"""
    payload = json.dumps({"from": from_lang, "to": to_lang, "q": text},
                         ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {config.BAIDU_MT_TOKEN}",
    }
    for attempt in range(config.BAIDU_MT_MAX_RETRIES):
        try:
            status, body = http_request("POST", config.BAIDU_MT_URL,
                                        data=payload, headers=headers, timeout=60)
            result = json.loads(body)
            # 百度限流: HTTP 418/429 或 error_code 18 (QPS 超限)
            err = result.get("error_code")
            if status in (418, 429) or err == "18":
                wait = config.BAIDU_MT_RETRY_WAIT * (attempt + 1)
                print(f"    限流，{wait}s 后重试...", flush=True)
                time.sleep(wait)
                continue
            if err:
                raise RuntimeError(f"百度翻译错误 {err}: {result.get('error_msg')}")
            lines = [item.get("dst", "") for item in result["result"]["trans_result"]]
            # trans_result 按原文本的 \n 拆分，需重新拼回
            return "\n".join(lines)
        except (HTTPError, KeyError, json.JSONDecodeError) as e:
            if attempt == config.BAIDU_MT_MAX_RETRIES - 1:
                raise
            print(f"    请求异常({e})，{config.BAIDU_MT_RETRY_WAIT}s 后重试...", flush=True)
            time.sleep(config.BAIDU_MT_RETRY_WAIT)
    raise RuntimeError("翻译重试次数耗尽")


def translate_text(text: str, from_lang: str = "en", to_lang: str = "zh") -> str:
    """并发翻译整篇文本（含分块与限流退避）。"""
    chunks = split_into_chunks(text, config.BAIDU_MT_MAX_CHARS)
    if not chunks:
        return ""
    print(f"    分块: {len(chunks)} 块 (并发 {config.BAIDU_MT_CONCURRENCY})", flush=True)

    def worker(idx: int) -> tuple[int, str]:
        return idx, translate_chunk(chunks[idx], from_lang, to_lang)

    results: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=config.BAIDU_MT_CONCURRENCY) as pool:
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
    print(f"  [{num:02d}] {doc.title}")

    title_zh = translate_text(doc.title)
    body_zh = translate_text(doc.body)
    translation = f"**{title_zh}**\n\n{body_zh}".strip()

    zh_path.write_text(build_zh_md(title_zh, doc.meta, translation), encoding="utf-8")
    print(f"  [{num:02d}] -> {zh_path}")
    return zh_path


def main():
    ap = argparse.ArgumentParser(description="百度翻译：英文文章 → 中文文章")
    ap.add_argument("--num", type=int, help="文章编号")
    ap.add_argument("--all", action="store_true", help="翻译全部文章")
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--force", action="store_true", help="已存在也重新翻译")
    args = ap.parse_args()

    ws = get_workspace(args.workspace)
    nums = ws.all_en_nums() if (args.all or not args.num) else [args.num]
    for num in nums:
        translate_article(ws, num, force=args.force)


# ---------- 逐句容错翻译（LLM 回退路径） ----------
# 按句子边界切分（英文 .!? 后的空白/行尾），句炸不切分缩写类特殊情况可接受
_SENT_RE = re.compile(r"(?<=[.!?])(?=\s|$)")


def _split_sentences(para: str) -> list[str]:
    """按句粒度切分一段文本（整段为空则返回空列表），句子去除首尾空白。"""
    if not para.strip():
        return []
    return [p.strip() for p in _SENT_RE.split(para) if p.strip()]


def translate_text_sentences(text: str, from_lang: str = "en", to_lang: str = "zh") -> str:
    """逐句翻译整篇文本，单句失败则跳过（保留原句），不中断。

    段落（\\n\\n 分隔）结构保留；逐句容错，适用于 LLM 触敏回退场景。
    """
    paras = text.split("\n\n")
    out_paras = []
    for para in paras:
        if not para.strip():
            out_paras.append(para)
            continue
        # 单段内部的超长连续（如代码块/长行）整体分块翻译；否则逐句
        if len(para) <= config.BAIDU_MT_MAX_CHARS:
            sentences = _split_sentences(para)
            pieces = []
            for s in sentences:
                try:
                    pieces.append(translate_chunk(s, from_lang, to_lang))
                except Exception:
                    pieces.append(s)  # 该句失败：保留原文，跳过不中断
            out_paras.append(" ".join(pieces))
        else:
            try:
                out_paras.append(translate_text(para, from_lang, to_lang))
            except Exception:
                out_paras.append(para)  # 超长段失败：整体保留原文
    return "\n\n".join(out_paras)


def translate_article_sentences(ws: Workspace, num: int, force: bool = False) -> Path | None:
    """逐句百度翻译一篇（单句失败跳过），返回输出路径；跳过返回 None。"""
    en_path = ws.en_md(num)
    if not en_path:
        print(f"  [{num:02d}] 未找到英文原文，跳过")
        return None
    zh_path = ws.zh_md(num)
    if zh_path.exists() and not force:
        print(f"  [{num:02d}] 中文版已存在，跳过 ({zh_path.name})")
        return zh_path

    doc = parse_article_doc(en_path.read_text(encoding="utf-8"))
    print(f"  [{num:02d}] {doc.title}  （逐句百度回退）")

    title_zh = translate_text_sentences(doc.title)
    body_zh = translate_text_sentences(doc.body)
    translation = f"**{title_zh}**\n\n{body_zh}".strip()

    zh_path.write_text(build_zh_md(title_zh, doc.meta, translation), encoding="utf-8")
    print(f"  [{num:02d}] -> {zh_path}")
    return zh_path


if __name__ == "__main__":
    main()
