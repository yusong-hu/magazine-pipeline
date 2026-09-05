"""统一 Joplin 导入 — 合并旧版 v1/v2/auto 三个脚本的核心逻辑。

用法:
    python -m importer.import_joplin --num 1 [--workspace xxx]
    python -m importer.import_joplin --all
    python -m importer.import_joplin --watch        # 持续监控模式

笔记结构（6 分区，3/6 视解析内容可选）:
  1. 英文全文朗读 (en.mp3)
  2. 中文全文朗读 (zh_tr.mp3)
  3. 中文解析朗读 (zh_an.mp3, 可选)
  4. 英文原文
  5. 中文全文翻译
  6. 中文解析 (可选)

去重: 状态文件 + Joplin 标题查询双重检查。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from core.contract import Workspace, get_workspace
from core.joplin_client import JoplinClient
from core.markdown_utils import parse_article_doc


def load_state(ws: Workspace) -> dict:
    f = ws.state_file("imported")
    if f.exists():
        return json.loads(f.read_text())
    return {"imported": {}}


def save_state(ws: Workspace, state: dict) -> None:
    ws.state_file("imported").write_text(
        json.dumps(state, indent=2, ensure_ascii=False))


def build_note_body(title: str, en_doc, zh_doc, audio_ids: dict, audio_names: dict) -> str:
    """组装 6 分区笔记正文。"""
    parts = [f"# {title}\n\n"]

    meta = []
    for k in ("栏目", "作者", "日期", "来源"):
        v = zh_doc.meta.get(k) or en_doc.meta.get(k)
        if v:
            meta.append(f"**{k}**: {v}")
    if meta:
        parts.append(" · ".join(meta) + "\n\n---\n\n")

    sections = [
        ("1. 英文全文朗读", "en", "🎧 Listen to English full text"),
        ("2. 中文全文朗读", "zh_tr", "🎧 中文全文翻译朗读"),
        ("3. 中文解析朗读", "zh_an", "🎧 中文解析朗读"),
    ]
    for heading, kind, label in sections:
        rid = audio_ids.get(kind)
        if rid:
            parts.append(f"## {heading}\n\n")
            parts.append(f"**{label}** → [▶ {audio_names[kind]}](:/{rid} )\n\n")
            parts.append("---\n\n")

    parts.append("## 4. 英文原文\n\n")
    parts.append(en_doc.body.strip())
    parts.append("\n\n---\n\n")

    parts.append("## 5. 中文全文翻译\n\n")
    parts.append(zh_doc.translation.strip())

    if zh_doc.analysis.strip():
        parts.append("\n\n---\n\n## 6. 中文解析\n\n")
        parts.append(zh_doc.analysis.strip())
    parts.append("\n")
    return "".join(parts)


def import_article(ws: Workspace, client: JoplinClient, notebook_id: str,
                   num: int, state: dict, force: bool = False) -> str | None:
    """导入一篇文章。返回 note_id；跳过返回 None。"""
    en_path = ws.en_md(num)
    zh_path = ws.zh_md(num)
    if not en_path or not zh_path or not zh_path.exists():
        print(f"  [{num:02d}] 缺少英文或中文文档，跳过")
        return None

    en_doc = parse_article_doc(en_path.read_text(encoding="utf-8"))
    zh_doc = parse_article_doc(zh_path.read_text(encoding="utf-8"))

    # 标题: 中文标题 + 编号 + 后缀
    clean = zh_doc.title or en_doc.title
    note_title = f"{num:03d}. {clean} {config.NOTE_TITLE_SUFFIX}"

    old_note_id = state["imported"].get(str(num), {}).get("note_id")
    if not force:
        if old_note_id:
            print(f"  [{num:02d}] 已导入过（状态文件），跳过")
            return None
        if client.find_note_by_title(note_title):
            print(f"  [{num:02d}] Joplin 中已存在，跳过")
            return None

    # 上传音频（缺哪个跳哪个）
    audio_ids, audio_names = {}, {}
    for kind in ("en", "zh_tr", "zh_an"):
        p = ws.audio(num, kind)
        if p.exists() and p.stat().st_size > 0:
            print(f"  [{num:02d}] 上传 {kind} 音频...", flush=True)
            audio_ids[kind] = client.upload_resource(p)
            audio_names[kind] = p.name

    if not audio_ids.get("en") and not audio_ids.get("zh_tr"):
        print(f"  [{num:02d}] 无任何音频（TTS 未完成），跳过")
        return None

    body = build_note_body(note_title, en_doc, zh_doc, audio_ids, audio_names)

    # force 模式: 已有笔记则原地更新（如补充解析后重建），否则创建
    if force and old_note_id:
        client.update_note(old_note_id, body, title=note_title)
        state["imported"][str(num)] = {
            "title": note_title, "note_id": old_note_id,
            "updated_at": time.time(),
        }
        save_state(ws, state)
        print(f"  [{num:02d}] ✓ 已更新笔记: {note_title}")
        return old_note_id

    note_id = client.create_note(notebook_id, note_title, body)
    state["imported"][str(num)] = {
        "title": note_title, "note_id": note_id, "imported_at": time.time(),
    }
    save_state(ws, state)
    print(f"  [{num:02d}] ✓ 已创建笔记: {note_title}")
    return note_id


def scan_and_import(ws: Workspace, client: JoplinClient, notebook_id: str,
                    nums: list[int] | None = None, force: bool = False) -> int:
    state = load_state(ws)
    targets = nums if nums else ws.all_en_nums()
    count = 0
    for num in targets:
        try:
            if import_article(ws, client, notebook_id, num, state, force):
                count += 1
        except Exception as e:
            print(f"  [{num:02d}] 导入失败: {e}")
    if count:
        print(f"--- 本次导入 {count} 篇 ---")
    return count


def main():
    ap = argparse.ArgumentParser(description="导入文章到 Joplin")
    ap.add_argument("--num", type=int)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--watch", action="store_true", help="持续监控模式（每 2 分钟扫描）")
    ap.add_argument("--force", action="store_true", help="忽略去重强制导入")
    ap.add_argument("--workspace", default=None)
    args = ap.parse_args()

    ws = get_workspace(args.workspace)
    client = JoplinClient()
    notebook_id = client.resolve_notebook_id(ws.name)
    print(f"目标笔记本: {ws.name} ({notebook_id})")

    nums = None if (args.all or args.watch or not args.num) else [args.num]
    if args.watch:
        print("监控模式启动（Ctrl+C 退出）...")
        while True:
            try:
                scan_and_import(ws, client, notebook_id)
            except Exception as e:
                print(f"扫描异常: {e}")
            time.sleep(120)
    else:
        scan_and_import(ws, client, notebook_id, nums, force=args.force)


if __name__ == "__main__":
    main()
