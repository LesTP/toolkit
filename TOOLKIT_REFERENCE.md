# Toolkit — AI/LLM Context Reference

> Drop this file into any project's `.llms/` context folder so your AI assistant
> knows what toolkit provides and how to use it.

## What is toolkit?

A local Python package of reusable modules. Leaf modules have no toolkit
dependencies; two composing modules wrap exactly one leaf module each
(`cost_accountant → llm_client`, `gateway → telegram_client`). Heavy SDKs
are optional extras; numpy / sentence-transformers / hdbscan are required
only by the modules that use them.

Installed as an editable package (`pip install -e .` from the toolkit root).

Location: `p:\shared\toolkit\`

---

## Modules at a glance

| Module | Import | Purpose |
|--------|--------|---------|
| `toolkit.telegram_client` | `from toolkit.telegram_client import ...` | Async Telegram Bot API client — polling, sending, inline keyboards, MarkdownV2 formatting |
| `toolkit.json_rpc` | `from toolkit.json_rpc import ...` | JSON-RPC 2.0 client over stdio — subprocess lifecycle, request/response correlation, notifications |
| `toolkit.llm_client` | `from toolkit.llm_client import ...` | Provider-agnostic LLM client — Anthropic, OpenAI, Gemini, OpenRouter with unified interface |
| `toolkit.embedding` | `from toolkit.embedding import ...` | Text → vector embeddings with disk/in-memory cache, batch encoding |
| `toolkit.clustering` | `from toolkit.clustering import ...` | Semantic clustering — HDBSCAN, RAPTOR strategies; UMAP dimensionality reduction |
| `toolkit.cost_accountant` | `from toolkit.cost_accountant import ...` | LLM cost ledger, budget enforcement, pre-call estimation, rate-limit abort |
| `toolkit.prompt_regression` | `from toolkit.prompt_regression import ...` | Prompt regression test framework — scenarios, JSON path checks, LLM judging |
| `toolkit.structured_llm` | `from toolkit.structured_llm import ...` | LLM JSON extraction with schema validation |
| `toolkit.gateway` | `from toolkit.gateway import ...` | Multi-platform message bus — Telegram, log, fake adapters; inbound + outbound; feedback signals |
| `toolkit.source_ingestion` | `from toolkit.source_ingestion import ...` | Content adapter framework — RSS, Telegram channel, Reddit, human-share DM, corpus importers (LiveJournal, Blogspot, plain text, Facebook) |
| `toolkit.feedback_collector` | `from toolkit.feedback_collector import ...` | Normalises platform feedback (reactions/replies/silence) into structured events written to a memory store |
| `toolkit.coaching` | `from toolkit.coaching import ...` | Tag-based operator-input parser — `TAG: content` notes routed to consumers, `/command args` parsed to typed `Command`s, YAML-driven config |

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
    split_message,           # paragraph-first split into TELEGRAM_MESSAGE_LIMIT chunks; auto-invoked by send_message
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
    # send_message auto-chunks at 4096; for explicit per-chunk control:
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

## toolkit.embedding

Text → vector embeddings with caching. Currently uses `sentence-transformers`.

> Requires `pip install sentence-transformers numpy` (not declared as toolkit extras yet).

### Key exports

```python
from toolkit.embedding import (
    embed,                    # (texts: list[str], config: EmbeddingConfig) -> EmbeddingResult
    similarity,               # (a: ndarray, b: ndarray) -> float  cosine
    batch_similarity,         # (query: ndarray, candidates: ndarray) -> ndarray
    EmbeddingConfig,          # dataclass: model="all-MiniLM-L6-v2", batch_size=256,
                               #            cache_dir=None, device="cpu"
    EmbeddingResult,          # dataclass: vectors (ndarray (n, dim)), model, dimension,
                               #            from_cache, computed
    EmbeddingModelError,      # model not found / failed to load
    EmbeddingInputError,      # input validation failed (empty / non-string)
)
```

### Usage pattern

```python
from toolkit.embedding import embed, EmbeddingConfig, batch_similarity

config = EmbeddingConfig(model="all-MiniLM-L6-v2",
                         cache_dir="./cache/embeddings")
result = embed(["cat on couch", "felines on furniture", "Q3 revenue"], config)
print(result.vectors.shape)        # (3, 384)
print(result.from_cache, result.computed)
scores = batch_similarity(result.vectors[0], result.vectors[1:])
```

---

## toolkit.clustering

Semantic clustering over embeddings. HDBSCAN (flat) and RAPTOR (recursive
tree-of-summaries) strategies with optional UMAP dimensionality reduction.

> Requires `pip install numpy hdbscan` (plus `umap-learn` if `reduce_dims` is
> set). hdbscan/umap are lazy-imported inside `cluster()`.

### Key exports

```python
from toolkit.clustering import (
    cluster,                  # (embeddings, config, texts=None) -> ClusterResult
    ClusterConfig,            # dataclass: strategy, min_cluster_size=5, min_samples=3,
                               #            metric="euclidean", reduce_dims=None,
                               #            raptor_max_depth=3, raptor_summarizer=None,
                               #            raptor_embedder=None
    ClusterResult,            # dataclass: labels (ndarray (n,)), n_clusters, n_noise,
                               #            strategy, tree (RAPTOR only)
    ClusterStrategy,          # Enum: HDBSCAN, RAPTOR
    ClusterLayer,             # dataclass: depth, cluster_ids, member_counts, summaries
    ClusterInputError,
    ClusterStrategyError,
)
```

### Usage pattern

```python
from toolkit.clustering import cluster, ClusterConfig, ClusterStrategy

# Flat HDBSCAN
result = cluster(
    embeddings,
    ClusterConfig(strategy=ClusterStrategy.HDBSCAN,
                  min_cluster_size=5, reduce_dims=50),
)
print(f"{result.n_clusters} clusters, {result.n_noise} noise")

# RAPTOR — recursive summarized tree
tree_result = cluster(
    embeddings,
    ClusterConfig(strategy=ClusterStrategy.RAPTOR,
                  raptor_max_depth=3,
                  raptor_summarizer=my_summarizer,
                  raptor_embedder=my_embedder),
    texts=my_texts,
)
for layer in tree_result.tree:
    print(layer.depth, len(layer.cluster_ids))
```

---

## toolkit.gateway

Multi-platform message bus for inbound and outbound communication. Adapter
registry with Telegram (backed by `toolkit.telegram_client`), log, and fake
adapters. Inbound + feedback signal dispatch via callbacks.

### Key exports

```python
from toolkit.gateway import (
    Gateway,                  # manager: send, send_to_default, start_listener, stop_listener
    GatewayConfig,            # dataclass: platforms (list), default_platform, listen=True
    PlatformConfig,           # dataclass: name, adapter_type ("telegram"|"log"|"fake"),
                               #            credentials, params, enabled=True,
                               #            output_formats=["text"]
    InboundMessage,           # dataclass: content, platform, message_id, sender,
                               #            timestamp, reply_to, reactions, raw
    OutboundMessage,          # dataclass: content, platform, format="text", reply_to,
                               #            intent_tag, metadata
    DeliveryResult,           # dataclass: success, platform, message_id, error
    FeedbackSignal,           # dataclass: platform, message_id, signal_type
                               #            ("reaction"|"reply"|"edit"|adapter-specific),
                               #            value, sender, timestamp
    # Errors
    GatewayError,
    PlatformConfigError,
    PlatformConnectionError,
    PlatformNotFoundError,
    FormatNotSupportedError,
    DeliveryError,
)
```

### Usage pattern

```python
from toolkit.gateway import (
    Gateway, GatewayConfig, PlatformConfig,
    InboundMessage, OutboundMessage, FeedbackSignal,
)

def on_message(msg: InboundMessage) -> None:
    print(f"{msg.sender} on {msg.platform}: {msg.content}")

def on_feedback(signal: FeedbackSignal) -> None:
    print(f"{signal.signal_type} on {signal.message_id}: {signal.value}")

config = GatewayConfig(
    platforms=[
        PlatformConfig(name="telegram", adapter_type="telegram",
                       credentials={"bot_token": "123456:ABC-DEF"},
                       params={"chat_id": "42"},
                       output_formats=["text", "markdown", "telegraph"]),
        PlatformConfig(name="log", adapter_type="log", credentials={},
                       params={"log_path": "logs/outputs.jsonl"}),
    ],
    default_platform="telegram",
    listen=True,
)

gateway = Gateway(config, on_message=on_message, on_feedback=on_feedback)
gateway.send(OutboundMessage(content="Hello", platform="telegram"))
gateway.start_listener()
# ...
gateway.stop_listener()
```

### Notes

- Telegram adapter optionally imports `toolkit.telegram_client` at runtime — the
  second documented toolkit cross-module exception (alongside
  `cost_accountant → llm_client`). Log/fake adapters work without it.
- Adapter errors surface as `DeliveryResult.success=False` rather than
  exceptions out of `send()`.

---

## toolkit.source_ingestion

Adapter framework that pulls content from external sources and normalizes it
into `ContentItem` objects. Durable last-seen markers make polling idempotent
across restarts.

### Key exports

```python
from toolkit.source_ingestion import (
    SourceIngestion,          # manager: poll(adapter_label=None), poll_once(adapter_label)
    IngestionConfig,          # dataclass: adapters, fetch_timeout=30s,
                               #            max_content_length=50_000, extract_links=True
    AdapterConfig,            # dataclass: adapter_type, source_label,
                               #            poll_interval=4h, enabled=True,
                               #            credentials=None, params={}
    ContentItem,              # dataclass: content, source, timestamp, url, linked_urls,
                               #            title, author, human_annotation
    IngestionResult,          # dataclass: items, adapter_label, errors, poll_timestamp
    IngestionError,           # dataclass: url, error, adapter_label
    # Errors
    SourceIngestionError,
    AdapterConfigError,
    AdapterNotFoundError,
)
```

Built-in `adapter_type` values: `rss`, `telegram_channel`, `reddit`,
`human_share`, `corpus_livejournal`, `corpus_blogspot`, `corpus_text`,
`corpus_facebook`, `corpus_twitter`.

### Usage pattern

```python
from datetime import timedelta
from toolkit.source_ingestion import (
    SourceIngestion, IngestionConfig, AdapterConfig,
)

config = IngestionConfig(adapters=[
    AdapterConfig(adapter_type="rss", source_label="some_blog",
                  poll_interval=timedelta(hours=4),
                  params={"feed_url": "https://example.com/feed.xml",
                          "marker_store_path": "./markers.json"}),
    AdapterConfig(adapter_type="corpus_text", source_label="my_archive",
                  params={"archive_path": "./seed/",
                          "marker_store_path": "./markers.json"}),
])

ingestion = SourceIngestion(config)
for result in ingestion.poll():
    print(f"{result.adapter_label}: {len(result.items)} items, "
          f"{len(result.errors)} errors")
```

### Notes

- Adapters use a durable `LastSeenMarker` (path via `params["marker_store_path"]`).
- Corpus adapters read static archives once and advance the marker to the last
  imported timestamp.
- Live adapters advance the marker after every poll.

---

## toolkit.feedback_collector

Normalizes platform feedback signals (reactions, replies, forwards, silence)
into structured `FeedbackEvent`s and writes them to a caller-supplied memory
store via a duck-typed contract.

### Key exports

```python
from toolkit.feedback_collector import (
    FeedbackCollector,        # register_output, process_signal, check_silence,
                               # check_delayed_engagement, update_unresolvedness_on_feedback
    FeedbackCollectorConfig,  # dataclass: silence_window=24h, delayed_recheck_window=7d,
                               #            positive_reactions (default ["👍","❤️","🔥","💡","🤔"]),
                               #            negative_reactions (default ["👎"]),
                               #            reply_is_positive=True, forward_is_positive=True
    FeedbackEvent,            # dataclass: output_message_id, output_intent_tag, output_mode,
                               #            signal_type ("like"|"dislike"|"reply"|"forward"
                               #                         |"silence"),
                               #            signal_value, source_note_ids, retention_criteria,
                               #            timestamp
    OutputRecord,             # dataclass: message_id, intent_tag, output_mode,
                               #            source_note_ids, retention_criteria,
                               #            delivered_at, feedback_events, silence_recorded
)
```

### Memory store contract (duck-typed)

The injected `memory_store` must structurally support:

```python
get_note(note_id: str) -> object         # with .tags, .tier, .unresolvedness
store_note(note) -> Any                  # accepts any object with the field shape of
                                         # toolkit.feedback_collector.types._NoteInput
update_note(note_id: str, patch) -> Any  # accepts any object with the field shape of
                                         # toolkit.feedback_collector.types._NotePatch
```

`_NoteInput` / `_NotePatch` are intentionally private — they mirror Phosphene's
`memory_store.NoteInput` / `NotePatch` shapes exactly so Phosphene's
`MemoryStore` accepts them by duck typing.

### Usage pattern

```python
from toolkit.feedback_collector import FeedbackCollector
from toolkit.gateway import FeedbackSignal

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

### Notes

- `register_output(output, delivery)` reads `output.source_note_ids`,
  `output.intent_tag`, `output.output_mode`, `delivery.success`,
  `delivery.message_id` — structural; works with `Gateway.DeliveryResult`.
- `process_signal(signal)` reads `signal.message_id`, `signal.signal_type`,
  `signal.value`, `signal.timestamp` — structural; works with
  `toolkit.gateway.FeedbackSignal`.
- `check_silence()` uses timezone-aware `datetime.now(timezone.utc)`. Consumers
  must deliver `OutputRecord.delivered_at` as timezone-aware.

---

## toolkit.cost_accountant

Cost ledger and budget enforcement that wraps `toolkit.llm_client`. Pre-call
estimation, per-call / operation / session budgets, append-only JSONL ledger,
rate-limit and spending-cap abort.

### Key exports

```python
from toolkit.cost_accountant import (
    CostAccountant,           # ledger-backed LLM call accountant
    CostBudget,               # dataclass: operation_name, operation_budget_usd,
                               #            session_budget_usd=100.0, per_call_max_usd=1.0,
                               #            abort_on_rate_limit=True, abort_on_spending_cap=True
    CostEstimate,             # dataclass: model, input_tokens, estimated_output_tokens,
                               #            input_cost_usd, output_cost_usd, total_usd
    BatchEstimate,            # dataclass: calls (list[CallEstimate]), total_usd
    CallEstimate,             # dataclass: label, input_tokens, estimated_cost_usd
    LedgerEntry,              # dataclass: one JSONL ledger row
    CostReport,               # dataclass: aggregated historical report
    ModelPricing,             # dataclass: input_per_mtok, output_per_mtok
    DEFAULT_PRICING,          # dict: Anthropic/OpenAI/Gemini pricing table
    normalize_model_name,     # strip date-snapshot suffix for pricing lookup
    # Errors
    CostAccountantError,
    BudgetExceededError,
    PerCallBudgetError,
    OperationBudgetError,
    SessionBudgetError,
    SpendingCapAbortError,
    RateLimitAbortError,
    UnknownModelError,
)
```

### Methods (CostAccountant)

```python
__init__(ledger_path: Path,
         pricing: dict[str, ModelPricing] | None = None,
         default_budget: CostBudget | None = None)

complete(*, messages: list[Message], config: LLMConfig, tier: ModelTier,
         budget: CostBudget | None = None,
         attribution: str | None = None,
         purpose: str | None = None) -> LLMResponse

estimate_cost(model: str, input_tokens: int,
              expected_output_tokens: int = 1000) -> CostEstimate

estimate_batch(model: str, calls: list[dict],
               expected_output_tokens_per_call: int = 1000) -> BatchEstimate

report(since: datetime | None = None) -> CostReport

session_total: float    # property — cumulative session spend
```

### Usage pattern

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

response = accountant.complete(
    messages=[Message(role="user", content="Summarize: ...")],
    config=LLMConfig(provider="anthropic", api_key="sk-ant-...",
                     models={"quality": "claude-sonnet-4-5-20250929"}),
    tier=ModelTier.QUALITY,
    attribution="my_pipeline",
)
print(f"Session spend: ${accountant.session_total:.4f}")
```

### Notes

- `budget` is optional in `complete()`; falls back to `default_budget`.
- Default-default budget: $25 session / $25 operation / $2 per call.
- Unknown models fall back to conservative pricing ($15 / $75 per Mtok).
- `normalize_model_name()` strips OpenAI `-YYYY-MM-DD` and Anthropic
  `-YYYYMMDD` date suffixes so dated IDs hit the pricing table.

---

## toolkit.structured_llm

LLM JSON extraction with schema injection, validation, and bounded retry.
Wraps an injected `llm_client` (typically `toolkit.llm_client`) — does not
import a provider directly.

### Key exports

```python
from toolkit.structured_llm import (
    Example,                  # dataclass: input (str), output (dict)
    StructuredResult,         # dataclass: success, data, raw, retries, error
    # High-level
    structured_call,          # async: full pipeline
    # Low-level primitives
    structured_complete,      # async: raw LLM call with messages (no parsing)
    parse_json_response,      # extract a JSON object from a model response string
    validate_json_schema,     # validate a parsed dict against a JSON Schema
    load_prompt,              # read a prompt template file
    load_schema,              # read a JSON Schema file
)
```

### Signature

```python
async def structured_call(
    llm_client: Any,                    # typically the toolkit.llm_client module
    config: dict,                        # LLMConfig-shaped dict
    tier: str,                           # e.g. "commodity"
    *,
    schema: dict,
    system_prompt: str,
    user_prompt: str,
    examples: list[Example] | list[dict] | None = None,
    max_retries: int = 1,
) -> StructuredResult
```

### Usage pattern

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
        system_prompt="Extract a title and tags.",
        user_prompt="A short essay about gardening...",
        examples=[Example(input="Note about coffee.",
                          output={"title": "Coffee", "tags": ["beverage"]})],
        max_retries=2,
    )
    if result.success:
        print(result.data)        # validated dict
    else:
        print(result.error, result.raw)

asyncio.run(main())
```

---

## toolkit.prompt_regression

Scenario-based prompt regression test framework. Loads scenarios from JSON
files, dispatches each to a consumer-provided async module callback, then
evaluates the response via JSON path checks and/or LLM-as-judge.

### Key exports

```python
from toolkit.prompt_regression import (
    ScenarioRunner,           # loads, dispatches, evaluates scenarios
    LLMJudge,                 # LLM-backed verdict
    JudgeResult,              # dataclass: verdict ("PASS"|"FAIL"), explanation, criteria
    PropertyCheck,            # dataclass: type ("json_path_exists" | "json_path_equals"
                               #                  | "llm_judge"), description, path, value,
                               #            criteria, pass_instruction, fail_instruction
    PropertyResult,           # dataclass: passed, description, expected, actual,
                               #            judge_explanation
    ScenarioResult,           # dataclass: scenario_id, description, properties, passed
    RunReport,                # dataclass: results, total, passed
    ModuleCaller,             # Protocol: async (module_name, payload, context) -> Any
    PROPERTY_TYPES,           # tuple of allowed PropertyCheck.type values
    load_scenario,            # load one scenario JSON file
    load_scenarios,           # load all scenarios in a directory
    json_path_exists,         # True if a JSONPath resolves in data
    json_path_get,            # resolve a JSONPath against data
)
```

### Classes

```python
class LLMJudge:
    def __init__(self, llm_client: Any, llm_config: dict,
                 tier: str = "commodity") -> None
    async def evaluate(self, response_text: str, criteria: str,
                       pass_instruction: str, fail_instruction: str,
                       context: str = "") -> JudgeResult

class ScenarioRunner:
    def __init__(self, llm_client: Any, llm_config: dict,
                 module_caller: Callable[[str, Any, dict], Awaitable[Any]]) -> None
    async def run_scenario(self, scenario: dict) -> ScenarioResult
    async def run_all(self, scenario_dir: str | Path,
                      module_filter: str | None = None) -> RunReport
```

### Scenario shape

```json
{
  "scenario_id": "extract-tags-from-essay",
  "description": "Extractor returns at least one tag",
  "module": "extractor",
  "input": "A short essay about gardening...",
  "properties": [
    {"type": "json_path_exists", "description": "has tags", "path": "$.tags"},
    {"type": "llm_judge", "description": "tags are relevant",
     "criteria": "Tags should describe the subject.",
     "pass_instruction": "Return PASS if any tag relates to gardening.",
     "fail_instruction": "Return FAIL if all tags are unrelated."}
  ]
}
```

### Usage pattern

```python
import asyncio
from toolkit import llm_client
from toolkit.prompt_regression import ScenarioRunner

async def call_my_module(module_name, payload, context):
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
    print(f"{report.passed}/{report.total} passed")

asyncio.run(main())
```

---

## toolkit.coaching

Tag-based operator-input parser. Reads lines like `PRIORITY: secure alliance`
or `/preview` and returns either a typed `CoachingEvent` (tag → routed
consumer + canonical type) or a `Command` (slash-command name + args). Tag
vocabulary and command list are loaded from a YAML config so consumers can
extend without code changes. No core dependencies; PyYAML is lazy-imported
only inside `load_routes_config`.

### Key exports

```python
from toolkit.coaching import (
    # Result types
    CoachingEvent,           # frozen dataclass: coaching_type, content, route
    Command,                 # frozen dataclass: name, args (dict)
    RouteRule,               # frozen dataclass: coaching_type, route
    # Parser
    TaggedCoachingParser,    # __init__(routes_path), .from_config(dict), .parse(text)
    # Config loader
    load_routes_config,      # YAML file -> dict (lazy-imports yaml)
)
```

### Config format

```yaml
tags:
  PRIORITY:
    route: coaching_queue
    coaching_type: PRIORITY
  INTEL:
    route: state_updater
    coaching_type: INTEL
  default:                 # required — used for untagged / unknown-tag input
    route: coaching_queue
    coaching_type: FREE

commands:
  - /preview
  - /approve
  - /edit
  - /block
```

### Usage pattern

```python
from toolkit.coaching import TaggedCoachingParser, CoachingEvent, Command

# Load from YAML config (requires pyyaml)
parser = TaggedCoachingParser("config/coaching_routes.yaml")

# Or pass an already-parsed dict (no yaml dependency required)
parser = TaggedCoachingParser.from_config({
    "tags": {
        "default": {"route": "coaching_queue", "coaching_type": "FREE"},
        "INTEL": {"route": "state_updater", "coaching_type": "INTEL"},
    },
    "commands": ["/preview", "/edit"],
})

# Parse operator input
result = parser.parse("INTEL: Alpha broke promise to Gamma")
# -> CoachingEvent(coaching_type="INTEL", content="...", route="state_updater")

result = parser.parse("/edit: soften the second paragraph")
# -> Command(name="edit", args={"text": "soften the second paragraph"})

result = parser.parse("untagged free text")
# -> CoachingEvent(coaching_type="FREE", content="...", route="coaching_queue")

# Dispatch
match result:
    case Command(name=name, args=args):
        handle_command(name, args)
    case CoachingEvent(route="state_updater", content=text):
        extract_and_update_state(text)
    case CoachingEvent(route="coaching_queue", coaching_type=tag, content=text):
        queue_for_next_response(tag, text)
```

### Notes

- Tag matching is case-insensitive (`priority:` and `PRIORITY:` route the same).
- Untagged input, unknown tags, and malformed tag lines all fall through to
  the `default` route with the default `coaching_type`.
- Unknown slash commands are returned as `CoachingEvent` on the default route
  (not as `Command`), so they don't get silently dropped.
- The `/edit` command is special-cased to capture the rest of the line as
  `args["text"]`; other commands return `args={}`.
- `from_config()` is the dependency-free constructor — use it when the
  consumer wants to control config loading (JSON, env vars, etc.) and avoid
  the PyYAML dependency.

---

## Project structure

```
toolkit/
├── pyproject.toml              # core dep: jsonschema; extras: anthropic, openai, google, ws
└── src/toolkit/
    ├── __init__.py
    ├── embedding/              # leaf — needs sentence-transformers + numpy
    │   ├── __init__.py
    │   ├── types.py            # EmbeddingConfig, EmbeddingResult, errors
    │   └── core.py             # embed, similarity, batch_similarity
    ├── clustering/             # leaf — needs hdbscan (lazy), umap (lazy)
    │   ├── __init__.py
    │   ├── types.py            # ClusterConfig, ClusterResult, ClusterStrategy, ClusterLayer, errors
    │   └── core.py             # cluster()
    ├── llm_client/             # leaf — lazy SDK loads
    │   ├── __init__.py
    │   ├── types.py            # LLMConfig, LLMResponse, TokenUsage, Message, ModelTier, errors
    │   └── providers.py        # LLMProvider ABC, Anthropic/OpenAI/Gemini/OpenRouter, create_provider
    ├── cost_accountant/        # composing — depends on llm_client
    │   ├── __init__.py
    │   ├── types.py            # CostBudget, CostEstimate, LedgerEntry, ModelPricing, DEFAULT_PRICING
    │   ├── errors.py           # Cost Accountant exception hierarchy
    │   └── core.py             # CostAccountant (estimate, complete, report)
    ├── structured_llm/         # leaf — wraps an injected llm_client at call time
    │   ├── __init__.py
    │   └── core.py             # structured_call + low-level primitives
    ├── prompt_regression/      # leaf — wraps an injected llm_client at call time
    │   ├── __init__.py
    │   ├── types.py            # PropertyCheck, PropertyResult, ScenarioResult, RunReport
    │   ├── judge.py            # LLMJudge
    │   └── runner.py           # ScenarioRunner, ModuleCaller Protocol
    ├── telegram_client/        # leaf — no external deps (urllib)
    │   ├── __init__.py
    │   ├── types.py            # TelegramUpdate, SendResult, InlineButton, InlineKeyboard, errors
    │   ├── transport.py        # HTTPSTransport (urllib), TelegramTransport Protocol
    │   ├── formatting.py       # escape_markdown, escape_url, format_link, split_message
    │   └── client.py           # TelegramClient (polling, send, edit, keyboard)
    ├── json_rpc/               # leaf — websockets only for WebSocketTransport extra
    │   ├── __init__.py         # lazy-loads WebSocketTransport
    │   ├── types.py            # error hierarchy
    │   ├── transport.py        # SubprocessTransport, JsonRpcTransport Protocol
    │   ├── transport_ws.py     # WebSocket transport (optional websockets dep)
    │   └── client.py           # JsonRpcClient (correlation, routing, lifecycle)
    ├── gateway/                # composing — optionally depends on telegram_client at runtime
    │   ├── __init__.py
    │   ├── types.py            # GatewayConfig, PlatformConfig, messages, signals
    │   ├── errors.py           # Gateway exception hierarchy
    │   ├── adapters.py         # Adapter Protocol + Log/Fake/Telegram adapters
    │   └── gateway.py          # Gateway manager (send, listener lifecycle)
    ├── source_ingestion/       # leaf — needs feedparser/praw for those adapters
    │   ├── __init__.py
    │   ├── types.py            # ContentItem, AdapterConfig, IngestionConfig
    │   ├── errors.py
    │   ├── adapters.py         # Adapter Protocol + registry + LastSeenMarker
    │   ├── ingestion.py        # SourceIngestion manager (poll, poll_once)
    │   ├── normalization.py    # URL fetching + content normalization helpers
    │   ├── rss.py              # RSS adapter
    │   ├── telegram_channel.py # Telegram channel adapter
    │   ├── reddit.py           # Reddit adapter
    │   ├── human_share.py      # Human-share (DM) adapter
    │   └── corpus.py           # LiveJournal/Blogspot/Text/Facebook/Twitter importers
    └── feedback_collector/     # leaf — duck-typed memory store contract
        ├── __init__.py
        ├── types.py            # FeedbackEvent, OutputRecord, _NoteInput, _NotePatch
        └── collector.py        # FeedbackCollector (register, classify, silence)
    └── coaching/               # leaf — no core deps (yaml lazy-imported)
        ├── __init__.py
        └── core.py             # CoachingEvent, Command, RouteRule, TaggedCoachingParser, load_routes_config
```

## Current consumers

| Project | Modules used |
|---------|-------------|
| **Diplomat** | `llm_client`, `cost_accountant`, `structured_llm`, `prompt_regression`, `telegram_client`, `coaching` |
| **Phosphene** | `embedding`, `clustering`, `llm_client`, `cost_accountant`, `gateway`, `source_ingestion`, `feedback_collector` |
| **Year-in-Search** | `embedding`, `clustering`, `llm_client` |
| **codexbot** | `telegram_client` (polling, messaging), `json_rpc` (Codex subprocess comms) |
| **TGbot** | `telegram_client` (formatting helpers), `llm_client` (LLM provider abstraction) |
