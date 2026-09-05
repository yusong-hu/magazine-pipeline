"""Import 3 audios (EN full, ZH translation, ZH analysis) per article and
create a 6-section Joplin note.

Structure:
  1. 英文全文朗读 (audio)
  2. 中文全文朗读 (audio)
  3. 中文解析朗读 (audio)
  4. 英文原文 (text)
  5. 中文全文翻译 (text)
  6. 中文解析 (text)

Title format: "NNN. {title} — 英中对照 + 文章讲解"
"""
import re
import sys
from pathlib import Path

import requests
import json
import mimetypes

JOPLIN_BASE = "http://127.0.0.1:41184"
JOPLIN_TOKEN = "<已移除：经环境变量或 config_local.py 配置>"
NOTEBOOK_ID = "1e80b71a80814a7b98e4246368ad5a55"  # 21_英文杂志

ARTICLES_DIR = Path("/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/articles")
ARTICLES_ZH_DIR = Path("/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/articles-zh")
AUDIO_DIR = Path("/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/audio")


def joplin_request(method, path, **kwargs):
    url = f"{JOPLIN_BASE}{path}?token={JOPLIN_TOKEN}"
    if method == "GET":
        r = requests.get(url, params=kwargs, timeout=60)
    elif method == "POST":
        if "json" in kwargs:
            r = requests.post(url, json=kwargs["json"], timeout=120)
        else:
            r = requests.post(url, data=kwargs.get("data"), timeout=120)
    elif method == "DELETE":
        r = requests.delete(url, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"Joplin API error {r.status_code}: {r.text[:300]}")
    return r.json() if r.text else {}


def upload_resource(audio_path: Path) -> str:
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


def split_zh_into_parts(zh_md_text: str) -> tuple[str, str]:
    """Split Chinese article into (translation, analysis) parts.

    Translation: the prose that mirrors the English original
    Analysis: the 解析 sections (核心主张 through 5 句精读)
    """
    # Find the "## 中文解析" header
    m = re.search(r"^##\s+中文解析", zh_md_text, re.MULTILINE)
    if not m:
        return zh_md_text, ""
    translation = zh_md_text[:m.start()].strip()
    # Strip leading frontmatter from translation
    translation = re.sub(r"^#\s+.+?\n\n", "", translation, flags=re.DOTALL)
    translation = re.sub(r"^>.*\n(\n>.*\n)*\n", "", translation, flags=re.MULTILINE)
    translation = re.sub(r"^---\n\n", "", translation, flags=re.MULTILINE)
    # Find "## 中文全文翻译" - the actual translation body
    m2 = re.search(r"^##\s+中文全文翻译", translation, re.MULTILINE)
    if m2:
        translation = translation[m2.end():].strip()
    analysis = zh_md_text[m.end():].strip()
    analysis = re.sub(r"^---\n", "", analysis, flags=re.MULTILINE)
    return translation, analysis


def split_en_into_body(en_md_text: str) -> str:
    """Extract just the article body (skip the frontmatter)."""
    m = re.search(r"^---\n\n", en_md_text, re.MULTILINE)
    if m:
        return en_md_text[m.end():].strip()
    return en_md_text


def build_audio_link(resource_id: str, label: str, filename: str) -> str:
    return f"**{label}** → [▶ {filename}](:/{resource_id} )\n\n"


def import_article(en_md_path: Path, audio_subdir: str = "02_v2"):
    """Import one article with 3 audios and 6 sections."""
    en_text = en_md_path.read_text(encoding="utf-8")

    # Extract article number
    num_match = re.match(r"^(\d+)_", en_md_path.stem)
    article_num = num_match.group(1) if num_match else "00"

    # Find title (first H1)
    title_match = re.search(r"^#\s+(.+?)$", en_text, re.MULTILINE)
    en_title = title_match.group(1).strip() if title_match else en_md_path.stem

    # Find Chinese article
    zh_md_path = ARTICLES_ZH_DIR / f"{article_num}_zh.md"
    if not zh_md_path.exists():
        print(f"  SKIP: no Chinese version for {article_num}")
        return None

    zh_text = zh_md_path.read_text(encoding="utf-8")
    zh_title_match = re.search(r"^#\s+(.+?)$", zh_text, re.MULTILINE)
    zh_title = zh_title_match.group(1).strip() if zh_title_match else en_title

    # Note title: 3-digit number + clean title + "— 英中对照 + 文章讲解"
    clean_title = re.sub(r"^\d+\.\s+", "", zh_title)  # remove "01. " if present
    # Strip "—— 英中对照 + 文章讲解" or similar suffix
    clean_title = re.sub(r"\s*—.*$", "", clean_title).strip()
    note_title = f"{int(article_num):03d}. {clean_title} — 英中对照 + 文章讲解"

    # Find frontmatter
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

    # Audio paths (3 audios in audio_subdir)
    audio_base = AUDIO_DIR / audio_subdir
    en_audio = audio_base / "en" / "final.mp3"
    zh_tr_audio = audio_base / "zh_tr" / "final.mp3"
    zh_an_audio = audio_base / "zh_an" / "final.mp3"

    # Text bodies
    en_body = split_en_into_body(en_text)
    zh_translation, zh_analysis = split_zh_into_parts(zh_text)

    print(f"\n=== {note_title} ===")
    print(f"  EN audio: {en_audio.exists()}")
    print(f"  ZH tr audio: {zh_tr_audio.exists()}")
    print(f"  ZH an audio: {zh_an_audio.exists()}")

    # Upload 3 audios
    en_id = zh_tr_id = zh_an_id = None
    if en_audio.exists():
        print("  uploading EN audio...")
        en_id = upload_resource(en_audio)
        print(f"    -> {en_id}")
    if zh_tr_audio.exists():
        print("  uploading ZH translation audio...")
        zh_tr_id = upload_resource(zh_tr_audio)
        print(f"    -> {zh_tr_id}")
    if zh_an_audio.exists():
        print("  uploading ZH analysis audio...")
        zh_an_id = upload_resource(zh_an_audio)
        print(f"    -> {zh_an_id}")

    # Build 6-section body
    parts = []
    # Header
    parts.append(f"# {note_title}\n\n")
    meta = []
    if front.get("栏目"):
        meta.append(f"**栏目**: {front['栏目']}")
    if front.get("作者"):
        meta.append(f"**作者**: {front['作者']}")
    if front.get("日期"):
        meta.append(f"**日期**: {front['日期']}")
    if front.get("来源"):
        meta.append(f"**来源**: {front['来源']}")
    if meta:
        parts.append(" · ".join(meta) + "\n\n---\n\n")

    # === Section 1: 英文全文朗读 ===
    if en_id:
        parts.append("## 1. 英文全文朗读\n\n")
        parts.append(build_audio_link(en_id, "🎧 Listen to English full text", en_audio.name))
        parts.append("---\n\n")

    # === Section 2: 中文全文朗读 ===
    if zh_tr_id:
        parts.append("## 2. 中文全文朗读\n\n")
        parts.append(build_audio_link(zh_tr_id, "🎧 中文全文翻译朗读", zh_tr_audio.name))
        parts.append("---\n\n")

    # === Section 3: 中文解析朗读 ===
    if zh_an_id:
        parts.append("## 3. 中文解析朗读\n\n")
        parts.append(build_audio_link(zh_an_id, "🎧 中文解析朗读", zh_an_audio.name))
        parts.append("---\n\n")

    # === Section 4: 英文原文 ===
    parts.append("## 4. 英文原文\n\n")
    parts.append(en_body.strip())
    parts.append("\n\n---\n\n")

    # === Section 5: 中文全文翻译 ===
    parts.append("## 5. 中文全文翻译\n\n")
    parts.append(zh_translation.strip())
    parts.append("\n\n---\n\n")

    # === Section 6: 中文解析 ===
    if zh_analysis:
        parts.append("## 6. 中文解析\n\n")
        parts.append(zh_analysis.strip())
        parts.append("\n")

    body = "".join(parts)

    # Create note
    print(f"  creating note (body: {len(body)} chars)...")
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
    print(f"  -> note_id: {note_id}")
    print(f"  title: {note_title}")

    return {
        "title": note_title,
        "en_id": en_id,
        "zh_tr_id": zh_tr_id,
        "zh_an_id": zh_an_id,
        "note_id": note_id,
    }


def main():
    article_num = sys.argv[1] if len(sys.argv) > 1 else "02"
    audio_subdir = sys.argv[2] if len(sys.argv) > 2 else "02_v2"
    matches = list(ARTICLES_DIR.glob(f"{article_num}_*.md"))
    if not matches:
        print(f"No article found for {article_num}")
        return
    en_md = matches[0]
    print(f"Importing: {en_md}")
    import_article(en_md, audio_subdir=audio_subdir)


if __name__ == "__main__":
    main()
