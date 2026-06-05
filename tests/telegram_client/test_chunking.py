"""Unit tests for toolkit.telegram_client.split_message — Phase 32.1.

Upgraded 2026-06-04 from a line-only algorithm to paragraph-first with
``[continued ...]`` continuation markers (ported from Diplomat's
``modules/review_gate/chunking.py``, which is being retired in Phase 32.3
in favor of this shared toolkit implementation).
"""
from __future__ import annotations

import pytest

from toolkit.telegram_client import (
    CONTINUATION_PREFIX,
    TELEGRAM_MESSAGE_LIMIT,
    split_message,
)


# ---------------------------------------------------------------------------
# Basic input handling
# ---------------------------------------------------------------------------


def test_short_text_returns_single_chunk_unmarked():
    """Text within the limit must be returned as a single chunk with no
    continuation marker added."""
    chunks = split_message("hello world", limit=100)
    assert chunks == ["hello world"]


def test_text_exactly_at_limit_returns_single_chunk():
    text = "x" * 100
    chunks = split_message(text, limit=100)
    assert chunks == [text]


def test_empty_text_returns_single_empty_chunk():
    chunks = split_message("", limit=100)
    assert chunks == [""]


def test_defaults_to_telegram_message_limit():
    """If ``limit`` is not provided, ``TELEGRAM_MESSAGE_LIMIT`` is used."""
    long_text = "x" * (TELEGRAM_MESSAGE_LIMIT + 1)
    chunks = split_message(long_text)
    assert len(chunks) >= 2
    assert all(len(c) <= TELEGRAM_MESSAGE_LIMIT for c in chunks)


# ---------------------------------------------------------------------------
# Boundary preferences: paragraph → line → char
# ---------------------------------------------------------------------------


def test_paragraph_boundary_preferred_over_line_boundary():
    """When both paragraph and line boundaries are available, the splitter
    should pack along paragraphs first."""
    para_a = "alpha line one\nalpha line two"
    para_b = "beta line one\nbeta line two"
    para_c = "gamma line one\ngamma line two"
    text = "\n\n".join([para_a, para_b, para_c])
    # Pick a limit that fits exactly one paragraph at a time
    limit = max(len(p) for p in (para_a, para_b, para_c)) + 5

    chunks = split_message(text, limit=limit)

    # First chunk should be a whole paragraph (paragraph-first packing),
    # not a partial line from paragraph A merged with paragraph B
    assert chunks[0].startswith("alpha line one")
    assert "alpha line two" in chunks[0]
    # Subsequent chunks should each begin with the continuation marker
    for chunk in chunks[1:]:
        assert chunk.startswith(CONTINUATION_PREFIX)


def test_line_fallback_when_paragraph_alone_exceeds_limit():
    """A single paragraph that exceeds the limit should fall back to splitting
    on line boundaries within that paragraph."""
    # One big paragraph, multiple lines, each line fits but the whole
    # paragraph does not
    lines = [f"line-{i}-{'x' * 30}" for i in range(8)]
    text = "\n".join(lines)
    limit = 100

    chunks = split_message(text, limit=limit)

    assert len(chunks) >= 2
    # Every chunk must respect the limit
    assert all(len(c) <= limit for c in chunks)
    # The first chunk's content (after stripping any prefix) should start
    # with one of the source lines, not mid-line
    first = chunks[0]
    assert first.startswith("line-0")


def test_character_fallback_when_single_line_exceeds_limit():
    """A single line longer than the limit forces hard character chunking."""
    # 250 character single line, no paragraph or line boundaries
    text = "x" * 250
    limit = 100

    chunks = split_message(text, limit=limit)

    # Should yield 3 chunks (100 + 100 + 50-ish, accounting for continuation)
    assert len(chunks) >= 3
    assert all(len(c) <= limit for c in chunks)


# ---------------------------------------------------------------------------
# Continuation markers
# ---------------------------------------------------------------------------


def test_continuation_marker_absent_from_first_chunk():
    text = "line one\nline two\nline three\nline four"
    chunks = split_message(text, limit=20)
    assert not chunks[0].startswith(CONTINUATION_PREFIX)


def test_continuation_marker_present_on_subsequent_chunks():
    text = "line one\nline two\nline three\nline four"
    chunks = split_message(text, limit=20)
    assert len(chunks) >= 2
    for chunk in chunks[1:]:
        assert chunk.startswith(CONTINUATION_PREFIX)


def test_continuation_chunks_respect_limit_with_marker_included():
    """Each continuation chunk must include the marker AND its content
    within ``limit`` chars — the marker eats into the chunk budget, not
    on top of it."""
    text = "x" * 500
    limit = 100

    chunks = split_message(text, limit=limit)

    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= limit


# ---------------------------------------------------------------------------
# Reassembly: content preservation modulo markers
# ---------------------------------------------------------------------------


def test_reassembly_preserves_all_source_characters():
    """Stripping the continuation markers and concatenating must yield the
    original text — chunking never loses or alters source characters."""
    text = (
        "Paragraph one. It has a few sentences.\n\n"
        "Paragraph two.\nWith a line break inside.\n\n"
        "Paragraph three goes here, long enough to matter for the limit.\n\n"
        "Paragraph four is the last."
    )
    chunks = split_message(text, limit=60)

    stripped = [
        chunk[len(CONTINUATION_PREFIX):] if chunk.startswith(CONTINUATION_PREFIX) else chunk
        for chunk in chunks
    ]
    assert "".join(stripped) == text


def test_reassembly_preserves_hard_char_split_content():
    text = "x" * 500
    chunks = split_message(text, limit=100)

    stripped = [
        chunk[len(CONTINUATION_PREFIX):] if chunk.startswith(CONTINUATION_PREFIX) else chunk
        for chunk in chunks
    ]
    assert "".join(stripped) == text


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_rejects_non_string_input():
    with pytest.raises(TypeError):
        split_message(b"bytes are not str", limit=100)
    with pytest.raises(TypeError):
        split_message(None, limit=100)  # type: ignore[arg-type]


def test_rejects_limit_below_one():
    with pytest.raises(ValueError):
        split_message("text", limit=0)
    with pytest.raises(ValueError):
        split_message("text", limit=-1)


def test_rejects_limit_at_or_below_continuation_prefix_length():
    """The continuation prefix must fit inside the limit with room for at
    least one content character; otherwise marker-prefixed chunks would
    have negative content budget."""
    too_small = len(CONTINUATION_PREFIX)
    with pytest.raises(ValueError):
        split_message("x" * 100, limit=too_small)
    with pytest.raises(ValueError):
        split_message("x" * 100, limit=too_small - 1)


# ---------------------------------------------------------------------------
# Constants visible in package API
# ---------------------------------------------------------------------------


def test_continuation_prefix_constant_is_exported():
    assert CONTINUATION_PREFIX == "[continued ...]\n\n"


def test_telegram_message_limit_constant_is_4096():
    assert TELEGRAM_MESSAGE_LIMIT == 4096
