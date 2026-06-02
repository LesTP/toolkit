# Toolkit — AI/LLM Context Reference

> Drop this file into any project's `.llms/` context folder so your AI assistant
> knows what toolkit provides and how to use it.

## What is toolkit?

A local Python package of reusable modules extracted from my projects. Zero
external dependencies for the core; optional extras for provider-specific SDKs.
Installed as an editable package (`pip install -e .` from the toolkit root).

Location: `c:\Users\myeluashvili\claude-code-workspace\projects\toolkit\`

---

## Modules at a glance

| Module | Import | Purpose |
|--------|--------|---------|
| `toolkit.telegram_client` | `from toolkit.telegram_client import ...` | Async Telegram Bot API client — polling, sending, inline keyboards, MarkdownV2 formatting |
| `toolkit.json_rpc` | `from toolkit.json_rpc import ...` | JSON-RPC 2.0 client over stdio — subprocess lifecycle, request/response correlation, notifications |
| `toolkit.llm_client` | `from toolkit.llm_client import ...` | Provider-agnostic LLM client — Anthropic, OpenAI, Gemini with unified interface |
| `toolkit.embedding` | `from toolkit.embedding import ...` | Text → vector embeddings with disk/in-memory cache, batch encoding |
| `toolkit.clustering` | `from toolkit.clustering import ...` | Semantic clustering — HDBSCAN, RAPTOR strategies; UMAP dimensionality reduction |
| `toolkit.cost_accountant` | `from toolkit.cost_accountant import ...` | LLM cost ledger, budget enforcement, pre-call estimation, rate-limit abort |
| `toolkit.prompt_regression` | `from toolkit.prompt_regression import ...` | Prompt regression test framework — scenarios, JSON path checks, LLM judging |
| `toolkit.structured_llm` | `from toolkit.structured_llm import ...` | LLM JSON extraction with schema validation |
| `toolkit.gateway` | `from toolkit.gateway import ...` | Multi-platform message bus — Telegram, log, fake adapters; inbound + outbound; feedback signals |
| `toolkit.source_ingestion` | `from toolkit.source_ingestion import ...` | Content adapter framework — RSS, Telegram channel, Reddit, human-share DM, corpus importers (LiveJournal, Blogspot, plain text, Facebook) |
| `toolkit.feedback_collector` | `from toolkit.feedback_collector import ...` | Normalises platform feedback (reactions/replies/silence) into structured events written to a memory store |

---

## toolkit.telegram_client

Async Telegram Bot API client. No external dependencies (uses `urllib`).

### Key exports

```python
from toolkit.telegram_client import (
    # Client
    TelegramClient,          # async client: polling, send_message, edit_message, send_with_keyboard
    # Data types
    TelegramUpdate,          # frozen dataclass: chat_id, user_id, message_text, command, args, message_id, raw
    SendResult,              # frozen dataclass: success, message_id, error
    InlineButton,            # frozen dataclass: text, callback_data
    InlineKeyboard,          # frozen dataclass: rows of InlineButtons, .to_markup()
    # Formatting
    escape_markdown,         # escape MarkdownV2 special chars
    escape_url,              # escape ) and \ inside inline URLs
    format_link,             # build [text](url) with proper escaping
    split_message,           # split text at line boundaries within TELEGRAM_MESSAGE_LIMIT
    # Transport
    HTTPSTransport,          # default HTTP transport (urllib, no deps)
    TelegramTransport,       # Protocol for custom/mock transports
    # Constants
    TELEGRAM_MESSAGE_LIMIT,  # 4096
    DEFAULT_REQUEST_TIMEOUT_SECONDS,  # 30.0
    # Errors
    TelegramClientError,     # base error
    TelegramAPIError,        # Telegram returned an error response
)
```

### Usage pattern

```python
import asyncio
from toolkit.telegram_client import TelegramClient, escape_markdown, split_message

async def main():
    client = TelegramClient(bot_token="123456:ABC-DEF")

    # Simple send
    await client.send_message(chat_id=42, text="Hello")

    # MarkdownV2
    safe = escape_markdown("Score: 4.5 (out of 5)")
    await client.send_message(chat_id=42, text=safe, parse_mode="MarkdownV2")

    # Long messages — auto-split at 4096 char boundary
    for chunk in split_message(long_text):
        await client.send_message(chat_id=42, text=chunk)

asyncio.run(main())
```

### Polling pattern

```python
async def poll():
    client = TelegramClient(bot_token="123456:ABC-DEF")
    polling = asyncio.create_task(client.start_polling())
    try:
        while True:
            update = await client.get_next_update()
            if update and update.command == "stop":
                break
    finally:
        await client.stop_polling()
        polling.cancel()
```

---

## toolkit.json_rpc

JSON-RPC 2.0 client over stdio. No external dependencies.

### Key exports

```python
from toolkit.json_rpc import (
    # Client
    JsonRpcClient,           # async client: request(), send_notification(), next_notification()
    # Transport
    SubprocessTransport,     # launches child process, wires stdin/stdout
    JsonRpcTransport,        # Protocol: write_line, read_line, close
    encode_json_line,        # serialize dict to compact JSON + newline
    # Errors
    JsonRpcError,            # base error
    JsonRpcTransportError,   # transport (pipe) failed
    JsonRpcTimeoutError,     # no response within timeout
    JsonRpcProtocolError,    # malformed message
    JsonRpcErrorResponse,    # server returned error (has .code, .data)
)
```

### Usage pattern

```python
import asyncio
from toolkit.json_rpc import JsonRpcClient, SubprocessTransport

async def main():
    transport = await SubprocessTransport.spawn("my-server", "--stdio")
    client = JsonRpcClient(transport, request_timeout=30.0)
    await client.start()

    result = await client.request("initialize", {"version": "1.0"})
    await client.send_notification("initialized", {})
    event = await client.next_notification("server/ready")

    await client.stop()

asyncio.run(main())
```

### Callbacks

```python
# Notification routing
client.on_notification(lambda msg: print(msg["method"], msg.get("params")))

# Server-initiated requests
client.on_server_request(lambda msg: {"id": msg["id"], "result": {"status": "ok"}})
```

---

## toolkit.llm_client

Provider-agnostic LLM client. SDKs are optional extras — only loaded when the
provider is used.

### Install extras

```bash
pip install -e ".[anthropic]"   # for AnthropicProvider
pip install -e ".[openai]"      # for OpenAIProvider
pip install -e ".[google]"      # for GeminiProvider
```

### Key exports

```python
from toolkit.llm_client import (
    # Config & response
    LLMConfig,               # dataclass: provider, api_key, models (dict[str, str]),
                              #            max_tokens (4096), temperature (0.7)
                              #   .model property — shorthand for first model value
    LLMResponse,             # dataclass: content (str), model (str), provider (str),
                              #            token_usage ({"input_tokens": int, "output_tokens": int})
    # Providers
    LLMProvider,             # ABC with .call(model, system_prompt, user_prompt, max_tokens) -> LLMResponse
    AnthropicProvider,       # Anthropic Claude (lazy imports anthropic)
    OpenAIProvider,          # OpenAI GPT (lazy imports openai)
    GeminiProvider,          # Google Gemini (lazy imports google-genai)
    # Factory
    create_provider,         # config.provider -> provider instance
                              #   "anthropic" -> AnthropicProvider
                              #   "openai"    -> OpenAIProvider
                              #   "google"    -> GeminiProvider
    # Errors
    LLMAPIError,             # API call failed: .message, .status_code, .retry_after
    LLMResponseError,        # empty/whitespace response: .message
)
```

### Usage pattern

```python
from toolkit.llm_client import LLMConfig, create_provider

config = LLMConfig(
    provider="anthropic",          # or "openai", "google"
    api_key="sk-ant-...",
    models={
        "quality": "claude-sonnet-4-5-20250929",
        "commodity": "claude-haiku-4-5-20251001",
    },
)

provider = create_provider(config)
response = provider.call(
    model=config.models["quality"],      # pick a tier
    system_prompt="You are a technical writer.",
    user_prompt="Summarize this: ...",
    max_tokens=2000,
)

print(response.content)                 # the generated text
print(response.model)                   # actual model used
print(response.provider)                # "anthropic"
print(response.token_usage)             # {"input_tokens": N, "output_tokens": M}
```

### Model tiers

`LLMConfig.models` is a `dict[str, str]` mapping tier names to model IDs.
Tier names are consumer-defined — use whatever makes sense for your project:

```python
# Two-tier (quality + commodity)
models={"quality": "gpt-4o", "commodity": "gpt-4o-mini"}

# Single model
models={"default": "gemini-2.5-pro"}
config.model  # shorthand -> "gemini-2.5-pro"

# Custom tiers
models={"fast": "claude-haiku-4-5-20251001", "smart": "claude-sonnet-4-5-20250929", "vision": "claude-sonnet-4-5-20250929"}
```

### Error handling

```python
from toolkit.llm_client import LLMAPIError, LLMResponseError

try:
    response = provider.call(model, system, user, max_tokens)
except LLMAPIError as e:
    # Rate limit, auth failure, network error
    print(e.message, e.status_code, e.retry_after)
except LLMResponseError as e:
    # Empty or whitespace-only response
    print(e.message)
```

### Switching providers

The interface is identical across providers — only `LLMConfig` changes:

```python
# Swap from Anthropic to OpenAI — zero code changes in calling code
config = LLMConfig(
    provider="openai",
    api_key="sk-...",
    models={"quality": "gpt-4o", "commodity": "gpt-4o-mini"},
)
provider = create_provider(config)
# provider.call(...) works exactly the same
```

---

## Project structure

```
toolkit/
├── pyproject.toml              # zero core deps; optional extras: anthropic, openai, google
└── src/toolkit/
    ├── __init__.py
    ├── telegram_client/
    │   ├── __init__.py         # public re-exports
    │   ├── types.py            # TelegramUpdate, SendResult, InlineButton, InlineKeyboard, errors
    │   ├── transport.py        # HTTPSTransport (urllib), TelegramTransport Protocol
    │   ├── formatting.py       # escape_markdown, escape_url, format_link, split_message
    │   └── client.py           # TelegramClient (polling, send, edit, keyboard)
    ├── json_rpc/
    │   ├── __init__.py         # public re-exports
    │   ├── types.py            # error hierarchy
    │   ├── transport.py        # SubprocessTransport, JsonRpcTransport Protocol
    │   └── client.py           # JsonRpcClient (correlation, routing, lifecycle)
    └── llm_client/
        ├── __init__.py         # public re-exports
        ├── types.py            # LLMConfig, LLMResponse, LLMAPIError, LLMResponseError
        └── providers.py        # LLMProvider ABC, Anthropic/OpenAI/Gemini providers, create_provider
```

## Current consumers

| Project | Modules used |
|---------|-------------|
| **codexbot** | `telegram_client` (polling, messaging), `json_rpc` (Codex subprocess comms) |
| **TGbot** | `telegram_client` (formatting helpers), `llm_client` (LLM provider abstraction) |
