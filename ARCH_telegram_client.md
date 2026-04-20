# ARCH: Telegram Client

## Purpose
Full Telegram Bot API client: send messages, receive updates via long polling, edit messages, handle MarkdownV2 formatting, inline keyboards, message splitting, and optional Telegraph publishing for long content overflow. Async-first design with pluggable transport for testing.

**Provenance:** Sending side adapted from TGBot's `src/delivery/telegram_client.py`, `formatting.py`, `telegraph_client.py`. Receiving side adapted from codexbot's `telegram_adapter.py`. Both are tested, deployed code.

## Public API

### TelegramClient

The primary interface. Holds the transport and provides all operations — sending, receiving, and editing.

- **Constructor:** `TelegramClient(bot_token: str, *, transport: TelegramTransport | None = None)`
  - bot_token: str — Telegram Bot API token
  - transport: TelegramTransport | None — injectable transport for testing. Defaults to `HTTPSTransport` with standard settings.

#### Sending

**send_message**
- **Signature:** `async def send_message(self, chat_id: str | int, text: str, *, parse_mode: str = "MarkdownV2", disable_web_preview: bool = False, reply_to: int | None = None) -> SendResult`
- **Parameters:**
  - chat_id: str | int — Telegram chat/channel ID (e.g., `"@channel_name"` or numeric)
  - text: str — message content. Must be non-empty, ≤ 4096 chars after formatting.
  - parse_mode: str — `"MarkdownV2"`, `"HTML"`, or `""` for plain text
  - disable_web_preview: bool — suppress link previews
  - reply_to: int | None — message ID to reply to
- **Returns:** SendResult
- **Errors:** `TelegramAPIError`

**send_with_keyboard**
- **Signature:** `async def send_with_keyboard(self, chat_id: str | int, text: str, keyboard: InlineKeyboard, *, parse_mode: str = "MarkdownV2") -> SendResult`
- **Parameters:** text, chat_id, parse_mode same as `send_message`; keyboard: InlineKeyboard layout
- **Returns:** SendResult
- **Errors:** `TelegramAPIError`

**edit_message**
- **Signature:** `async def edit_message(self, chat_id: int, message_id: int, text: str, *, parse_mode: str = "MarkdownV2") -> None`
- **Parameters:**
  - chat_id: int — chat containing the message
  - message_id: int — ID of the message to edit
  - text: str — new content
- **Returns:** None
- **Errors:** `TelegramAPIError`

#### Receiving

**start_polling**
- **Signature:** `async def start_polling(self, *, initial_offset: int | None = None, poll_timeout: int = 25) -> None`
- Starts a background long-polling loop. Updates are queued internally and consumed via `get_next_update()`. Handles network errors with exponential backoff.
- **Parameters:**
  - initial_offset: int | None — update offset to resume from. None = start fresh.
  - poll_timeout: int — long-poll timeout in seconds (Telegram server holds the connection)
- **Returns:** None (polling runs as a background task)

**stop_polling**
- **Signature:** `async def stop_polling(self) -> None`
- Signals the polling loop to stop and waits for it to finish.

**get_next_update**
- **Signature:** `async def get_next_update(self) -> TelegramUpdate | None`
- Blocks until the next update is available, or returns None if polling has stopped.
- **Returns:** TelegramUpdate | None

**normalize_update**
- **Signature:** `def normalize_update(self, raw: dict[str, Any]) -> TelegramUpdate | None`
- Converts a raw Telegram update dict into a TelegramUpdate. Returns None for unsupported update types (non-message, non-callback). Useful for consumers processing updates from external sources (webhooks, test fixtures).

#### Properties

**next_update_offset**
- **Signature:** `@property def next_update_offset(self) -> int | None`
- The offset to pass on the next `getUpdates` call. Consumers can persist this value to survive restarts.

#### Low-level

**request_api**
- **Signature:** `async def request_api(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]`
- Direct Bot API call. For methods not covered by the high-level API.

### Transport Protocol

```python
class TelegramTransport(Protocol):
    async def request(
        self, bot_token: str, method: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]: ...
```

### HTTPSTransport

Default transport implementation. Uses `urllib` with asyncio for zero external dependencies.

- **Constructor:** `HTTPSTransport(*, timeout: float = 30.0, base_url: str = "https://api.telegram.org")`

### Formatting Functions (sync, pure)

These are standalone functions — no client instance needed.

**escape_markdown**
- **Signature:** `def escape_markdown(text: str) -> str`
- Escapes all MarkdownV2 special characters: `_*[]()~\`>#+-=|{}.!`

**format_link**
- **Signature:** `def format_link(text: str, url: str) -> str`
- Produces a MarkdownV2 link. Text is escaped, URL parentheses are percent-encoded.

**split_message**
- **Signature:** `def split_message(text: str, *, limit: int = 4096) -> list[str]`
- Splits text into chunks that fit Telegram's message length limit. Splits at newline boundaries when possible, falls back to hard splits. Always returns at least one chunk.

### TelegraphClient

For publishing long content that overflows Telegram's 4096-char limit.

- **Constructor:** `TelegraphClient(access_token: str)`

**create_page**
- **Signature:** `async def create_page(self, title: str, content: str, *, author: str = "") -> TelegraphResult`
- Publishes content as a Telegraph article. Content can be plain text or HTML.
- **Returns:** TelegraphResult
- **Errors:** `TelegraphAPIError`

**create_account** (module-level)
- **Signature:** `async def create_account(short_name: str, author_name: str = "") -> str`
- Creates a new Telegraph account. Returns the access token.

## Types

```python
@dataclass(frozen=True)
class TelegramUpdate:
    chat_id: int
    user_id: int
    message_text: str
    command: str | None           # parsed command name without "/", or None
    args: tuple[str, ...]         # parsed command arguments
    message_id: int
    raw: dict[str, Any]           # original update dict for fields not covered above

@dataclass(frozen=True)
class SendResult:
    success: bool
    message_id: int | None        # Telegram message ID if sent
    error: str | None             # error description if failed

@dataclass(frozen=True)
class TelegraphResult:
    success: bool
    url: str | None               # Telegraph article URL if published
    error: str | None

@dataclass(frozen=True)
class InlineButton:
    text: str                     # button label
    callback_data: str | None = None  # callback payload (max 64 bytes)
    url: str | None = None            # URL to open on tap

@dataclass(frozen=True)
class InlineKeyboard:
    rows: list[list[InlineButton]]
```

## Errors

```python
class TelegramClientError(Exception):
    """Base class for all telegram_client errors."""

class TelegramAPIError(TelegramClientError):
    """Telegram API returned an error. Includes status_code and error message."""

class TelegraphAPIError(TelegramClientError):
    """Telegraph API returned an error."""
```

## State

- **Polling offset:** Managed internally during `start_polling`. Exposed via `next_update_offset` property for consumers that want to persist it across restarts. The client does not persist offsets itself — that's the consumer's responsibility.
- **Update queue:** Internal asyncio.Queue populated by the polling loop, drained by `get_next_update()`.
- **No other state.** Each send/edit call is independent.

## Usage Examples

### Simple send (TGBot-style)
```python
from telegram_client import TelegramClient

client = TelegramClient(bot_token="bot123:ABC...")
result = await client.send_message(chat_id="@my_channel", text="Daily digest ready")
```

### Send with keyboard (Phosphene feedback)
```python
from telegram_client import TelegramClient, InlineKeyboard, InlineButton

client = TelegramClient(bot_token="bot123:ABC...")
keyboard = InlineKeyboard(rows=[
    [InlineButton(text="👍", callback_data="like_123"),
     InlineButton(text="💬", callback_data="discuss_123")],
])
result = await client.send_with_keyboard(
    chat_id="@my_channel",
    text="Observation: distributed systems and biological memory share...",
    keyboard=keyboard,
)
```

### Long polling + responding (codexbot-style)
```python
from telegram_client import TelegramClient

client = TelegramClient(bot_token="bot123:ABC...")
await client.start_polling(initial_offset=saved_offset)

while True:
    update = await client.get_next_update()
    if update is None:
        break  # polling stopped

    if update.command == "status":
        await client.send_message(chat_id=update.chat_id, text="All systems nominal")

    # persist for restart recovery
    save_offset(client.next_update_offset)

await client.stop_polling()
```

### Streaming edit (codexbot-style progressive response)
```python
msg = await client.send_message(chat_id=chat_id, text="Thinking...")
accumulated = ""
async for chunk in response_stream:
    accumulated += chunk
    if len(accumulated) > 500:  # batch edits
        await client.edit_message(chat_id=chat_id, message_id=msg.message_id, text=accumulated)
```

### Telegraph overflow
```python
from telegram_client import TelegramClient, TelegraphClient

tg = TelegramClient(bot_token="bot123:ABC...")
tp = TelegraphClient(access_token="tph_token_...")

text = long_essay_text
if len(text) > 3800:
    tp_result = await tp.create_page(title="Weekly Synthesis", content=text)
    excerpt = text[:800] + f"\n\n[Read full essay]({tp_result.url})"
    await tg.send_message(chat_id="@my_channel", text=excerpt)
else:
    await tg.send_message(chat_id="@my_channel", text=text)
```

## Design Notes

### Async-first
All network operations are async. This is a change from the original TGBot-derived ARCH which used sync functions. Rationale: codexbot and Phosphene are both async; TGBot can wrap with `asyncio.run()` for its simple send-and-exit pattern.

### What stays in consumers
- **Allowlist/security checks** — codexbot enforces chat/user allowlists in its Security Layer, not in the telegram client. The toolkit module sends to whatever chat_id it's given.
- **Offset persistence** — the client exposes the offset but doesn't persist it. Codexbot uses its StateStore; other consumers choose their own persistence.
- **Domain-specific formatting** — TGBot's digest layout, Phosphene's observation formatting. The toolkit provides `escape_markdown` and `split_message`; consumers build their own layouts on top.
- **Overflow strategy** — whether and when to use Telegraph is the consumer's decision. The toolkit provides the Telegraph client as a separate tool.

### Transport testability
The `TelegramTransport` Protocol allows injecting a test double that returns canned responses. No mocking frameworks needed — just implement the Protocol.

---

## Change History
| Date | What Changed | Why |
|------|-------------|-----|
| 2026-04-04 | Initial ARCH — send-only, adapted from TGBot delivery module | Phase 1 Discovery |
| 2026-04-20 | Expanded: added receiving (polling), editing, transport abstraction, async-first redesign | Codexbot telegram_adapter proved the receiving pattern; merge both sides into one module |
