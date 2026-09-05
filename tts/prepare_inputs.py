"""TTS 输入预处理 — 为每篇文章生成 3 个朗读输入文件。

用法:
    python -m tts.prepare_inputs --num 1 [--workspace xxx]
    python -m tts.prepare_inputs --all

产出 (workspace/tts_inputs/NN_tts/):
  01_en.md     英文正文（纯文本）
  02_zh_tr.md  中文全文翻译（纯文本）
  03_zh_an.md  中文解析（纯文本，可能为空则不生成）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.contract import Workspace, get_workspace
from core.markdown_utils import markdown_to_plain_text, parse_article_doc


def prepare_article(ws: Workspace, num: int) -> bool:
    en_path = ws.en_md(num)
    zh_path = ws.zh_md(num)
    if not en_path:
        print(f"  [{num:02d}] 无英文原文，跳过")
        return False
    if not zh_path.exists():
        print(f"  [{num:02d}] 无中文翻译，跳过")
        return False

    en_doc = parse_article_doc(en_path.read_text(encoding="utf-8"))
    zh_doc = parse_article_doc(zh_path.read_text(encoding="utf-8"))

    out_dir = ws.tts_input_dir(num)
    out_dir.mkdir(parents=True, exist_ok=True)

    ws.tts_input(num, "en").write_text(
        markdown_to_plain_text(en_doc.body), encoding="utf-8")
    ws.tts_input(num, "zh_tr").write_text(
        markdown_to_plain_text(zh_doc.translation), encoding="utf-8")

    made = [f"EN {len(en_doc.body)}", f"ZH-tr {len(zh_doc.translation)}"]
    if zh_doc.analysis.strip():
        ws.tts_input(num, "zh_an").write_text(
            markdown_to_plain_text(zh_doc.analysis), encoding="utf-8")
        made.append(f"ZH-an {len(zh_doc.analysis)}")
    print(f"  [{num:02d}] {en_doc.title}  ({', '.join(made)} chars)")
    return True


def main():
    ap = argparse.ArgumentParser(description="生成 TTS 朗读输入文件")
    ap.add_argument("--num", type=int)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--workspace", default=None)
    args = ap.parse_args()

    ws = get_workspace(args.workspace)
    nums = ws.all_en_nums() if (args.all or not args.num) else [args.num]
    count = sum(prepare_article(ws, n) for n in nums)
    print(f"\n预处理完成: {count} 篇 → {ws.tts_inputs_dir}")


if __name__ == "__main__":
    main()
