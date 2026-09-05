"""杂志流水线统一入口 — 一条命令掌握全流程。

用法:
    python pipeline.py extract  --epub TheEconomist.2026.08.22.epub [--limit N]
    python pipeline.py translate --num 1 | --all
    python pipeline.py prepare-tts --num 1 | --all
    python pipeline.py tts       --num 1 | --all
    python pipeline.py import    --num 1 | --all [--watch]
    python pipeline.py run       --num 1          # 翻译→TTS→导入 一键流程

全局参数:
    --workspace NAME    工作区名称（默认 config.DEFAULT_WORKSPACE）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from core.contract import get_workspace
from extract.extract_epub import extract as extract_articles
from translate import translate_article
from analyze.llm_analysis import analyze_article
from tts.prepare_inputs import prepare_article
from tts.generate_audio import generate_audio


def cmd_extract(args):
    outputs = extract_articles(args.epub, args.workspace, args.limit)
    return 0 if outputs else 1


def cmd_translate(args):
    ws = get_workspace(args.workspace)
    nums = ws.all_en_nums() if (args.all or not args.num) else [args.num]
    ok = all(translate_article(ws, n, force=args.force) is not None for n in nums)
    return 0 if ok else 1


def _tts_stage(args, prepare_fn, gen_fn):
    ws = get_workspace(args.workspace)
    nums = ws.all_en_nums() if (args.all or not args.num) else [args.num]
    for n in nums:
        if not prepare_fn(ws, n):
            return 1
        results = gen_fn(ws, n)
        if not (results.get("en") or results.get("zh_tr")):
            print(f"[{n:02d}] 音频生成失败")
            return 1
    return 0


def cmd_analyze(args):
    ws = get_workspace(args.workspace)
    nums = ws.all_en_nums() if (args.all or not args.num) else [args.num]
    ok = all(analyze_article(ws, n, force=args.force) is not None for n in nums)
    return 0 if ok else 1


def cmd_prepare_tts(args):
    ws = get_workspace(args.workspace)
    nums = ws.all_en_nums() if (args.all or not args.num) else [args.num]
    ok = all(prepare_article(ws, n) for n in nums)
    return 0 if ok else 1


def cmd_tts(args):
    return _tts_stage(args, prepare_article, generate_audio)


def cmd_import(args):
    # 延迟导入，避免不需要时初始化 Joplin 连接
    from importer.import_joplin import scan_and_import
    from core.joplin_client import JoplinClient

    ws = get_workspace(args.workspace)
    client = JoplinClient()
    notebook_id = client.resolve_notebook_id()
    print(f"目标笔记本: {config.JOPLIN_NOTEBOOK_NAME} ({notebook_id})")
    nums = None if (args.all or not args.num) else [args.num]
    count = scan_and_import(ws, client, notebook_id, nums, force=args.force)
    return 0 if count >= 0 else 1


def cmd_run(args):
    """翻译 → 解读 → TTS 输入 → 音频 → 导入 Joplin。"""
    ws = get_workspace(args.workspace)
    num = args.num

    print(f"\n===== [1/5] 翻译 =====")
    if translate_article(ws, num, force=args.force) is None:
        return 1

    print(f"\n===== [2/5] LLM 中文解读 =====")
    if analyze_article(ws, num, force=args.force) is None:
        return 1

    print(f"\n===== [3/5] TTS 输入 =====")
    if not prepare_article(ws, num):
        return 1

    print(f"\n===== [4/5] TTS 音频 =====")
    results = generate_audio(ws, num)
    if not (results.get("en") or results.get("zh_tr")):
        print("音频生成失败，中止")
        return 1

    print(f"\n===== [5/5] 导入 Joplin =====")
    from importer.import_joplin import scan_and_import
    from core.joplin_client import JoplinClient
    client = JoplinClient()
    notebook_id = client.resolve_notebook_id()
    print(f"目标笔记本: {config.JOPLIN_NOTEBOOK_NAME} ({notebook_id})")
    scan_and_import(ws, client, notebook_id, [num], force=args.force)
    return 0


def main():
    ap = argparse.ArgumentParser(
        prog="pipeline", description="杂志流水线：提取→翻译→TTS→Joplin")
    # parent parser: --workspace 全局参数，子命令前后均可使用
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace", default=None,
                        help=f"工作区（默认 {config.DEFAULT_WORKSPACE}）")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("extract", parents=[common], help="从 EPUB 提取英文文章")
    p.add_argument("--epub", required=True)
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(func=cmd_extract)

    for name, desc in (("translate", "翻译为中文（引擎见 TRANSLATE_ENGINE: llm|baidu）"),
                       ("analyze", "LLM 生成中文解析"),
                       ("prepare-tts", "生成 TTS 朗读输入"),
                       ("tts", "生成 TTS 音频"),
                       ("import", "导入 Joplin")):
        p = sub.add_parser(name, parents=[common], help=desc)
        p.add_argument("--num", type=int, default=None)
        p.add_argument("--all", action="store_true")
        p.add_argument("--force", action="store_true")
        p.set_defaults(func={"translate": cmd_translate, "analyze": cmd_analyze,
                             "prepare-tts": cmd_prepare_tts, "tts": cmd_tts,
                             "import": cmd_import}[name])

    p = sub.add_parser("run", parents=[common],
                       help="单篇一键流程: 翻译→解读→TTS→导入")
    p.add_argument("--num", type=int, required=True)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_run)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
