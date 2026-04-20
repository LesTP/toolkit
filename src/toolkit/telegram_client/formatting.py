"""Telegram message formatting utilities."""

from __future__ import annotations

TELEGRAM_MESSAGE_LIMIT = 4096

# MarkdownV2 special characters that must be escaped with '\'
_SPECIAL_CHARS = set(r'_*[]()~`>#+-=|{}.!')


def split_message(
    text: str,
    *,
    limit: int = TELEGRAM_MESSAGE_LIMIT,
) -> list[str]:
    """Split text into Telegram-sized chunks, preferring line boundaries."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < 0:
            split_at = limit
            chunk = remaining[:split_at]
            remaining = remaining[split_at:]
        else:
            chunk = remaining[: split_at + 1]
            remaining = remaining[split_at + 1 :]
        chunks.append(chunk)

    if remaining or not chunks:
        chunks.append(remaining)
    return chunks


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
