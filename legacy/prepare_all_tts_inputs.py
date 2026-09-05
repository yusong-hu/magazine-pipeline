"""Prepare TTS source files for all 20 articles.

For each article, create 3 input files:
  - 01_en.md       (English full text, cleaned)
  - 02_zh_tr.md    (Chinese translation section only)
  - 03_zh_an.md    (Chinese analysis section only)
"""
import re
import sys
from pathlib import Path

ARTICLES_DIR = Path("/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/articles")
ARTICLES_ZH_DIR = Path("/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/articles-zh")
TTS_INPUTS_DIR = Path("/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/tts_inputs")

sys.path.insert(0, '/Users/yusonghu/.minimax/skills/text-to-speech/scripts')
from tts_generate import markdown_to_plain_text


def extract_section(text: str, start_marker: str, end_marker: str = None) -> str:
    """Extract content between start_marker and end_marker (or end of text)."""
    m = re.search(start_marker, text, re.MULTILINE)
    if not m:
        return ""
    start = m.end()
    if end_marker:
        m2 = re.search(end_marker, text[start:], re.MULTILINE)
        if m2:
            return text[start:start + m2.start()].strip()
    return text[start:].strip()


def main():
    TTS_INPUTS_DIR.mkdir(parents=True, exist_ok=True)
    en_files = sorted(ARTICLES_DIR.glob("*.md"))
    summary = []
    for en_path in en_files:
        num_match = re.match(r"^(\d+)_", en_path.stem)
        if not num_match:
            continue
        num = num_match.group(1)  # e.g. "4" or "11"
        # Find corresponding zh file (handles both 04_zh and 011_zh)
        zh_path = None
        for cand in [f"{int(num):02d}_zh.md", f"{int(num):03d}_zh.md"]:
            p = ARTICLES_ZH_DIR / cand
            if p.exists():
                zh_path = p
                break
        if not zh_path:
            print(f"  skip {num}: no zh translation")
            continue

        out_dir = TTS_INPUTS_DIR / f"{num}_tts"
        out_dir.mkdir(exist_ok=True)

        # 1. English full text (cleaned of markdown)
        en_text = en_path.read_text(encoding="utf-8")
        en_body = re.sub(r"^#\s+.+?\n\n", "", en_text, flags=re.DOTALL)
        en_body = re.sub(r"^>.*\n(\n>.*\n)*\n", "", en_body, flags=re.MULTILINE)
        en_body = re.sub(r"^---\n\n", "", en_body, flags=re.MULTILINE)
        en_clean = markdown_to_plain_text(en_body)
        (out_dir / "01_en.md").write_text(en_clean, encoding="utf-8")

        # 2. Chinese translation section: from "## 中文全文翻译" to next "## "
        zh_text = zh_path.read_text(encoding="utf-8")
        zh_tr = extract_section(zh_text, r"^##\s+中文全文翻译", r"^##\s+")
        (out_dir / "02_zh_tr.md").write_text(zh_tr, encoding="utf-8")

        # 3. Chinese analysis section: from "## 中文解析" to end of file
        zh_an = extract_section(zh_text, r"^##\s+中文解析")
        (out_dir / "03_zh_an.md").write_text(zh_an, encoding="utf-8")

        summary.append({
            "num": num,
            "en_chars": len(en_clean),
            "zh_tr_chars": len(zh_tr),
            "zh_an_chars": len(zh_an),
        })

    print(f"Prepared {len(summary)} articles:")
    for s in summary:
        print(f"  {s['num']:>3} | EN {s['en_chars']:>6} | ZH-tr {s['zh_tr_chars']:>6} | ZH-an {s['zh_an_chars']:>6}")
    total_en = sum(s["en_chars"] for s in summary)
    total_tr = sum(s["zh_tr_chars"] for s in summary)
    total_an = sum(s["zh_an_chars"] for s in summary)
    print(f"\nTotal chars:")
    print(f"  EN:   {total_en}  (chunks @ 250: ~{total_en // 250})")
    print(f"  ZH-tr: {total_tr}  (chunks @ 250: ~{total_tr // 250})")
    print(f"  ZH-an: {total_an}  (chunks @ 250: ~{total_an // 250})")


if __name__ == "__main__":
    main()
