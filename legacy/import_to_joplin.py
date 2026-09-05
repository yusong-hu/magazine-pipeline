"""Upload article audio (English + Chinese) to Joplin, then create a note
with the audio embedded at the top.

For each article in articles/:
  1. Upload English audio as a Joplin resource
  2. Upload Chinese audio as a Joplin resource
  3. Create a Joplin note under 21_英文杂志 with:
       - English audio player
       - Chinese article body (English original + Chinese translation + analysis)
       - Chinese audio player
       - Markdown body

Usage:
  python import_to_joplin.py [N]
"""
import re
import sys
import time
from pathlib import Path

import requests
import json
import mimetypes

# Joplin config
JOPLIN_BASE = "http://127.0.0.1:41184"
JOPLIN_TOKEN = "<已移除：经环境变量或 config_local.py 配置>"
NOTEBOOK_ID = "1e80b71a80814a7b98e4246368ad5a55"  # 21_英文杂志

ARTICLES_DIR = Path("/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/articles")
AUDIO_DIR = Path("/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/audio")
ARTICLES_ZH_DIR = Path("/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/articles-zh")


def joplin_request(method: str, path: str, **kwargs) -> dict:
    """Make a request to the Joplin API."""
    url = f"{JOPLIN_BASE}{path}?token={JOPLIN_TOKEN}"
    if method == "GET":
        r = requests.get(url, params=kwargs, timeout=30)
    elif method == "POST":
        if "json" in kwargs:
            r = requests.post(url, json=kwargs["json"], timeout=60)
        else:
            r = requests.post(url, data=kwargs.get("data"), timeout=60)
    elif method == "PUT":
        r = requests.put(url, json=kwargs.get("json"), timeout=30)
    elif method == "DELETE":
        r = requests.delete(url, timeout=30)
    else:
        raise ValueError(method)

    if r.status_code >= 400:
        raise RuntimeError(f"Joplin API error: {r.status_code} {r.text[:500]}")
    return r.json() if r.text else {}


def upload_resource(audio_path: Path) -> str:
    """Upload an audio file to Joplin via the Web API.

    Uses multipart/form-data with 'data' (the file) and 'props' (metadata).
    """
    mime, _ = mimetypes.guess_type(str(audio_path))
    if not mime:
        mime = "audio/mpeg"

    props = json.dumps({
        "filename": audio_path.name,
        "mime": mime,
    })

    with open(audio_path, "rb") as f:
        files = {"data": (audio_path.name, f, mime)}
        data = {"props": props}
        r = requests.post(
            f"{JOPLIN_BASE}/resources?token={JOPLIN_TOKEN}",
            files=files, data=data, timeout=300,
        )

    if r.status_code >= 400:
        raise RuntimeError(f"Resource upload failed: {r.status_code} {r.text[:500]}")
    result = r.json()
    if "error" in result:
        raise RuntimeError(f"Resource upload failed: {result['error']}")
    return result["id"]


def extract_frontmatter(md_text: str) -> tuple[dict, str]:
    """Split markdown into (frontmatter dict, body)."""
    front = {}
    body = md_text
    m = re.match(r"^#\s+(.+?)\n\n((?:>.*\n)+\n)?---\n\n", md_text, re.DOTALL)
    if not m:
        return front, md_text

    title = m.group(1).strip()
    front["title"] = title
    block = m.group(2) or ""
    for line in block.splitlines():
        line = line.strip().lstrip(">").strip()
        if line.startswith("**"):
            m2 = re.match(r"\*\*([^:]+)\*\*:\s*(.+)", line)
            if m2:
                front[m2.group(1).strip()] = m2.group(2).strip()
    body = md_text[m.end():]
    return front, body


def get_article_base(en_md_path: Path) -> str:
    """Get the base name used for audio dir, e.g. '02_donald-trump-...'."""
    return en_md_path.stem


def find_zh_article(en_base: str) -> Path | None:
    """Find the Chinese article for a given English base.

    English base: '02_donald-trump-is-still-trying-to-make-it-harder-to-vote'
    Chinese base: '02_zh' (because the chinese file is named 'NN_zh.md')
    """
    # Extract the number prefix from the English base
    m = re.match(r"^(\d+)_", en_base)
    if not m:
        return None
    num = m.group(1)
    zh_path = ARTICLES_ZH_DIR / f"{num}_zh.md"
    return zh_path if zh_path.exists() else None


def find_audio(audio_dir_name: str, lang: str = "en") -> Path | None:
    """Find the audio file for a given article dir name.

    audio_dir_name: e.g. '02_donald-trump-...'
    lang: 'en' or 'zh'
    """
    if lang == "en":
        p = AUDIO_DIR / audio_dir_name / "final.mp3"
    else:
        # Chinese: audio/02_zh/final.mp3
        # Extract number prefix
        m = re.match(r"^(\d+)_", audio_dir_name)
        if not m:
            return None
        p = AUDIO_DIR / f"{m.group(1)}_zh" / "final.mp3"
    return p if p.exists() else None


def build_audio_block(resource_id: str, lang: str, filename: str) -> str:
    """Markdown link block for one language.

    Joplin's only reliable way to embed audio is a plain markdown link
    with the `:/RESOURCE_ID` syntax. Clicking the link opens the resource
    in Joplin's built-in media viewer (which plays audio).
    HTML <audio> tags do NOT work in Joplin notes.
    """
    label = "🇺🇸 English" if lang == "en" else "🇨🇳 中文（含解析）"
    return f"**🎧 {label} 朗读** → [▶ {filename}](:/{resource_id} )\n\n"


def import_article(en_md_path: Path, skip_missing_audio: bool = True):
    """Import one article: upload EN+ZH audio, create one combined note."""
    en_base = get_article_base(en_md_path)
    en_audio = find_audio(en_base, "en")
    zh_md = find_zh_article(en_base)
    zh_audio = find_audio(en_base, "zh")

    # Resolve what to use for title/author
    en_text = en_md_path.read_text(encoding="utf-8")
    front, en_body = extract_frontmatter(en_text)
    title = front.get("title", en_base)

    # For author/date: prefer Chinese frontmatter if available
    if zh_md:
        zh_text = zh_md.read_text(encoding="utf-8")
        zh_front, zh_body = extract_frontmatter(zh_text)
        # Use the Chinese version's title which is more descriptive
        if zh_front.get("title"):
            title = zh_front["title"]
        author = zh_front.get("作者") or front.get("作者", "")
        section = zh_front.get("栏目") or front.get("栏目", "")
        date = zh_front.get("日期") or front.get("日期", "")
    else:
        author = front.get("作者", "")
        section = front.get("栏目", "")
        date = front.get("日期", "")
        zh_body = ""

    print(f"\n=== {title} ===")
    print(f"    author: {author}")
    print(f"    section: {section}")
    print(f"    date: {date}")
    print(f"    EN audio: {en_audio}")
    print(f"    ZH audio: {zh_audio}")
    print(f"    ZH md: {zh_md}")

    # 1. Upload English audio
    en_audio_id = None
    if en_audio:
        print("    uploading EN audio ...")
        en_audio_id = upload_resource(en_audio)
        print(f"    -> EN resource: {en_audio_id}")
    elif skip_missing_audio:
        print("    SKIP: EN audio not found")
        return None

    # 2. Upload Chinese audio
    zh_audio_id = None
    if zh_audio:
        print("    uploading ZH audio ...")
        zh_audio_id = upload_resource(zh_audio)
        print(f"    -> ZH resource: {zh_audio_id}")

    # 3. Build note body
    body_parts = []

    # Header
    header = f"# {title}\n\n"
    meta_lines = []
    if section:
        meta_lines.append(f"**栏目**: {section}")
    if author:
        meta_lines.append(f"**作者**: {author}")
    if date:
        meta_lines.append(f"**日期**: {date}")
    meta_lines.append(f"**来源**: The New Yorker, 2026-08-24")
    header += " · ".join(meta_lines) + "\n\n---\n\n"
    body_parts.append(header)

    # Audio blocks at the top
    if en_audio_id:
        body_parts.append(build_audio_block(en_audio_id, "en", en_audio.name))
    if zh_audio_id:
        body_parts.append(build_audio_block(zh_audio_id, "zh", zh_audio.name))

    # English body (original article)
    body_parts.append("## 🇺🇸 English Original\n\n")
    body_parts.append(en_body.strip())
    body_parts.append("\n\n---\n\n")

    # Chinese body (translation + analysis)
    if zh_body:
        body_parts.append("## 🇨🇳 中文翻译 + 解析\n\n")
        body_parts.append(zh_body.strip())
        body_parts.append("\n")

    note_body = "".join(body_parts)

    # 4. Create note
    print(f"    creating note (body: {len(note_body)} chars) ...")
    result = joplin_request(
        "POST", "/notes",
        json={
            "parent_id": NOTEBOOK_ID,
            "title": title,
            "body": note_body,
            "source": "markdown",
        },
    )
    if "error" in result:
        raise RuntimeError(f"Note creation failed: {result['error']}")
    note_id = result["id"]
    print(f"    -> note_id: {note_id}")

    return {
        "title": title,
        "en_audio_path": str(en_audio) if en_audio else None,
        "en_audio_resource_id": en_audio_id,
        "zh_audio_path": str(zh_audio) if zh_audio else None,
        "zh_audio_resource_id": zh_audio_id,
        "note_id": note_id,
    }


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else None
    md_files = sorted(ARTICLES_DIR.glob("*.md"))
    if n:
        md_files = md_files[:n]

    print(f"Importing {len(md_files)} articles to Joplin notebook 21_英文杂志 ...")
    print(f"(EN audio + ZH audio + Chinese translation+analysis)")

    results = []
    for md_path in md_files:
        try:
            r = import_article(md_path)
            if r:
                results.append(r)
        except Exception as e:
            print(f"    ERROR: {e}")
            raise

    print(f"\n=== Done. {len(results)} articles imported. ===")
    for r in results:
        print(f"  - {r['title']}")
        print(f"      note: joplin://note/{r['note_id']}")


if __name__ == "__main__":
    main()
