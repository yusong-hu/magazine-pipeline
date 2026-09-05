"""LLM 中文解读模块 — 用大模型为英文文章生成结构化中文解析。

用法:
    python -m analyze.llm_analysis --num 1 [--workspace xxx]
    python -m analyze.llm_analysis --all

产出: 在中文文章 md 的 "## 中文解析" 小节写入/替换 LLM 生成的解读，
后续 TTS / 导入阶段自动识别该小节（3/6 分区恢复启用）。

接口: core/llm_client 统一客户端（提供商/模型见 config.LLM_PROVIDER，
默认 MiniMax，可切 SiliconFlow），Anthropic 兼容 Messages 协议。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from core.contract import Workspace, get_workspace
from core.llm_client import chat_with_retry, provider_info
from core.markdown_utils import build_zh_md, parse_article_doc

ANALYSIS_PROMPT = """你是一位资深英文杂志精读导师，为中文读者深度解读下面这篇《{source}》文章。

请严格按以下 8 个小节输出 Markdown（小节标题用 ### 三级标题，保留编号）：

### 1. 核心主张（Thesis）
用 2-3 句话概括文章的中心论点。

### 2. 行文结构（Argument Structure）
梳理文章的论证脉络（如：现象引入 → 立论 → 论据展开 → 反方观点 → 结论）。

### 3. 关键论据（Key Evidence）
列出支撑论点的核心事实、数据与事例（3-6 条，每条一句话）。

### 4. 核心概念（Concepts Worth Knowing）
解释文中出现的重要概念、机构、专有名词（3-5 个）。

### 5. 高亮词汇与短语（Vocabulary）
挑出 8-12 个值得学习的英文词汇/短语，给出释义与文中例句（英文原句 + 中文翻译）。

### 6. 修辞与文风（Stylistic Notes）
点评标题、导语或文中精彩的写作手法（如双关、对比、新闻体惯用语）。

### 7. 个人点评（Commentary）
以导师口吻写 3-5 句点评：这篇文章的价值、局限与延伸思考方向。

### 8. 适合精读的句子（5 句）
挑 5 个最值得背诵/仿写的英文原句，逐句给中文翻译并点评亮点。

要求:
- 全部用中文（例句保留英文原文）
- 内容具体、贴合原文，不要泛泛而谈
- 只输出上述 8 个小节的 Markdown，不要额外开场白或结尾

文章信息:
- 标题: {title}
- 栏目: {section}

英文原文:

{body}"""

# 敏感词/内容审核报错特征串（出现任一即判定该篇触雷，跳过并继续）
_SENSITIVE_HINTS = (
    "敏感", "审核", "过滤", "违规", "拒绝",
    "content filter", "content_policy", "moderation",
    "safety", "blocked", "inappropriate", "sensitive",
)


def _is_sensitive_error(exc: Exception) -> bool:
    """按异常文本识别是否为敏感词/内容审核导致的失败。"""
    msg = str(exc).lower()
    return any(h.lower() in msg for h in _SENSITIVE_HINTS)


def analyze_article(ws: Workspace, num: int, force: bool = False) -> Path | None:
    """为一篇文章生成中文解析并写入 zh md。"""
    en_path = ws.en_md(num)
    zh_path = ws.zh_md(num)
    if not en_path or not zh_path.exists():
        print(f"  [{num:02d}] 缺少英文或中文文档，跳过")
        return None

    zh_doc = parse_article_doc(zh_path.read_text(encoding="utf-8"))
    if zh_doc.analysis.strip() and not force:
        print(f"  [{num:02d}] 中文解析已存在，跳过（--force 覆盖）")
        return zh_path

    en_doc = parse_article_doc(en_path.read_text(encoding="utf-8"))
    body = en_doc.body[:config.LLM_MAX_INPUT_CHARS]
    print(f"  [{num:02d}] {en_doc.title}  ({len(body)} chars → {provider_info()})",
          flush=True)

    prompt = ANALYSIS_PROMPT.format(
        source=en_doc.meta.get("来源", "英文杂志"),
        title=en_doc.title,
        section=en_doc.meta.get("栏目", ""),
        body=body,
    )
    try:
        analysis = chat_with_retry(prompt)
    except Exception as exc:
        # 任何调用失败均不中断整批：在文章解析段落写入标记后跳过继续（幂等）
        if _is_sensitive_error(exc):
            note = "（本篇解析被评测系统判为含敏感信息，已跳过，未生成解析）"
        else:
            note = f"（本篇解析调用失败：{type(exc).__name__}，已跳过，未生成解析）"
        print(f"  [{num:02d}] {note}")
        zh_path.write_text(
            build_zh_md(zh_doc.title, zh_doc.meta, zh_doc.translation,
                        f"\n> {note}\n"),
            encoding="utf-8")
        return zh_path
    # 去掉模型可能自带的顶层 "## 中文解析" 重复标题
    analysis = re.sub(r"^##\s*中文解析\s*\n+", "", analysis, flags=re.MULTILINE).strip()

    zh_path.write_text(
        build_zh_md(zh_doc.title, zh_doc.meta, zh_doc.translation, analysis),
        encoding="utf-8")
    print(f"  [{num:02d}] 解析完成 ({len(analysis)} chars) -> {zh_path}")
    return zh_path


def main():
    ap = argparse.ArgumentParser(description="LLM 生成中文解析")
    ap.add_argument("--num", type=int, default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true", help="已有解析也重新生成")
    ap.add_argument("--workspace", default=None)
    args = ap.parse_args()

    ws = get_workspace(args.workspace)
    print(f"解读模型: {provider_info()}")
    nums = ws.all_en_nums() if (args.all or not args.num) else [args.num]
    for num in nums:
        analyze_article(ws, num, force=args.force)


if __name__ == "__main__":
    main()
