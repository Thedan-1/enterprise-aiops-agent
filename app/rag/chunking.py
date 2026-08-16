"""Markdown 感知的 Chunking。

策略：先按 Markdown 标题(#/##/###)切成 section，保留标题作为上下文前缀（防止
"Chunk 之后失去所在小节的语境"这个常见问题）；每个 section 若超过 chunk_size
再按字符数滑动窗口二次切分，用 overlap 保留跨窗口的语境连续性。

这是一个工程参数，不是固定答案——见 eval/run_eval.py 里的 chunk size 对比实验。
"""
import re
from dataclasses import dataclass


@dataclass
class RawChunk:
    content: str
    section_title: str
    chunk_index: int


def _split_by_headers(markdown: str) -> list[tuple[str, str]]:
    """返回 [(标题, 该标题下的正文), ...]，正文不含标题本身。"""
    lines = markdown.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_title = "(无标题)"
    current_lines: list[str] = []
    for line in lines:
        if re.match(r"^#{1,3}\s+", line):
            if current_lines:
                sections.append((current_title, current_lines))
            current_title = re.sub(r"^#{1,3}\s+", "", line).strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_title, current_lines))
    return [(title, "\n".join(lines).strip()) for title, lines in sections if "\n".join(lines).strip()]


def _sliding_window(text: str, chunk_size: int, overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    windows = []
    start = 0
    step = max(chunk_size - overlap, 1)
    while start < len(text):
        windows.append(text[start : start + chunk_size])
        if start + chunk_size >= len(text):
            break
        start += step
    return windows


def chunk_markdown(markdown: str, chunk_size: int = 512, overlap: int = 50) -> list[RawChunk]:
    sections = _split_by_headers(markdown)
    chunks: list[RawChunk] = []
    idx = 0
    for title, body in sections:
        for window in _sliding_window(body, chunk_size, overlap):
            # 标题作为上下文前缀写入chunk内容，保留语境
            content = f"[{title}]\n{window}" if title != "(无标题)" else window
            chunks.append(RawChunk(content=content, section_title=title, chunk_index=idx))
            idx += 1
    return chunks
