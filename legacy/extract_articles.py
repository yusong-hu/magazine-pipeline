"""Extract articles from the New Yorker EPUB into clean markdown files.

Output:
  /Users/yusonghu/Documents/个人电脑控制/new-yorker-import/articles/
    01_<slug>.md
    02_<slug>.md
    ...
Each .md has YAML-style frontmatter (title, author, source) + clean prose.
"""
import re
import sys
from pathlib import Path
from html import unescape

EPUB_DIR = Path("/tmp/epub_extract/unpacked/EPUB")
OUTPUT_DIR = Path("/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/articles")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Table of contents from nav.xhtml
TOC = [
    ("Goings On", "What to Do in New York City This Fall", "d19342ae08aa1b130d18c8999d7a3abb.html"),
    ("Talk of the Town", "Donald Trump Is Still Trying to Make It Harder to Vote", "e9b466648a7a970f3a7a296de40aa64f.html"),
    ("Talk of the Town", "Move Over, Aaron Judge—the Real Yankees M.V.P. Is George Costanza", "c4c440fc8d806878405904aa05575260.html"),
    ("Talk of the Town", "New York's Hottest Club Is . . . the Jacob Riis Bathhouse?", "19ac16a4fa1c2cecc890c9e84a659f8b.html"),
    ("Talk of the Town", "Rachel Bell, Curator of High Art", "1262590585cad3c67ae6046c5d489339.html"),
    ("Talk of the Town", "Where There's Smoke, There’s Fire Towers", "d812c7a860a00aeb03fc5a192fc1caee.html"),
    ("Reporting & Essays", "The Big, Dumb, Gluttonous Fun of America’s Semiquincentennial", "f7172ba4f03553bb1f0a311a17e87d7c.html"),
    ("Reporting & Essays", "The End of the European Summer", "c83cdd1cdf6114107581340ff2cd2287.html"),
    ("Reporting & Essays", "The Children a Scientist Took Home", "2b0cb5df6deea225e4f16cd0f36e7cc8.html"),
    ("Reporting & Essays", "How Far Will the Trump Administration Go to Deport Mahmoud Khalil?", "4021780f6fb10e91954571e56a58fbec.html"),
    ("Shouts & Murmurs", "Admissions Tour: Being a Person", "359ea051bc91743e3d611d8d80151bf5.html"),
    ("Fiction", "Hidden Life", "0055048a086816f51e1b0000003753a3.html"),
    ("Fiction", "A Crossword Odyssey", "c96fb763a13745671c33f074c12b58ff.html"),
    ("The Critics", "Rachel Cusk's Protest Against Personhood", "ec440b646e3631bbe9cca4c6d7064659.html"),
    ("The Critics", "Briefly Noted", "42b9f679aababac4b2bf1b5e494b9b2b.html"),
    ("The Critics", "Anatomy of a Sex Scandal", "21ffd426e4bc29325a2dfdebf8435387.html"),
    ("The Critics", "Your Friendly Neighborhood Hooters", "a1be170e73317c9f00bcaddc787aeb07.html"),
    ("The Critics", "Toons Have Seldom Been Loonier Than in \"Coyote vs. Acme\"", "e373cee7999512d46b618aba43b68ec0.html"),
    ("Poems", "Saint Paul", "80b0d8817b7289d75d04b09c70893504.html"),
    ("Poems", "Lament", "612d992ba526d71f44399b817757990e.html"),
    ("Puzzles", "The Crossword: Wednesday, August 12, 2026", "1e0bb7ac4a22d489b58a9ae6679e3dc5.html"),
]


def clean_html_to_markdown(html: str) -> str:
    """Convert article body HTML to clean markdown."""
    # Remove style/script blocks
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    # Italic
    html = re.sub(r"<em>([^<]+)</em>", r"*\1*", html)
    html = re.sub(r"<i>([^<]+)</i>", r"*\1*", html)
    # Bold
    html = re.sub(r"<strong>([^<]+)</strong>", r"**\1**", html)
    html = re.sub(r"<b>([^<]+)</b>", r"**\1**", html)
    # Drop cap
    html = re.sub(r'<span[^>]*class="[^"]*dropcap[^"]*"[^>]*>([^<])</span>', r"\1", html)
    # Paragraphs
    html = re.sub(r"<p[^>]*>", "\n\n", html)
    html = re.sub(r"</p>", "", html)
    # Line breaks
    html = re.sub(r"<br\s*/?>", "\n", html)
    # Strip remaining tags
    html = re.sub(r"<[^>]+>", "", html)
    # Unescape HTML entities
    html = unescape(html)
    # Normalize whitespace
    html = re.sub(r"[ \t]+", " ", html)
    html = re.sub(r"\n[ \t]+", "\n", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


def extract_article(section: str, title: str, html_filename: str) -> dict:
    """Extract title, author, date, body from one article HTML file."""
    html_path = EPUB_DIR / html_filename
    html = html_path.read_text(encoding="utf-8")

    # Body text (after stripping)
    text = clean_html_to_markdown(html)

    # Find author byline (e.g., "By Amy Davidson Sorkin")
    author = ""
    m = re.search(r"\bBy\s+([A-Z][\w'\.\-]+(?:\s+[A-Z][\w'\.\-]+){0,3})", text)
    if m:
        author = m.group(1).strip()

    # Find date (e.g., "August 16, 2026")
    date = ""
    m = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}", text)
    if m:
        date = m.group(0)

    # Cut body: remove leading metadata (title repeat, "Comment" label, byline, date)
    # Start from the first substantial paragraph
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    body_start = 0
    for i, ln in enumerate(lines):
        if len(ln) > 80 and not ln.startswith(("By ", "Comment")) and "Trump has never" not in ln[:20] and "August" not in ln[:10]:
            body_start = i
            break
    body = "\n\n".join(lines[body_start:])

    # Pull just the byline/date from the front (skip them in body)
    front = []
    for ln in lines[:body_start]:
        if ln.startswith("By ") or re.match(r".*\d{4}\s*$", ln):
            front.append(ln)
        elif ln == "Comment":
            continue
        elif len(ln) < 50:
            front.append(ln)

    return {
        "section": section,
        "title": title,
        "author": author,
        "date": date,
        "body": body,
        "char_count": len(body),
    }


def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s[:60].strip("-")


def main():
    # Process first 3 only
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    print(f"Extracting first {N} articles...")

    results = []
    for i, (section, title, html_file) in enumerate(TOC[:N], 1):
        article = extract_article(section, title, html_file)
        slug = slugify(title)
        out_path = OUTPUT_DIR / f"{i:02d}_{slug}.md"

        # Build markdown
        md_lines = [
            f"# {title}",
            "",
            f"> **栏目**: {section}  ",
        ]
        if article["author"]:
            md_lines.append(f"> **作者**: {article['author']}  ")
        if article["date"]:
            md_lines.append(f"> **日期**: {article['date']}  ")
        md_lines.append(f"> **来源**: The New Yorker, 2026-08-24")
        md_lines.append(f"> **字数**: {article['char_count']}")
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")
        md_lines.append(article["body"])
        md_lines.append("")

        out_path.write_text("\n".join(md_lines), encoding="utf-8")
        print(f"  [{i:02d}] {title}")
        print(f"       author: {article['author']}, date: {article['date']}, "
              f"chars: {article['char_count']}")
        print(f"       -> {out_path}")
        results.append({"path": str(out_path), **article})

    # Summary
    print(f"\nDone. {len(results)} articles written to {OUTPUT_DIR}/")
    total_chars = sum(r["char_count"] for r in results)
    print(f"Total chars: {total_chars} (~{total_chars / 1000:.1f}K words)")


if __name__ == "__main__":
    main()
