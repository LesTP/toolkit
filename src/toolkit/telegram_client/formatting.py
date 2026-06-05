"""Telegram message formatting utilities."""

from __future__ import annotations

TELEGRAM_MESSAGE_LIMIT = 4096
CONTINUATION_PREFIX = "[continued ...]\n\n"

# MarkdownV2 special characters that must be escaped with '\'
_SPECIAL_CHARS = set(r'_*[]()~`>#+-=|{}.!')


def split_message(
    text: str,
    *,
    limit: int = TELEGRAM_MESSAGE_LIMIT,
) -> list[str]:
    """Split text into Telegram-sized chunks.

    Prefers paragraph (``\\n\\n``) boundaries, falls back to line (``\\n``)
    boundaries, then to hard character chunks for single long lines.
    Chunks 2 and later are prefixed with ``CONTINUATION_PREFIX`` so the
    operator can see at a glance that the message continues a prior part.

    The first chunk uses the full ``limit``; subsequent chunks reserve
    ``len(CONTINUATION_PREFIX)`` of their budget for the marker so the
    final wire-text never exceeds ``limit`` per message.

    Returns a single-element list for inputs at or under the limit (no
    marker added).

    Raises:
        TypeError: if ``text`` is not a string.
        ValueError: if ``limit`` is too small to fit the continuation
            prefix plus at least one content character.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if limit <= len(CONTINUATION_PREFIX):
        raise ValueError(
            f"limit must exceed continuation prefix length "
            f"({len(CONTINUATION_PREFIX)})"
        )
    if len(text) <= limit:
        return [text]

    first_chunks = _split_segment(text, limit, "")
    if len(first_chunks) <= 1:
        return first_chunks

    first_chunk = first_chunks[0]
    remainder = text[len(first_chunk):]
    tail_limit = limit - len(CONTINUATION_PREFIX)
    tail_chunks = _split_segment(remainder, tail_limit, "")
    return [first_chunk] + [CONTINUATION_PREFIX + chunk for chunk in tail_chunks]


def _split_segment(text: str, max_chars: int, trailing_sep: str) -> list[str]:
    """Recursively split ``text`` using paragraph → line → char fallback.

    ``trailing_sep`` is appended to the last produced piece so the caller
    can preserve the separator that originally followed this segment in
    the parent text.
    """
    if len(text) + len(trailing_sep) <= max_chars:
        return [text + trailing_sep]

    if "\n\n" in text:
        pieces: list[str] = []
        paragraphs = text.split("\n\n")
        for index, paragraph in enumerate(paragraphs):
            sep = "\n\n" if index < len(paragraphs) - 1 else trailing_sep
            pieces.extend(_split_segment(paragraph, max_chars, sep))
        return _pack_pieces(pieces, max_chars)

    if "\n" in text:
        pieces = []
        lines = text.split("\n")
        for index, line in enumerate(lines):
            sep = "\n" if index < len(lines) - 1 else trailing_sep
            pieces.extend(_split_segment(line, max_chars, sep))
        return _pack_pieces(pieces, max_chars)

    if len(trailing_sep) >= max_chars:
        raise ValueError("max_chars is too small for the requested separator")

    content_limit = max_chars - len(trailing_sep)
    pieces = [text[i:i + content_limit] for i in range(0, len(text), content_limit)]
    pieces[-1] += trailing_sep
    return pieces


def _pack_pieces(pieces: list[str], max_chars: int) -> list[str]:
    """Greedily concatenate adjacent pieces while staying under ``max_chars``."""
    packed: list[str] = []
    current = ""
    for piece in pieces:
        if not piece:
            continue
        if current and len(current) + len(piece) <= max_chars:
            current += piece
            continue
        if current:
            packed.append(current)
        current = piece
    if current:
        packed.append(current)
    return packed


def escape_markdown(text: str) -> str:
    """Escape all MarkdownV2 special characters in text.

    Every character in Telegram's MarkdownV2 special set is prefixed
    with a backslash so it renders as a literal character.
    """
    result = []
    for char in text:
        if char in _SPECIAL_CHARS:
            result.append('\\')
        result.append(char)
    return ''.join(result)


def escape_url(url: str) -> str:
    """Escape characters that would break a MarkdownV2 inline URL.

    Inside (...) only ')' and '\\' are structural and need escaping.
    """
    return url.replace('\\', '\\\\').replace(')', '\\)')


def format_link(text: str, url: str) -> str:
    """Build a MarkdownV2 inline link: [escaped_text](escaped_url).

    Text gets full MarkdownV2 escaping; URL only escapes ')' and '\\'.
    """
    return f"[{escape_markdown(text)}]({escape_url(url)})"
