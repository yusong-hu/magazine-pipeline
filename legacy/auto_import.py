"""Auto-import: scan for completed article audios and import to Joplin.

For each article where all 3 audios exist (en, zh_tr, zh_an), import to Joplin.
Runs continuously, checking every 60s. Logs results.
"""
from __future__ import annotations

import re
import sys
import time
import json
from pathlib import Path
from typing import Optional, Tuple

import requests

JOPLIN_BASE = "http://127.0.0.1:41184"
JOPLIN_TOKEN = "<已移除：经环境变量或 config_local.py 配置>"
NOTEBOOK_ID = "1e80b71a80814a7b98e4246368ad5a55"  # 21_英文杂志

ARTICLES_DIR = Path("/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/articles")
ARTICLES_ZH_DIR = Path("/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/articles-zh")
AUDIO_DIR = Path("/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/audio")
STATE_FILE = Path("/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/.imported-notes.json")


def joplin_request(method, path, **kwargs):
    url = f"{JOPLIN_BASE}{path}?token={JOPLIN_TOKEN}"
    if method == "GET":
        r = requests.get(url, params=kwargs, timeout=60)
    elif method == "POST":
        r = requests.post(url, json=kwargs.get("json"), timeout=120)
    elif method == "DELETE":
        r = requests.delete(url, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"Joplin API error {r.status_code}: {r.text[:300]}")
    return r.json() if r.text else {}


def upload_resource(audio_path: Path) -> str:
    import mimetypes
    mime, _ = mimetypes.guess_type(str(audio_path))
    if not mime:
        mime = "audio/mpeg"
    props = json.dumps({"filename": audio_path.name, "mime": mime})
    with open(audio_path, "rb") as f:
        files = {"data": (audio_path.name, f, mime)}
        data = {"props": props}
        r = requests.post(
            f"{JOPLIN_BASE}/resources?token={JOPLIN_TOKEN}",
            files=files, data=data, timeout=300,
        )
    if r.status_code >= 400:
        raise RuntimeError(f"Resource upload failed {r.status_code}: {r.text[:300]}")
    result = r.json()
    if "error" in result:
        raise RuntimeError(f"Resource upload error: {result['error']}")
    return result["id"]


def split_zh_into_parts(zh_md_text: str) -> Tuple[str, str]:
    """Split Chinese article into (translation, analysis) parts."""
    m = re.search(r"^##\s+中文全文翻译", zh_md_text, re.MULTILINE)
    if not m:
        return zh_md_text, ""
    m2 = re.search(r"^##\s+", zh_md_text[m.end():], re.MULTILINE)
    if m2:
        translation = zh_md_text[m.end():m.end() + m2.start()].strip()
        analysis = zh_md_text[m.end() + m2.start():].strip()
    else:
        translation = zh_md_text[m.end():].strip()
        analysis = ""
    return translation, analysis


def split_en_into_body(en_md_text: str) -> str:
    m = re.search(r"^---\n\n", en_md_text, re.MULTILINE)
    if m:
        return en_md_text[m.end():].strip()
    return en_md_text


def find_existing_note(title: str) -> Optional[str]:
    """Check if a note with this title already exists in the notebook."""
    r = requests.get(
        f"{JOPLIN_BASE}/notes?token={JOPLIN_TOKEN}",
        params={"query": title, "fields": "id,title", "limit": 5},
        timeout=30,
    )
    for n in r.json().get("items", []):
        if n.get("title") == title:
            return n["id"]
    return None


def import_article(num: str) -> Optional[dict]:
    """Import one article. Returns dict if imported, None if skipped."""
    # Find files
    en_md_path = next(ARTICLES_DIR.glob(f"{num}_*.md"), None)
    zh_candidates = [
        ARTICLES_ZH_DIR / f"{int(num):02d}_zh.md",
        ARTICLES_ZH_DIR / f"{int(num):03d}_zh.md",
    ]
    zh_md_path = next((p for p in zh_candidates if p.exists()), None)

    if not en_md_path or not zh_md_path:
        return None

    en_audio = AUDIO_DIR / num / "en.mp3"
    zh_tr_audio = AUDIO_DIR / num / "zh_tr.mp3"
    zh_an_audio = AUDIO_DIR / num / "zh_an.mp3"

    if not (en_audio.exists() and zh_tr_audio.exists() and zh_an_audio.exists()):
        return None

    # Load state
    state = {"imported": {}}
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())

    # Parse article
    en_text = en_md_path.read_text(encoding="utf-8")
    zh_text = zh_md_path.read_text(encoding="utf-8")

    # Extract title from ZH file
    title_match = re.search(r"^#\s+(.+?)$", zh_text, re.MULTILINE)
    zh_title = title_match.group(1).strip() if title_match else en_md_path.stem
    clean_title = re.sub(r"^\d+\.\s+", "", zh_title)
    clean_title = re.sub(r"\s*—.*$", "", clean_title).strip()
    note_title = f"{int(num):03d}. {clean_title} — 英中对照 + 文章讲解"

    # Check if already imported
    note_id = find_existing_note(note_title)
    if note_id or state["imported"].get(num):
        return {"num": num, "skipped": "already exists", "note_id": note_id}

    # Frontmatter
    front = {}
    m = re.match(r"^#\s+.+?\n\n((?:>.*\n)+\n)?---", en_text, re.DOTALL)
    if m:
        block = m.group(1) or ""
        for line in block.splitlines():
            line = line.strip().lstrip(">").strip()
            if line.startswith("**"):
                m2 = re.match(r"\*\*([^:]+)\*\*:\s*(.+)", line)
                if m2:
                    front[m2.group(1).strip()] = m2.group(2).strip()

    en_body = split_en_into_body(en_text)
    zh_translation, zh_analysis = split_zh_into_parts(zh_text)

    # Upload 3 audios
    print(f"  [{num}] uploading audios...")
    en_id = upload_resource(en_audio)
    zh_tr_id = upload_resource(zh_tr_audio)
    zh_an_id = upload_resource(zh_an_audio)
    print(f"  [{num}] resources: {en_id[:8]}, {zh_tr_id[:8]}, {zh_an_id[:8]}")

    # Build 6-section body
    parts = [f"# {note_title}\n\n"]
    meta = []
    for k in ("栏目", "作者", "日期", "来源"):
        if front.get(k):
            meta.append(f"**{k}**: {front[k]}")
    if meta:
        parts.append(" · ".join(meta) + "\n\n---\n\n")

    parts.append("## 1. 英文全文朗读\n\n")
    parts.append(f"**🎧 Listen to English full text** → [▶ {en_audio.name}](:/{en_id} )\n\n")
    parts.append("---\n\n")

    parts.append("## 2. 中文全文朗读\n\n")
    parts.append(f"**🎧 中文全文翻译朗读** → [▶ {zh_tr_audio.name}](:/{zh_tr_id} )\n\n")
    parts.append("---\n\n")

    parts.append("## 3. 中文解析朗读\n\n")
    parts.append(f"**🎧 中文解析朗读** → [▶ {zh_an_audio.name}](:/{zh_an_id} )\n\n")
    parts.append("---\n\n")

    parts.append("## 4. 英文原文\n\n")
    parts.append(en_body.strip())
    parts.append("\n\n---\n\n")

    parts.append("## 5. 中文全文翻译\n\n")
    parts.append(zh_translation.strip())
    parts.append("\n\n---\n\n")

    if zh_analysis:
        parts.append("## 6. 中文解析\n\n")
        parts.append(zh_analysis.strip())
        parts.append("\n")

    body = "".join(parts)

    # Create note
    print(f"  [{num}] creating note ({len(body)} chars)...")
    result = joplin_request(
        "POST", "/notes",
        json={
            "parent_id": NOTEBOOK_ID,
            "title": note_title,
            "body": body,
            "source": "markdown",
        },
    )
    note_id = result["id"]
    state["imported"][num] = {
        "title": note_title,
        "note_id": note_id,
        "imported_at": time.time(),
    }
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    print(f"  [{num}] -> note_id: {note_id}")
    return state["imported"][num]


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "once"

    if mode == "loop":
        interval = 120  # 2 minutes
        print(f"Auto-import loop: checking every {interval}s")
        while True:
            try:
                scan_and_import()
            except Exception as e:
                print(f"Error: {e}")
            time.sleep(interval)
    else:
        scan_and_import()


def scan_and_import():
    audio_dirs = sorted([d for d in AUDIO_DIR.iterdir() if d.is_dir() and d.name.isdigit()])
    imported_count = 0
    for d in audio_dirs:
        num = d.name
        try:
            r = import_article(num)
            if r and "skipped" not in r:
                imported_count += 1
                print(f"[{num}] ✓ imported: {r['title']}")
        except Exception as e:
            print(f"[{num}] error: {e}")
    if imported_count:
        print(f"--- {imported_count} new import(s) this cycle ---")
    return imported_count


if __name__ == "__main__":
    main()
