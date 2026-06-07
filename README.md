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

    # send_message auto-chunks at 4096 chars (paragraph-first, with
    # `[continued ...]` markers on chunks 2+). Returns the LAST message_id.
    await client.send_message(chat_id=42, text=long_text)

    # For explicit per-chunk control before sending, call split_message yourself:
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
| `split_message()` | function | Paragraph-first split into Telegram-sized chunks with `[continued ...]` markers on chunks 2+ |
| `CONTINUATION_PREFIX` | str | `"[continued ...]\n\n"` — marker prepended to non-first chunks |
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

### `toolkit.cost_accountant`

Cost ledger and budget enforcement that wraps `toolkit.llm_client`. Pre-call estimation, per-call / operation / session budgets, append-only JSONL ledger, rate-limit and spending-cap abort.

#### Quick start

```python
from pathlib import Path
from toolkit.cost_accountant import CostAccountant, CostBudget
from toolkit.llm_client import LLMConfig, Message, ModelTier

accountant = CostAccountant(
    ledger_path=Path("./logs/cost_ledger.jsonl"),
    default_budget=CostBudget(
        operation_name="default",
        operation_budget_usd=25.0,
        session_budget_usd=25.0,
        per_call_max_usd=2.0,
    ),
)

config = LLMConfig(
    provider="anthropic",
    api_key="sk-ant-...",
    models={"quality": "claude-sonnet-4-5-20250929"},
)

response = accountant.complete(
    messages=[Message(role="user", content="Summarize this: ...")],
    config=config,
    tier=ModelTier.QUALITY,
    attribution="my_pipeline",
)
print(f"Spent so far: ${accountant.session_total:.4f}")
```

#### Pre-call estimation

```python
estimate = accountant.estimate_cost(
    model="claude-sonnet-4-5-20250929",
    input_tokens=2500,
    expected_output_tokens=800,
)
print(f"Estimated: ${estimate.total_usd:.4f}")
```

#### Reporting

```python
from datetime import datetime, timedelta

report = accountant.report(since=datetime.now() - timedelta(days=7))
print(report)  # CostReport over last 7 days
```

#### Public API

| Symbol | Kind | Description |
|--------|------|-------------|
| `CostAccountant` | class | Budget-checked completion wrapper around LLM Client |
| `CostBudget` | dataclass | Operation/session/per-call limits and abort flags |
| `CostEstimate` | dataclass | Single-call estimate (input/output cost + total) |
| `BatchEstimate` | dataclass | Batch estimate with per-call breakdown |
| `CallEstimate` | dataclass | One labeled call in a batch estimate |
| `LedgerEntry` | dataclass | One JSONL ledger row (model, tokens, cost, attribution) |
| `CostReport` | dataclass | Aggregated historical ledger report |
| `ModelPricing` | dataclass | `input_per_mtok`, `output_per_mtok` |
| `DEFAULT_PRICING` | dict | Built-in pricing for known Anthropic/OpenAI/Gemini models |
| `normalize_model_name()` | function | Strip date-snapshot suffixes for pricing lookup |
| `CostAccountantError` | exception | Base error class |
| `BudgetExceededError` | exception | Pre-call estimate exceeds a budget |
| `PerCallBudgetError` | exception | Estimate exceeds `per_call_max_usd` |
| `OperationBudgetError` | exception | Operation cumulative spend exceeds budget |
| `SessionBudgetError` | exception | Session cumulative spend exceeds budget |
| `SpendingCapAbortError` | exception | Hard spending cap hit |
| `RateLimitAbortError` | exception | Provider rate-limit response triggered abort |
| `UnknownModelError` | exception | Model not in pricing table and no fallback wanted |

---

### `toolkit.structured_llm`

LLM JSON extraction with schema injection, validation, and bounded retry. Designed to wrap an injected `llm_client` (typically `toolkit.llm_client`); does not import a provider directly.

#### Quick start

```python
import asyncio
from toolkit import llm_client
from toolkit.structured_llm import structured_call, Example

schema = {
    "type": "object",
    "required": ["title", "tags"],
    "properties": {
        "title": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
}

async def main():
    result = await structured_call(
        llm_client=llm_client,
        config={"provider": "anthropic", "api_key": "sk-ant-...",
                "models": {"commodity": "claude-haiku-4-5-20251001"}},
        tier="commodity",
        schema=schema,
        system_prompt="Extract a title and tags from the user's text.",
        user_prompt="A short essay about gardening in early spring...",
        examples=[
            Example(input="A note about coffee.",
                    output={"title": "Coffee", "tags": ["beverage"]}),
        ],
        max_retries=2,
    )
    if result.success:
        print(result.data)            # validated dict
    else:
        print(result.error, result.raw)

asyncio.run(main())
```

#### Low-level primitives

```python
from toolkit.structured_llm import (
    structured_complete, parse_json_response, validate_json_schema,
    load_prompt, load_schema,
)

# Stop at any layer of the pipeline if you want manual control
raw = await structured_complete(llm_client, config, "commodity", messages)
data = parse_json_response(raw)
validate_json_schema(data, schema, label="my_extractor")
```

#### Public API

| Symbol | Kind | Description |
|--------|------|-------------|
| `Example` | dataclass | Few-shot example pair (`input`, `output`) |
| `StructuredResult` | dataclass | `success`, `data`, `raw`, `retries`, `error` |
| `structured_call()` | async function | Full pipeline: prompt assembly + schema + examples + retry |
| `structured_complete()` | async function | Raw LLM call with messages (no parsing) |
| `parse_json_response()` | function | Extract a JSON object from a model response string |
| `validate_json_schema()` | function | Validate a parsed dict against a JSON Schema |
| `load_prompt()` | function | Read a prompt template from a file |
| `load_schema()` | function | Read a JSON Schema from a file |

---

### `toolkit.prompt_regression`

Scenario-based prompt regression test framework. Loads scenarios from JSON files, dispatches each to a consumer-provided async module callback, then evaluates the response via JSON path checks and/or LLM-as-judge.

#### Quick start

```python
import asyncio
from toolkit import llm_client
from toolkit.prompt_regression import ScenarioRunner

async def call_my_module(module_name: str, payload, context: dict):
    # Consumer dispatches to whatever module the scenario names
    if module_name == "extractor":
        return await my_extractor(payload, **context)
    raise ValueError(module_name)

async def main():
    runner = ScenarioRunner(
        llm_client=llm_client,
        llm_config={"provider": "anthropic", "api_key": "sk-ant-...",
                    "models": {"commodity": "claude-haiku-4-5-20251001"}},
        module_caller=call_my_module,
    )
    report = await runner.run_all("./scenarios/", module_filter="extractor")
    print(f"{report.passed}/{report.total} scenarios passed")
    for r in report.results:
        if not r.passed:
            print(f"  FAIL {r.scenario_id}")
            for p in r.properties:
                if not p.passed:
                    print(f"    - {p.description}")

asyncio.run(main())
```

#### Scenario shape

Scenarios are plain JSON files. Each declares a module to call, an input payload, and a list of property checks (any mix of `json_path_exists`, `json_path_equals`, `llm_judge`).

```json
{
  "scenario_id": "extract-tags-from-essay",
  "description": "Extractor returns at least one tag for a short essay",
  "module": "extractor",
  "input": "A short essay about gardening...",
  "properties": [
    {"type": "json_path_exists", "description": "has tags", "path": "$.tags"},
    {"type": "llm_judge", "description": "tags are relevant",
     "criteria": "Tags should describe the essay's subject.",
     "pass_instruction": "Return PASS if any tag relates to gardening.",
     "fail_instruction": "Return FAIL if all tags are unrelated."}
  ]
}
```

#### Public API

| Symbol | Kind | Description |
|--------|------|-------------|
| `ScenarioRunner` | class | Loads scenarios, dispatches to consumer module, evaluates properties |
| `LLMJudge` | class | LLM-backed verdict on a response against criteria |
| `JudgeResult` | dataclass | `verdict` ("PASS"/"FAIL"), `explanation`, `criteria` |
| `PropertyCheck` | dataclass | A single check (type + path/value/criteria) |
| `PropertyResult` | dataclass | Outcome of one check (passed, expected, actual) |
| `ScenarioResult` | dataclass | Aggregated property results for one scenario |
| `RunReport` | dataclass | Full run: `results`, `total`, `passed` |
| `ModuleCaller` | Protocol | `async (module_name, payload, context) -> Any` |
| `PROPERTY_TYPES` | tuple | Allowed values for `PropertyCheck.type` |
| `load_scenario()` | function | Load one scenario JSON file |
| `load_scenarios()` | function | Load all scenarios in a directory |
| `json_path_exists()` | function | True if a JSONPath resolves in `data` |
| `json_path_get()` | function | Resolve a JSONPath against `data` |

---

### `toolkit.embedding`

Text → vector embeddings with disk/in-memory caching. Currently uses `sentence-transformers` (e.g. `all-MiniLM-L6-v2`).

> Requires `pip install sentence-transformers numpy` (not declared as toolkit extras yet — install alongside).

#### Quick start

```python
from toolkit.embedding import embed, EmbeddingConfig, similarity, batch_similarity

config = EmbeddingConfig(
    model="all-MiniLM-L6-v2",
    batch_size=256,
    cache_dir="./cache/embeddings",
    device="cpu",
)

texts = ["A cat sleeps on the couch.", "Felines napping on furniture.",
         "Quarterly revenue grew 12%."]
result = embed(texts, config)

print(result.vectors.shape)       # (3, 384)
print(f"cache hits: {result.from_cache} / computed: {result.computed}")

# Pairwise similarity
print(similarity(result.vectors[0], result.vectors[1]))   # ~0.7

# Rank candidates against a query vector
scores = batch_similarity(result.vectors[0], result.vectors[1:])
```

#### Public API

| Symbol | Kind | Description |
|--------|------|-------------|
| `embed()` | function | Encode a list of texts → `EmbeddingResult` |
| `similarity()` | function | Cosine similarity between two vectors |
| `batch_similarity()` | function | Rank candidates by similarity to a query vector |
| `EmbeddingConfig` | dataclass | `model`, `batch_size`, `cache_dir`, `device` |
| `EmbeddingResult` | dataclass | `vectors` (ndarray), `model`, `dimension`, `from_cache`, `computed` |
| `EmbeddingModelError` | exception | Model not found or failed to load |
| `EmbeddingInputError` | exception | Input validation failed (empty / non-string) |

---

### `toolkit.clustering`

Semantic clustering over embeddings. Supports HDBSCAN (flat) and RAPTOR (recursive tree-of-summaries) strategies, with optional UMAP dimensionality reduction.

> Requires `pip install numpy hdbscan` (and `umap-learn` if you set `reduce_dims`). Lazy-imported inside `cluster()`.

#### Quick start

```python
import numpy as np
from toolkit.clustering import cluster, ClusterConfig, ClusterStrategy

vectors = np.random.rand(200, 384).astype(np.float32)  # 200 items, 384-dim
config = ClusterConfig(
    strategy=ClusterStrategy.HDBSCAN,
    min_cluster_size=5,
    min_samples=3,
    metric="euclidean",
    reduce_dims=50,   # UMAP down to 50d before clustering
)

result = cluster(vectors, config)
print(f"{result.n_clusters} clusters, {result.n_noise} noise items")
print(result.labels[:10])    # per-item cluster id (-1 = noise)
```

#### RAPTOR (recursive tree-of-summaries)

```python
from toolkit.clustering import cluster, ClusterConfig, ClusterStrategy

config = ClusterConfig(
    strategy=ClusterStrategy.RAPTOR,
    min_cluster_size=5,
    raptor_max_depth=3,
    raptor_summarizer=my_summarizer,   # Callable[[list[str]], str]
    raptor_embedder=my_embedder,       # Callable[[list[str]], np.ndarray]
)
result = cluster(vectors, config, texts=my_texts)
for layer in result.tree:
    print(f"depth={layer.depth}  clusters={len(layer.cluster_ids)}")
    if layer.summaries:
        for cid, summary in layer.summaries.items():
            print(f"  [{cid}] {summary[:80]}")
```

#### Public API

| Symbol | Kind | Description |
|--------|------|-------------|
| `cluster()` | function | Embeddings → `ClusterResult` (labels + optional tree) |
| `ClusterConfig` | dataclass | Strategy, sizing, metric, UMAP reduction, RAPTOR knobs |
| `ClusterResult` | dataclass | `labels`, `n_clusters`, `n_noise`, `strategy`, optional `tree` |
| `ClusterStrategy` | Enum | `HDBSCAN`, `RAPTOR` |
| `ClusterLayer` | dataclass | One RAPTOR tree level (`depth`, `cluster_ids`, `summaries`) |
| `ClusterInputError` | exception | Input validation failed |
| `ClusterStrategyError` | exception | Unsupported or misconfigured strategy |

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

### `toolkit.coaching`

Tag-based operator-input parser. Parses `TAG: content` notes into `CoachingEvent` (routed to a consumer with a canonical type) and `/command args` into typed `Command` objects. Tag vocabulary and command list are loaded from a YAML config. Core stays dependency-free — PyYAML is lazy-imported only inside `load_routes_config`.

#### Quick start

```python
from toolkit.coaching import TaggedCoachingParser, CoachingEvent, Command

# Load from YAML config (requires pyyaml)
parser = TaggedCoachingParser("config/coaching_routes.yaml")

# Or pass a config dict directly (no yaml dep needed)
parser = TaggedCoachingParser.from_config({
    "tags": {
        "default": {"route": "coaching_queue", "coaching_type": "FREE"},
        "INTEL":   {"route": "state_updater",  "coaching_type": "INTEL"},
    },
    "commands": ["/preview", "/edit"],
})

# Parse and dispatch
match parser.parse(operator_input):
    case Command(name=name, args=args):
        handle_command(name, args)
    case CoachingEvent(route="state_updater", content=text):
        update_state_from_intel(text)
    case CoachingEvent(route="coaching_queue", coaching_type=tag, content=text):
        queue_for_next_response(tag, text)
```

#### Config format

```yaml
tags:
  PRIORITY:
    route: coaching_queue
    coaching_type: PRIORITY
  INTEL:
    route: state_updater
    coaching_type: INTEL
  default:                # required — handles untagged / unknown-tag input
    route: coaching_queue
    coaching_type: FREE
commands:
  - /preview
  - /approve
  - /edit
  - /block
```

#### Public API

| Symbol | Kind | Description |
|--------|------|-------------|
| `TaggedCoachingParser` | class | `__init__(routes_path)` (YAML), `from_config(dict)` (no dep), `parse(text)` |
| `CoachingEvent` | dataclass | `coaching_type`, `content`, `route` — routed coaching note |
| `Command` | dataclass | `name`, `args` — parsed slash command |
| `RouteRule` | dataclass | `coaching_type`, `route` — one config entry |
| `load_routes_config` | function | YAML file → dict (lazy-imports `yaml`) |

Notes:

- Tag matching is case-insensitive.
- Untagged, unknown-tag, and malformed-tag input all fall through to the `default` route.
- Unknown slash commands return `CoachingEvent` (default route) so they're not silently dropped.
- `/edit` is special-cased: trailing text becomes `args["text"]`. Other commands return `args={}`.

---

### `toolkit.edit_classifier`

LLM-as-judge categorical classifier for review-gate edit logs. Takes `(original_draft, edited_draft, edit_notes)` and returns a typed `EditClassification` with category (one of six fixed values), confidence in `[0, 1]`, one-line rationale, the classifier model name, and a tz-aware `classified_at`. Intended for a coached-review feedback loop: operator edits a draft → classifier categorises → consumer surfaces recurring patterns → underlying prompt gets tightened.

The classifier is config-agnostic. Each consumer writes its own `build_*` factory that translates its own config-file shape into the constructor kwargs.

#### Quick start

```python
from pathlib import Path

from toolkit.edit_classifier import LLMEditClassifier, EditClassification


classifier = LLMEditClassifier(
    llm_client=my_llm_client,                  # any object with .complete(**kwargs)
    llm_config={
        "provider": "openai",
        "models": {"commodity": "gpt-4.1-mini"},
        "api_key": "...",
    },
    tier="commodity",
    prompt_path=Path("config/prompts/edit_classifier.txt"),
    attribution="alpha",                        # optional, threaded into cost ledger
)

result: EditClassification = await classifier.classify(
    original="We will crush your proposal.",
    edited="We can push back on your proposal.",
    edit_notes="Soften tone.",
)
# result.category    -> "tone_softer"
# result.confidence  -> 0.9 (validated in [0,1])
# result.rationale   -> "The edit removes confrontational phrasing." (model-generated)
# result.classifier_model -> "gpt-4.1-mini"
# result.classified_at    -> datetime.now(timezone.utc)
```

#### Categories

The six categories are hardcoded for the v1 surface. Both Diplomat and Clanker Courts use the same set:

| Category | Meaning |
|---|---|
| `tone_softer` | Original was more confrontational than the edit |
| `tone_harder` | Original was softer than the edit |
| `commitment_removed` | Edit removes a concrete promise or agreement |
| `ambiguity_added` | Edit introduces hedging not in the original |
| `constraint_enforcement` | Edit removes content that violated a rule or constraint |
| `persona_correction` | Edit brings the response back in character |

#### Public API

| Symbol | Kind | Description |
|--------|------|-------------|
| `LLMEditClassifier` | class | `__init__(llm_client, llm_config, tier, prompt_path, attribution=None)`, `async classify(original, edited, edit_notes)` |
| `EditClassification` | dataclass | `category`, `confidence`, `rationale`, `classifier_model`, `classified_at` (tz-aware UTC) |
| `EDIT_CLASSIFICATION_CATEGORIES` | tuple | The six category strings |
| `EDIT_CLASSIFICATION_SCHEMA` | dict | JSON schema enforced by `structured_call` |

Notes:

- The prompt file is read at construction time; pass a path your project owns.
- Blank `original` or `edited` raise `ValueError`. Out-of-enum category, out-of-range confidence, or blank rationale raise `ValueError` as a defensive second check after the schema-validated structured call.
- Each consumer typically wraps the constructor in a project-side `build_edit_classifier(...)` factory that knows its own config shape (e.g. Diplomat's `pipeline.yaml` `{"primary": {...}}` convention). Mirror the `build_reconciler` pattern in Diplomat's `modules/reconciliation` for the wrapper shape.

---

## Project structure

```
toolkit/
├── pyproject.toml
└── src/toolkit/
    ├── __init__.py
    ├── embedding/
    │   ├── __init__.py            Public re-exports
    │   ├── types.py               EmbeddingConfig, EmbeddingResult, error classes
    │   └── core.py                embed, similarity, batch_similarity
    ├── clustering/
    │   ├── __init__.py            Public re-exports
    │   ├── types.py               ClusterConfig, ClusterResult, ClusterStrategy, error classes
    │   └── core.py                cluster() (lazy imports hdbscan / umap)
    ├── llm_client/
    │   ├── __init__.py            Public re-exports
    │   ├── types.py               LLMConfig, LLMResponse, error classes
    │   └── providers.py           LLMProvider ABC, Anthropic/OpenAI/Gemini/OpenRouter, factory
    ├── cost_accountant/           [depends on llm_client]
    │   ├── __init__.py            Public re-exports
    │   ├── types.py               CostBudget, CostEstimate, LedgerEntry, ModelPricing, DEFAULT_PRICING
    │   ├── errors.py              Cost Accountant exception hierarchy
    │   └── core.py                CostAccountant (estimate, complete, report)
    ├── structured_llm/
    │   ├── __init__.py            Public re-exports
    │   └── core.py                structured_call + low-level primitives
    ├── prompt_regression/
    │   ├── __init__.py            Public re-exports
    │   ├── types.py               PropertyCheck, PropertyResult, ScenarioResult, RunReport
    │   ├── judge.py               LLMJudge
    │   └── runner.py              ScenarioRunner, ModuleCaller Protocol
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
    ├── gateway/                   [optionally depends on telegram_client at runtime]
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
    ├── coaching/
    │   ├── __init__.py            Public re-exports
    │   └── core.py                CoachingEvent, Command, RouteRule, TaggedCoachingParser, load_routes_config (yaml lazy-imported)
    └── edit_classifier/
        ├── __init__.py            Public re-exports
        ├── types.py               EditClassification
        └── classifier.py          LLMEditClassifier, EDIT_CLASSIFICATION_CATEGORIES, EDIT_CLASSIFICATION_SCHEMA
```

## Consumers

- **Diplomat** — `llm_client`, `cost_accountant`, `structured_llm`, `prompt_regression`, `telegram_client`, `coaching`
- **Phosphene** — `embedding`, `clustering`, `llm_client`, `cost_accountant`, `gateway` (Telegram outbound + listener), `source_ingestion` (RSS, Telegram channel, corpus importers), `feedback_collector` (signal normalization wired into its own `MemoryStore` via duck-typed contract)
- **Year-in-Search** — `embedding`, `clustering`, `llm_client`
- **codexbot** — `telegram_client` (polling, messaging), `json_rpc` (Codex app-server communication)
- **TGbot** — `telegram_client.formatting` (escape_markdown, escape_url, format_link), `llm_client` (LLM provider abstraction)
