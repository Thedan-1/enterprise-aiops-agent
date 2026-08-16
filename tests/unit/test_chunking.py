from app.rag.chunking import chunk_markdown


def test_chunk_markdown_splits_by_header():
    md = "# Title A\ncontent a\n\n## Title B\ncontent b"
    chunks = chunk_markdown(md, chunk_size=512, overlap=50)
    titles = {c.section_title for c in chunks}
    assert "Title A" in titles
    assert "Title B" in titles


def test_chunk_size_enforced_with_sliding_window():
    long_text = "x" * 1000
    md = f"# Section\n{long_text}"
    chunks = chunk_markdown(md, chunk_size=256, overlap=50)
    assert len(chunks) > 1
    for c in chunks:
        # 每个chunk含标题前缀，正文部分不应远超chunk_size
        assert len(c.content) <= 256 + len("[Section]\n") + 5


def test_overlap_creates_shared_content_between_windows():
    long_text = "abcdefghij" * 50  # 500 chars
    md = f"# S\n{long_text}"
    chunks = chunk_markdown(md, chunk_size=200, overlap=50)
    assert len(chunks) >= 2
    # 相邻窗口应有重叠字符（overlap>0时不是简单切断）
    first_tail = chunks[0].content[-30:]
    assert any(first_tail[-10:] in c.content for c in chunks[1:])


def test_empty_input_returns_no_chunks():
    assert chunk_markdown("", chunk_size=512, overlap=50) == []
