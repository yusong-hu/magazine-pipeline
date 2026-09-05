"""文本处理公共工具 — 翻译/解读等模块共用。"""
from __future__ import annotations


def split_into_chunks(text: str, max_chars: int) -> list[str]:
    """按段落分块：整段超长再按行硬切，块之间以空行分隔。

    保证任意文本切出的块数最少，且块可按 "\\n\\n" 拼回原文。
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, current = [], ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # 单段超长：按行硬切
            if len(para) > max_chars:
                lines, buf = para.split("\n"), ""
                for line in lines:
                    if len(buf) + len(line) + 1 > max_chars:
                        if buf:
                            chunks.append(buf)
                        # 单行仍超长：按字符硬切
                        while len(line) > max_chars:
                            chunks.append(line[:max_chars])
                            line = line[max_chars:]
                        buf = line
                    else:
                        buf = f"{buf}\n{line}" if buf else line
                current = buf
            else:
                current = para
    if current:
        chunks.append(current)
    return chunks
