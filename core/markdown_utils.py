"""Markdown 工具 — frontmatter 解析、中文文档拆分、md 转纯文本。

英文/中文 md 的统一格式（数据契约）:

    # {标题}

    > **栏目**: xxx
    > **作者**: xxx
    > **日期**: xxx
    > **来源**: xxx

    ---

    {正文}
    （中文文档正文中包含 "## 中文全文翻译" / "## 中文解析" 两个小节）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import config


@dataclass
class ArticleDoc:
    """解析后的文章文档。"""
    title: str = ""
    meta: dict = field(default_factory=dict)   # 栏目/作者/日期/来源/字数
    body: str = ""                             # --- 之后的正文（英文原文）
    translation: str = ""                      # 中文全文翻译小节
    analysis: str = ""                         # 中文解析小节（可能为空）

    @property
    def author(self) -> str:
        return self.meta.get("作者", "")

    @property
    def section(self) -> str:
        return self.meta.get("栏目", "")

    @property
    def date(self) -> str:
        return self.meta.get("日期", "")

    @property
    def source(self) -> str:
        return self.meta.get("来源", "")


def parse_article_doc(md_text: str) -> ArticleDoc:
    """解析英文或中文文章 md，提取标题、meta、正文及中文小节。"""
    doc = ArticleDoc()

    m = re.match(r"^#\s+(.+?)\n", md_text)
    if m:
        doc.title = m.group(1).strip()

    # frontmatter 引用块（> **k**: v）
    fm = re.search(r"^((?:>.*\n)+)\n?---\n", md_text, re.MULTILINE)
    if fm:
        for line in fm.group(1).splitlines():
            line = line.strip().lstrip(">").strip()
            kv = re.match(r"\*\*([^:]+)\*\*:\s*(.+)", line)
            if kv:
                doc.meta[kv.group(1).strip()] = kv.group(2).strip()

    # --- 之后的正文
    sep = re.search(r"^---\s*$", md_text, re.MULTILINE)
    body = md_text[sep.end():].strip() if sep else md_text

    # 中文小节拆分（仅中文文档有）
    m_tr = re.search(r"^##\s+中文全文翻译\s*$", body, re.MULTILINE)
    if m_tr:
        rest = body[m_tr.end():]
        m_an = re.search(r"^##\s+中文解析\s*$", rest, re.MULTILINE)
        if m_an:
            doc.translation = rest[:m_an.start()].strip()
            doc.analysis = rest[m_an.end():].strip()
        else:
            doc.translation = rest.strip()
    else:
        doc.body = body

    return doc


def build_article_md(title: str, meta: dict, body: str) -> str:
    """组装英文文章 md（提取阶段输出格式）。"""
    lines = [f"# {title}", ""]
    for k in ("栏目", "作者", "日期", "来源", "字数"):
        if meta.get(k):
            lines.append(f"> **{k}**: {meta[k]}  ")
    lines += ["", "---", "", body.strip(), ""]
    return "\n".join(lines)


def build_zh_md(title: str, meta: dict, translation: str, analysis: str = "") -> str:
    """组装中文文章 md（翻译阶段输出格式）。"""
    lines = [f"# {title}", ""]
    for k in ("栏目", "作者", "日期", "来源"):
        if meta.get(k):
            lines.append(f"> **{k}**: {meta[k]}  ")
    lines += ["", "---", "", config.ZH_SECTION_TRANSLATION, "", translation.strip()]
    if analysis and analysis.strip():
        lines += ["", config.ZH_SECTION_ANALYSIS, "", analysis.strip()]
    lines.append("")
    return "\n".join(lines)


def markdown_to_plain_text(text: str) -> str:
    """把 markdown 正文转为适合 TTS 朗读的纯文本。"""
    # HTML 注释 / 图片 / HTML 标签
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    # 链接 [text](url) -> text
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # 强调
    text = re.sub(r"(\*\*|__|\*|`)", "", text)
    # 标题/引用/分隔线符号
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-=_]{3,}\s*$", "", text, flags=re.MULTILINE)
    # 列表符号
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    # 空白归一
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
