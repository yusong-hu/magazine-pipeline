"""通用杂志 EPUB 提取器 — 无硬编码目录，自适应《纽约客》/《经济学人》等。

用法:
    python -m extract.extract_epub --epub TheEconomist.2026.08.22.epub \
        --workspace economist-2026-08-22 [--limit N]

流程: 解包 EPUB → 解析 nav.xhtml 目录 → 逐篇解析 HTML（语义化 class）
      → 输出 articles/NN_slug.md（统一 frontmatter 格式）

适配的语义 class:
  标题   te_article_title | ny_article_h1_title | <h1>
  栏目   te_section_title | ny_article_category
  副题   te_article_rubric | ny_article_rubric
  作者   te_article_author | ny_article_author
  日期   te_article_datePublished | ny_article_datePublished
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.contract import get_workspace
from core.markdown_utils import build_article_md

TITLE_CLASSES = {"te_article_title", "ny_article_h1_title"}
SECTION_CLASSES = {"te_section_title", "ny_article_category"}
RUBRIC_CLASSES = {"te_article_rubric", "ny_article_rubric"}
AUTHOR_CLASSES = {"te_article_author", "ny_article_author"}
DATE_CLASSES = {"te_article_datePublished", "ny_article_datePublished"}
FOOTER_CLASSES = {"producer_link", "origin_link", "link_navbar"}
MIN_BODY_CHARS = 200        # 低于此长度视为非正文页（目录页/漫画页等）


@dataclass
class ArticleInfo:
    title: str = ""
    section: str = ""
    rubric: str = ""
    author: str = ""
    date: str = ""
    paragraphs: list = field(default_factory=list)

    @property
    def body(self) -> str:
        parts = []
        if self.rubric:
            parts.append(f"*{self.rubric}*")
        parts.extend(self.paragraphs)
        return "\n\n".join(parts)


class NavParser(HTMLParser):
    """解析 nav.xhtml：栏目(<span>) + 文章链接(<a>)，兼容平铺/嵌套两种结构。"""

    def __init__(self):
        super().__init__()
        self.items: list[tuple[str, str, str]] = []   # (section, title, href)
        self._section = ""
        self._href = None
        self._text = ""
        self._in_a = False
        self._span_text = ""
        self._in_span = False
        self._seen_h2 = False
        self.title = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "h2":
            self._seen_h2 = True
        elif tag == "a" and a.get("href"):
            self._in_a = True
            self._href = a["href"]
            self._text = ""
        elif tag == "span" and not self._in_a:
            self._in_span = True
            self._span_text = ""

    def handle_endtag(self, tag):
        if tag == "a" and self._in_a:
            if self._href and self._text.strip():
                self.items.append((self._section, self._text.strip(), self._href))
            self._in_a = False
        elif tag == "span" and self._in_span:
            text = self._text_of_span()
            if text and not self._seen_h2:      # nav 顶部的 <h2> 是期刊名，跳过
                self._section = text
            self._in_span = False

    def _text_of_span(self):
        return self._span_text.strip()

    def handle_data(self, data):
        if self._in_a:
            self._text += data
        elif self._in_span:
            self._span_text += data
        elif self._seen_h2 and not self.title and data.strip():
            self.title = data.strip()


class ArticleParser(HTMLParser):
    """解析单篇文章 HTML，提取标题/栏目/作者/日期/正文段落。"""

    def __init__(self):
        super().__init__()
        self.info = ArticleInfo()
        self._buf: list[str] = []
        self._capture = None          # 当前捕获目标: title/section/rubric/author/date
        self._in_p = False
        self._p_has_text = False
        self._p_classes: set = set()
        self._skip_p = False

    # ---- 元素捕获 ----
    def handle_starttag(self, tag, attrs):
        cls = set(dict(attrs).get("class", "").split())
        if tag in ("h1", "h3"):
            if cls & TITLE_CLASSES or (tag == "h1" and not self.info.title):
                self._capture = "title"
                self._buf = []
            elif cls & RUBRIC_CLASSES:
                self._capture = "rubric"
                self._buf = []
        elif tag == "span":
            if cls & SECTION_CLASSES:
                self._capture = "section"
                self._buf = []
            elif cls & AUTHOR_CLASSES:
                self._capture = "author"
                self._buf = []
            elif cls & DATE_CLASSES:
                self._capture = "date"
                self._buf = []
        elif tag == "p":
            self._in_p = True
            self._p_has_text = False
            self._buf = []
            self._p_classes = cls
            self._skip_p = bool(cls & FOOTER_CLASSES)

    def handle_endtag(self, tag):
        if tag in ("h1", "h3", "span") and self._capture:
            text = "".join(self._buf).strip()
            if self._capture == "title" and not self.info.title:
                self.info.title = text
            elif self._capture == "rubric" and not self.info.rubric:
                self.info.rubric = text
            elif self._capture == "section" and not self.info.section:
                self.info.section = text
            elif self._capture == "author" and not self.info.author:
                self.info.author = text
            elif self._capture == "date" and not self.info.date:
                self.info.date = text
            self._capture = None
        elif tag == "p" and self._in_p:
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if text and not self._skip_p and self._is_body_paragraph(text):
                self.info.paragraphs.append(text)
            self._in_p = False

    def _is_body_paragraph(self, text: str) -> bool:
        """过滤元信息段落（栏目行/标题重复/日期/水印页脚）。"""
        i = self.info
        if text in (i.title, i.rubric, i.date, i.section):
            return False
        if "This article was downloaded" in text or "zlibrary" in text.lower():
            return False
        # 栏目行形如 "Leaders | Our cover"
        if i.section and text.startswith(i.section) and len(text) < 60:
            return False
        return True

    def handle_data(self, data):
        if self._capture or self._in_p:
            self._buf.append(data)
            if data.strip():
                self._p_has_text = True


def unpack_epub(epub_path: Path) -> Path:
    """解包 EPUB 到临时目录，返回 EPUB 内容根（含 nav.xhtml 的目录）。"""
    tmp = Path(tempfile.mkdtemp(prefix="magpipe_epub_"))
    with zipfile.ZipFile(epub_path) as zf:
        zf.extractall(tmp)
    # nav.xhtml 所在目录即内容根
    for nav in tmp.rglob("nav.xhtml"):
        return nav.parent
    raise FileNotFoundError(f"EPUB 中未找到 nav.xhtml: {epub_path}")


def parse_magazine_meta(content_root: Path, epub_path: Path) -> tuple[str, str]:
    """从 OPF/文件名推断 (杂志名, 期刊日期)。"""
    stem = epub_path.stem
    m = re.match(r"^(.+?)\.(\d{4})\.(\d{2})\.(\d{2})$", stem)
    if m:
        name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", m.group(1))
        return name, f"{m.group(2)}-{m.group(3)}-{m.group(4)}"
    # 兜底: 用 nav 标题
    for nav in content_root.glob("nav.xhtml"):
        t = re.search(r"<title>([^<]+)</title>", nav.read_text(encoding="utf-8"))
        if t:
            return t.group(1), ""
    return stem, ""


def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s[:60].strip("-")


def extract(epub_path: str, workspace_name: str, limit: int = 0) -> list[Path]:
    epub_path = Path(epub_path).expanduser().resolve()
    if not epub_path.exists():
        raise FileNotFoundError(epub_path)

    ws = get_workspace(workspace_name)
    content_root = unpack_epub(epub_path)
    magazine, issue_date = parse_magazine_meta(content_root, epub_path)
    source = f"{magazine}, {issue_date}" if issue_date else magazine
    print(f"杂志: {magazine}  期刊: {issue_date or '未知'}")

    nav_text = (content_root / "nav.xhtml").read_text(encoding="utf-8")
    nav = NavParser()
    nav.feed(nav_text)
    print(f"目录条目: {len(nav.items)}")

    outputs, num = [], 0
    seen_titles = set()
    for _section, nav_title, href in nav.items:
        html_path = content_root / href
        if not html_path.exists():
            continue
        parser = ArticleParser()
        try:
            parser.feed(html_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [skip] 解析失败 {href}: {e}")
            continue

        info = parser.info
        if not info.title:
            info.title = nav_title
        body = info.body
        # 非正文页（栏目索引/漫画/无正文）跳过
        if len(info.paragraphs) < 1 or len(body) < MIN_BODY_CHARS:
            continue
        if info.title in seen_titles:
            continue
        seen_titles.add(info.title)

        num += 1
        if limit and num > limit:
            num -= 1
            break

        meta = {
            "栏目": info.section or _section,
            "作者": info.author,
            "日期": info.date,
            "来源": source,
            "字数": str(len(body)),
        }
        out = ws.articles_dir / f"{num:02d}_{slugify(info.title)}.md"
        out.write_text(build_article_md(info.title, meta, body), encoding="utf-8")
        outputs.append(out)
        print(f"  [{num:02d}] {info.title}  ({info.section}, {len(body)} chars)")

    print(f"\n提取完成: {num} 篇 → {ws.articles_dir}")
    return outputs


def main():
    ap = argparse.ArgumentParser(description="通用杂志 EPUB 提取器")
    ap.add_argument("--epub", required=True, help="EPUB 文件路径")
    ap.add_argument("--workspace", default=None, help="工作区名称")
    ap.add_argument("--limit", type=int, default=0, help="只提取前 N 篇（0=全部）")
    args = ap.parse_args()
    extract(args.epub, args.workspace, args.limit)


if __name__ == "__main__":
    main()
