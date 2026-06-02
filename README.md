# toolkit

Reusable Python modules extracted from project-specific code. Core has zero external dependencies; optional extras available for provider-specific integrations.

## Install

```bash
pip install -e .

# With Anthropic provider support:
pip install -e ".[anthropic]"

# With OpenAI provider support:
pip install -e ".[openai]"

# With Google Gemini provider support:
pip install -e ".[google]"

# With WebSocket transport support:
pip install -e ".[ws]"
```

---

## Modules

### `toolkit.telegram_client`

Async Telegram Bot API client with long polling, MarkdownV2 formatting, and message splitting.

#### Quick start

```python
import asyncio
from toolkit.telegram_client import TelegramClient, split_message, escape_markdown

async def main():
    client = TelegramClient(bot_token="123456:ABC-DEF")

    # Send a message
    result = await client.send_message(chat_id=42, text="Hello from toolkit")

    # Send with MarkdownV2 formatting
    safe = escape_markdown("Score: 4.5 (out of 5)")
    await client.send_message(chat_id=42, text=safe, parse_mode="MarkdownV2")

    # Split long text at line boundaries (respects Telegram's 4096-char limit)
    for chunk in split_message(long_text):
        await client.send_message(chat_id=42, text=chunk)

asyncio.run(main())
```

#### Polling for updates

```python
async def poll():
    client = TelegramClient(bot_token="123456:ABC-DEF")
    polling = asyncio.create_task(client.start_polling())
    try:
        while True:
            update = await client.get_next_update()
            if update is None:
                continue
            print(f"{update.user_id}: {update.message_text}")
            if update.command == "stop":
                break
    finally:
        await client.stop_polling()
        polling.cancel()
```

#### Inline keyboards

```python
from toolkit.telegram_client import InlineButton, InlineKeyboard

keyboard = InlineKeyboard(rows=(
    (
        InlineButton(text="Approve", callback_data="yes"),
        InlineButton(text="Reject", callback_data="no"),
    ),
))
await client.send_with_keyboard(chat_id, "Confirm?", keyboard)
```

#### Formatting helpers

```python
from toolkit.telegram_client import escape_markdown, escape_url, format_link

escape_markdown("Hello_world!")      # "Hello\_world\!"
escape_url("https://x.com/a(b)")    # "https://x.com/a\(b\)"
format_link("Click here", url)       # "[Click here](https://...)"
```

#### Public API

| Symbol | Kind | Description |
|--------|------|-------------|
| `TelegramClient` | class | Async client with polling, send, edit, keyboard support |
| `TelegramUpdate` | dataclass | Normalized incoming update (chat_id, user_id, command, args, ...) |
| `SendResult` | dataclass | Result of a send operation (success, message_id, error) |
| `InlineButton` | dataclass | Single keyboard button (text + callback_data) |
| `InlineKeyboard` | dataclass | Button grid with `to_markup()` for the API |
| `TelegramClientError` | exception | Base error class |
| `TelegramAPIError` | exception | Telegram returned an error response |
| `HTTPSTransport` | class | Default HTTP transport (urllib, no deps) |
| `TelegramTransport` | Protocol | Transport interface for testing/mocking |
| `split_message()` | function | Split text at line boundaries within a char limit |
| `escape_markdown()` | function | Escape MarkdownV2 special characters |
| `escape_url()` | function | Escape `)` and `\` inside inline URLs |
| `format_link()` | function | Build `[text](url)` with proper escaping |
| `TELEGRAM_MESSAGE_LIMIT` | int | 4096 |
| `DEFAULT_REQUEST_TIMEOUT_SECONDS` | float | 30.0 |

---

### `toolkit.json_rpc`

JSON-RPC 2.0 client over stdio or WebSocket. Manages request–response correlation, notification routing, and transport lifecycle.

#### Quick start

```python
import asyncio
from toolkit.json_rpc import JsonRpcClient, SubprocessTransport

async def main():
    # Launch a subprocess and talk JSON-RPC over its stdin/stdout
    transport = await SubprocessTransport.spawn("my-server", "--stdio")
    client = JsonRpcClient(transport, request_timeout=30.0)
    await client.start()

    # Send a request and await the correlated response
    response = await client.request("initialize", {"version": "1.0"})
    print(response["result"])

    # Send a fire-and-forget notification
    await client.send_notification("initialized", {})

    # Wait for a specific notification from the server
    event = await client.next_notification("server/ready")

    await client.stop()

asyncio.run(main())
```

#### Notification callbacks

```python
# Route all notifications through a callback
def on_notification(message):
    method = message["method"]
    params = message.get("params", {})
    print(f"Notification: {method} -> {params}")

client.on_notification(on_notification)
```

#### Server-initiated requests

```python
# Handle requests the server sends to the client
def handle_server_request(message):
    return {"id": message["id"], "result": {"status": "ok"}}

client.on_server_request(handle_server_request)
```

#### WebSocket transport

```python
from toolkit.json_rpc import JsonRpcClient, WebSocketTransport

async def main():
    # Connect to a JSON-RPC server over WebSocket
    transport = await WebSocketTransport.connect("ws://localhost:4242")
    client = JsonRpcClient(transport, request_timeout=30.0)
    await client.start()

    response = await client.request("initialize", {"version": "1.0"})
    print(response["result"])

    await client.stop()
```

`WebSocketTransport.connect()` retries automatically until the server is reachable or the timeout (default 30s) expires. Requires `pip install toolkit[ws]`.

#### Custom transport

```python
from toolkit.json_rpc import JsonRpcTransport

class MyTransport:
    """Any object matching the JsonRpcTransport protocol."""
    async def write_line(self, line: str) -> None: ...
    async def read_line(self) -> str: ...
    async def close(self) -> None: ...
```

#### Public API

| Symbol | Kind | Description |
|--------|------|-------------|
| `JsonRpcClient` | class | Async client with request correlation and notification routing |
| `SubprocessTransport` | class | Launches a child process, wires stdin/stdout |
| `WebSocketTransport` | class | Connects to a WS server (requires `toolkit[ws]`) |
| `JsonRpcTransport` | Protocol | Transport interface (write_line, read_line, close) |
| `encode_json_line()` | function | Serialize a dict to compact JSON + newline |
| `JsonRpcError` | exception | Base error class |
| `JsonRpcTransportError` | exception | Transport (pipe) failed |
| `JsonRpcTimeoutError` | exception | No response within timeout |
| `JsonRpcProtocolError` | exception | Malformed message |
| `JsonRpcErrorResponse` | exception | Server returned an error (has `.code` and `.data`) |

---

### `toolkit.llm_client`

Provider-agnostic LLM client. Supports model tiers (quality/commodity) and lazy provider loading. Currently implements Anthropic (Claude), OpenAI (GPT), and Google Gemini; additional providers are additive.

#### Quick start

```python
from toolkit.llm_client import LLMConfig, create_provider

config = LLMConfig(
    provider="anthropic",
    api_key="sk-ant-...",
    models={
        "quality": "claude-sonnet-4-5-20250929",
        "commodity": "claude-haiku-4-5-20251001",
    },
)

provider = create_provider(config)
response = provider.call(
    model=config.models["quality"],
    system_prompt="You are a technical writer.",
    user_prompt="Summarize this README: ...",
    max_tokens=2000,
)

print(response.content)
print(f"{response.model} via {response.provider}")
print(f"Tokens: {response.token_usage}")
```

#### Provider selection

```python
from toolkit.llm_client import LLMConfig, create_provider

# Anthropic (Claude) — pip install toolkit[anthropic]
anthropic_config = LLMConfig(
    provider="anthropic",
    api_key="sk-ant-...",
    models={"quality": "claude-sonnet-4-5-20250929", "commodity": "claude-haiku-4-5-20251001"},
)

# OpenAI (GPT) — pip install toolkit[openai]
openai_config = LLMConfig(
    provider="openai",
    api_key="sk-...",
    models={"quality": "gpt-4o", "commodity": "gpt-4o-mini"},
)

# Google Gemini — pip install toolkit[google]
gemini_config = LLMConfig(
    provider="google",
    api_key="AIza...",
    models={"quality": "gemini-2.5-pro", "commodity": "gemini-2.5-flash"},
)

# Same calling convention for any provider
provider = create_provider(openai_config)
response = provider.call(
    model=openai_config.models["quality"],
    system_prompt="You are a helpful assistant.",
    user_prompt="Explain quantum computing in one paragraph.",
    max_tokens=500,
)
print(f"{response.provider}/{response.model}: {response.content[:80]}...")
```

#### Public API

| Symbol | Kind | Description |
|--------|------|-------------|
| `LLMConfig` | dataclass | Provider + credentials + model tier mapping |
| `LLMResponse` | dataclass | Structured response (content, model, provider, token_usage) |
| `LLMProvider` | ABC | Abstract base class for providers |
| `AnthropicProvider` | class | Anthropic (Claude) implementation |
| `OpenAIProvider` | class | OpenAI (GPT) implementation |
| `GeminiProvider` | class | Google Gemini implementation |
| `create_provider()` | function | Factory: config → provider instance |
| `LLMAPIError` | exception | API call failed (rate limit, auth, network) |
| `LLMResponseError` | exception | Empty or unparseable response |

---

### `toolkit.gateway`

Multi-platform message bus for both inbound and outbound communication. Adapter registry with Telegram (backed by `toolkit.telegram_client`), log, and fake adapters. Feedback signal dispatch (reactions, replies, edits).

#### Quick start

```python
from toolkit.gateway import (
    Gateway, GatewayConfig, PlatformConfig,
    InboundMessage, OutboundMessage, FeedbackSignal,
)

def on_message(msg: InboundMessage) -> None:
    print(f"{msg.sender} on {msg.platform}: {msg.content}")

def on_feedback(signal: FeedbackSignal) -> None:
    print(f"{signal.signal_type} on message {signal.message_id}: {signal.value}")

config = GatewayConfig(
    platforms=[
        PlatformConfig(
            name="telegram",
            adapter_type="telegram",
            credentials={"bot_token": "123456:ABC-DEF"},
            params={"chat_id": "42"},
            output_formats=["text", "markdown", "telegraph"],
        ),
        PlatformConfig(
            name="log",
            adapter_type="log",
            credentials={},
            params={"log_path": "logs/outputs.jsonl"},
        ),
    ],
    default_platform="telegram",
    listen=True,
)

gateway = Gateway(config, on_message=on_message, on_feedback=on_feedback)
gateway.send(OutboundMessage(content="Hello", platform="telegram"))
gateway.start_listener()  # spawns a polling thread per platform that supports it
# ...
gateway.stop_listener()
```

#### Public API

| Symbol | Kind | Description |
|--------|------|-------------|
| `Gateway` | class | Public manager: `send`, `send_to_default`, `start_listener`, `stop_listener` |
| `GatewayConfig` | dataclass | List of platforms + default platform + listen flag |
| `PlatformConfig` | dataclass | Per-platform adapter type, credentials, params, output formats |
| `InboundMessage` | dataclass | Normalized inbound (content, platform, message_id, sender, timestamp, reply_to, reactions, raw) |
| `OutboundMessage` | dataclass | Outbound (content, platform, format, reply_to, intent_tag, metadata) |
| `DeliveryResult` | dataclass | Send result (success, platform, message_id, error) |
| `FeedbackSignal` | dataclass | Feedback event (platform, message_id, signal_type, value, sender, timestamp) |
| `GatewayError` | exception | Base error class |
| `PlatformConfigError` | exception | Configuration validation failed |
| `PlatformConnectionError` | exception | Listener could not connect |
| `PlatformNotFoundError` | exception | Target platform missing or disabled |
| `FormatNotSupportedError` | exception | Platform does not support the requested output format |
| `DeliveryError` | exception | Adapter-side delivery failure |

---

### `toolkit.source_ingestion`

Adapter framework that pulls content from external sources and normalizes it into `ContentItem` objects. Supports live sources (RSS, Telegram channel, Reddit, human-share DM) and corpus importers (LiveJournal, Blogspot, plain text, Facebook archive HTML). Durable last-seen markers make polling idempotent across restarts.

#### Quick start

```python
from datetime import timedelta
from toolkit.source_ingestion import (
    SourceIngestion, IngestionConfig, AdapterConfig,
)

config = IngestionConfig(
    adapters=[
        AdapterConfig(
            adapter_type="rss",
            source_label="some_blog",
            poll_interval=timedelta(hours=4),
            params={
                "feed_url": "https://example.com/feed.xml",
                "marker_store_path": "./markers.json",
            },
        ),
        AdapterConfig(
            adapter_type="corpus_text",
            source_label="my_archive",
            params={
                "archive_path": "./seed/",
                "marker_store_path": "./markers.json",
            },
        ),
    ],
)

ingestion = SourceIngestion(config)
for result in ingestion.poll():
    print(f"{result.adapter_label}: {len(result.items)} items, {len(result.errors)} errors")
    for item in result.items:
        print(f"  [{item.timestamp}] {item.title or item.content[:60]}")
```

#### Public API

| Symbol | Kind | Description |
|--------|------|-------------|
| `SourceIngestion` | class | Public manager: `poll(adapter_label=None)`, `poll_once(adapter_label)` |
| `IngestionConfig` | dataclass | List of adapters + fetch timeout + max content length + link extraction toggle |
| `AdapterConfig` | dataclass | Adapter type, source label, poll interval, credentials, params |
| `ContentItem` | dataclass | Normalized content (content, source, timestamp, url, linked_urls, title, author, human_annotation) |
| `IngestionResult` | dataclass | Per-adapter poll result (items, errors, poll_timestamp) |
| `IngestionError` | dataclass | Per-URL fetch error |
| `SourceIngestionError` | exception | Base error class |
| `AdapterConfigError` | exception | Configuration validation failed |
| `AdapterNotFoundError` | exception | Unknown `adapter_type` requested |

Built-in `adapter_type` values: `rss`, `telegram_channel`, `reddit`, `human_share`, `corpus_livejournal`, `corpus_blogspot`, `corpus_text`, `corpus_facebook`, `corpus_twitter`.

---

### `toolkit.feedback_collector`

Normalizes platform feedback signals (reactions, replies, forwards, silence) into structured `FeedbackEvent`s and writes them to a caller-supplied memory store. Includes output tracking, bounded pruning, silence detection, and optional unresolvedness bumps on positive feedback.

#### Quick start

```python
from toolkit.feedback_collector import (
    FeedbackCollector, FeedbackCollectorConfig,
)
from toolkit.gateway import FeedbackSignal

# memory_store must structurally support get_note / store_note / update_note
collector = FeedbackCollector(memory_store=my_memory_store)

# Register an output when you deliver something
collector.register_output(generator_output, delivery_result)

# When a feedback signal arrives via the gateway, normalize it
def on_feedback(signal: FeedbackSignal) -> None:
    event = collector.process_signal(signal)
    if event is not None:
        print(f"recorded: {event.signal_type} on {event.output_intent_tag}")

# Periodically check for silence on old outputs that never got feedback
silenced = collector.check_silence()
```

#### Memory store contract

The injected `memory_store` must structurally support:

- `get_note(note_id)` — returns an object with `.tags`, `.tier`, `.unresolvedness` attributes
- `store_note(note)` — accepts any object with the field shape of `toolkit.feedback_collector.types._NoteInput`
- `update_note(note_id, patch)` — accepts any object with the field shape of `_NotePatch`

The `_NoteInput` / `_NotePatch` shapes are private — they mirror Phosphene's `memory_store.NoteInput` / `NotePatch` field names and types so Phosphene's `MemoryStore` accepts them by duck typing without any wiring change. Other consumers wire any memory store that satisfies the structural contract.

#### Public API

| Symbol | Kind | Description |
|--------|------|-------------|
| `FeedbackCollector` | class | `register_output`, `process_signal`, `check_silence`, `check_delayed_engagement`, `update_unresolvedness_on_feedback` |
| `FeedbackCollectorConfig` | dataclass | Silence window, positive/negative reactions, reply/forward polarity |
| `FeedbackEvent` | dataclass | Normalized feedback (output_message_id, intent_tag, output_mode, signal_type, signal_value, source_note_ids, retention_criteria, timestamp) |
| `OutputRecord` | dataclass | Tracked output (message_id, intent_tag, source_note_ids, retention_criteria, delivered_at, feedback_events, silence_recorded) |

---

## Project structure

```
toolkit/
├── pyproject.toml
└── src/toolkit/
    ├── __init__.py
    ├── llm_client/
    │   ├── __init__.py            Public re-exports
    │   ├── types.py               LLMConfig, LLMResponse, error classes
    │   └── providers.py           LLMProvider ABC, AnthropicProvider, factory
    ├── telegram_client/
    │   ├── __init__.py            Public re-exports
    │   ├── types.py               Data types and errors
    │   ├── transport.py           HTTP transport (Protocol + urllib impl)
    │   ├── formatting.py          MarkdownV2 escaping, message splitting
    │   └── client.py              TelegramClient (polling, send, edit)
    ├── json_rpc/
    │   ├── __init__.py            Public re-exports (lazy-loads WebSocketTransport)
    │   ├── types.py               Error hierarchy
    │   ├── transport.py           Subprocess transport + Protocol
    │   ├── transport_ws.py        WebSocket transport (optional websockets dep)
    │   └── client.py              JsonRpcClient (correlation, routing, lifecycle)
    ├── gateway/
    │   ├── __init__.py            Public re-exports
    │   ├── types.py               GatewayConfig, PlatformConfig, messages, signals
    │   ├── errors.py              Gateway exception hierarchy
    │   ├── adapters.py            Adapter Protocol + Log/Fake/Telegram adapters
    │   └── gateway.py             Gateway manager (send, listener lifecycle)
    ├── source_ingestion/
    │   ├── __init__.py            Public re-exports
    │   ├── types.py               ContentItem, AdapterConfig, IngestionConfig
    │   ├── errors.py              Source Ingestion exception hierarchy
    │   ├── adapters.py            Adapter Protocol + registry + LastSeenMarker
    │   ├── ingestion.py           SourceIngestion manager (poll, poll_once)
    │   ├── normalization.py       URL fetching + content normalization helpers
    │   ├── rss.py                 RSS adapter
    │   ├── telegram_channel.py    Telegram channel adapter
    │   ├── reddit.py              Reddit adapter
    │   ├── human_share.py         Human-share (DM) adapter
    │   └── corpus.py              LiveJournal/Blogspot/Text/Facebook/Twitter importers
    └── feedback_collector/
        ├── __init__.py            Public re-exports
        ├── types.py               FeedbackEvent, OutputRecord, _NoteInput, _NotePatch
        └── collector.py           FeedbackCollector (register, classify, silence)
```

## Consumers

- **codexbot** — uses both `telegram_client` (polling, messaging) and `json_rpc` (Codex app-server communication)
- **TGbot** — uses `telegram_client.formatting` (escape_markdown, escape_url, format_link) and `llm_client` (LLM provider abstraction)
- **Phosphene** — uses `gateway` (Telegram outbound + listener), `source_ingestion` (RSS, Telegram channel, corpus importers), `feedback_collector` (signal normalization wired into its own `MemoryStore` via duck-typed contract), plus `embedding`, `llm_client` (via Anthropic provider)
