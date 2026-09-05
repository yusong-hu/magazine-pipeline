"""整期批量处理 — 循环工作区内每一篇文章，串行走完五阶段全流程。

对每篇: 翻译 → LLM 解读 → TTS 输入 → 音频 → 导入 Joplin。
- 单篇失败不中断：记入失败清单，跳到下一篇，最后统一报告。
- 幂等可续：每阶段对已有产物自动跳过，意外中断后可直接重跑。
- 阶段间强依赖（前半失败则后半跳过），避免半成品流转。

用法:
    python run_issue.py                 # 处理整期全部文章
    python run_issue.py --nums 1 5 12   # 只处理指定编号
    python run_issue.py --force         # 翻译/解读已存在也强制重做
    python run_issue.py --workspace xxx # 指定工作区
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from core.contract import get_workspace
from translate import translate_article
from analyze.llm_analysis import analyze_article
from tts.prepare_inputs import prepare_article
from tts.generate_audio import generate_audio


def process_one(ws, num: int, force: bool) -> bool:
    """处理单篇全流程，返回是否成功。任一必做阶段失败返回 False。"""
    tag = f"[{num:02d}]"
    try:
        # [1/5] 翻译
        if translate_article(ws, num, force=force) is None:
            print(f"{tag} 缺英文原文或翻译失败，跳过")
            return False

        # [2/5] LLM 中文解读
        if analyze_article(ws, num, force=force) is None:
            print(f"{tag} LLM 解读失败，跳过")
            return False

        # [3/5] TTS 输入
        if not prepare_article(ws, num):
            print(f"{tag} TTS 输入生成失败，跳过")
            return False

        # [4/5] 音频（en + zh_tr 任一成功即视为产出）
        audio = generate_audio(ws, num)
        if not (audio.get("en") or audio.get("zh_tr")):
            print(f"{tag} 音频生成失败，跳过导入")
            return False

        # [5/5] 导入 Joplin
        from importer.import_joplin import scan_and_import
        from core.joplin_client import JoplinClient
        client = JoplinClient()
        notebook_id = client.resolve_notebook_id()
        count = scan_and_import(ws, client, notebook_id, [num], force=force)
        if count < 0:
            print(f"{tag} Joplin 导入失败")
            return False
        print(f"{tag} ✓ 完成", flush=True)
        return True
    except Exception as e:  # 单篇异常不中断整期
        print(f"{tag} ✗ 异常: {type(e).__name__}: {e}", flush=True)
        return False


def main():
    ap = argparse.ArgumentParser(
        prog="run_issue", description="整期批量处理：逐篇 翻译→解读→TTS→导入")
    ap.add_argument("--nums", type=int, nargs="*", help="指定文章编号，缺省处理全部")
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--force", action="store_true", help="已存在产物的阶段也强制重做")
    args = ap.parse_args()

    ws = get_workspace(args.workspace)

    # 解析 Joplin 笔记本、建立连接（复用，避免每篇重建）
    from core.joplin_client import JoplinClient
    try:
        client = JoplinClient()
        notebook_id = client.resolve_notebook_id()
        print(f"工作区: {ws.name} | LLM: {config.LLM_PROVIDER} | "
              f"翻译引擎: {config.TRANSLATE_ENGINE}")
        print(f"目标笔记本: {config.JOPLIN_NOTEBOOK_NAME} ({notebook_id})\n")
    except Exception as e:
        print(f"⚠ Joplin 连接异常: {e}", flush=True)
        client, notebook_id = None, None

    if args.nums:
        nums = sorted(set(args.nums))
    else:
        nums = ws.all_en_nums()
    print(f"本次将处理 {len(nums)} 篇\n")

    ok, failed = [], []
    for num in nums:
        if client is None:  # 首次连接失败时逐篇尝试重建
            try:
                from core.joplin_client import JoplinClient
                client = JoplinClient()
                notebook_id = client.resolve_notebook_id()
            except Exception:
                failed.append((num, "Joplin 连接不可用"))
                continue
        ok_ = process_one(ws, num, args.force)
        ok.append(num) if ok_ else failed.append((num, "流程失败"))

    print(f"\n===== 整期汇总 =====")
    print(f"成功: {len(ok)} / {len(nums)}")
    if failed:
        detail = ", ".join(f"{n:02d}({r})" for n, r in failed)
        print(f"失败 {len(failed)} 篇: {detail}")
        return 1
    print("全部完成 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())