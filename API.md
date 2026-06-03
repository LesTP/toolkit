# Toolkit API Contracts

Canonical API signatures for all toolkit modules. Use these when building fakes
in consumer projects where toolkit is not importable.

Last synced: 2026-06-02

**Consumers:** Diplomat, Phosphene, Codexbot, Year-in-Search, TGBot

---

## toolkit.embedding
**Consumers:** Year-in-Search, Phosphene

### Types

```python
@dataclass
class EmbeddingConfig:
    model: str = "all-MiniLM-L6-v2"
    batch_size: int = 256
    cache_dir: str | None = None
    device: str = "cpu"

@dataclass
class EmbeddingResult:
    vectors: np.ndarray          # shape (n_texts, dimension)
    model: str
    dimension: int
    from_cache: int
    computed: int

class EmbeddingModelError(Exception):
    message: str
    model: str | None

class EmbeddingInputError(Exception):
    message: str
```

### Functions

```python
embed(texts: list[str], config: EmbeddingConfig) -> EmbeddingResult
similarity(a: np.ndarray, b: np.ndarray) -> float
batch_similarity(query: np.ndarray, candidates: np.ndarray) -> np.ndarray
```

---

## toolkit.clustering
**Consumers:** Year-in-Search, Phosphene

### Types

```python
class ClusterStrategy(str, Enum):
    HDBSCAN = "hdbscan"
    RAPTOR = "raptor"

@dataclass
class ClusterConfig:
    strategy: ClusterStrategy = ClusterStrategy.HDBSCAN
    min_cluster_size: int = 5
    min_samples: int = 3
    metric: str = "euclidean"
    reduce_dims: int | None = None
    raptor_max_depth: int = 3
    raptor_summarizer: Callable | None = None    # RAPTOR only
    raptor_embedder: Callable | None = None      # RAPTOR only

@dataclass
class ClusterLayer:
    depth: int
    cluster_ids: list[int]
    member_counts: dict[int, int]
    summaries: dict[int, str] | None = None

@dataclass
class ClusterResult:
    labels: np.ndarray           # shape (n_items,)
    n_clusters: int
    n_noise: int
    strategy: str
    tree: list[ClusterLayer] | None = None       # RAPTOR only

class ClusterInputError(Exception):
    message: str

class ClusterStrategyError(Exception):
    message: str
```

### Functions

```python
cluster(embeddings: np.ndarray, config: ClusterConfig,
        texts: list[str] | None = None) -> ClusterResult
```

---

## toolkit.llm_client
**Consumers:** Diplomat, Phosphene, Codexbot, TGBot, Year-in-Search

### Types

```python
@dataclass
class Message:
    role: str                    # "system" | "user" | "assistant"
    content: str

class ModelTier(str, Enum):
    QUALITY = "quality"
    DEFAULT = "default"
    COMMODITY = "commodity"

@dataclass
class LLMConfig:
    provider: str                # "anthropic" | "openai" | "google" | "openrouter"
    api_key: str
    models: dict[str, str]       # tier name → model ID
    max_tokens: int = 4096
    temperature: float = 0.7

@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    token_usage: TokenUsage

@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int

class LLMAPIError(Exception):
    message: str
    status_code: int | None
    retry_after: float | None

class LLMResponseError(Exception):
    message: str
```

### Functions

```python
complete(messages: list[Message], config: LLMConfig,
         tier: ModelTier = ModelTier.DEFAULT) -> LLMResponse
create_provider(config: LLMConfig) -> LLMProvider
```

**Provider-specific behavior:** `OpenAIProvider.call()` internally dispatches the token-limit kwarg by model prefix — `gpt-5*` / `o1*` / `o3*` / `o4*` get `max_completion_tokens`, others get `max_tokens`. `OpenRouterProvider` always uses `max_tokens` (OpenRouter handles reasoning models internally). Consumers always pass `max_tokens: int` on the `LLMProvider.call()` contract; per-provider translation is internal. See `ARCH_llm_client.md` "Token-parameter dispatch."

**OpenRouter usage:** Set `provider="openrouter"` and `api_key=OPENROUTER_API_KEY`. Model names use OpenRouter's `provider/model` format (e.g. `"meta-llama/llama-3.3-70b-instruct"`, `"deepseek/deepseek-v3"`). Pricing for representative models is in `cost_accountant/types.py`; unknown models fall through to the conservative default.

---

## toolkit.telegram_client
**Consumers:** Diplomat, Phosphene, Codexbot, TGBot

### Types

```python
class TelegramClient:
    def __init__(self, bot_token: str, *,
                 transport: TelegramTransport | None = None,
                 request_timeout_seconds: float = 10.0,
                 poll_timeout_seconds: float = 25.0) -> None

@dataclass(frozen=True)
class TelegramUpdate:
    chat_id: int
    user_id: int
    message_text: str            # NOTE: not "text" or "content"
    command: str | None
    args: tuple[str, ...]
    message_id: int
    raw: dict[str, Any]

@dataclass(frozen=True)
class SendResult:
    success: bool
    message_id: int | None = None
    error: str | None = None

class TelegramAPIError(TelegramClientError): ...
class TelegramClientError(Exception): ...
```

### Methods (TelegramClient)

```python
async send_message(chat_id: int, text: str, reply_to: int | None = None,
                   *, parse_mode: str | None = None) -> int
async start_polling(*, initial_offset: int | None = None) -> None
async stop_polling() -> None
async get_next_update() -> TelegramUpdate | None
async send_with_keyboard(chat_id: int, text: str, keyboard: InlineKeyboard,
                          *, parse_mode: str | None = None) -> SendResult
async edit_message(chat_id: int, message_id: int, text: str,
                   *, parse_mode: str | None = None) -> None
```

---

## toolkit.json_rpc
**Consumers:** Codexbot

### Types

```python
class JsonRpcClient:
    def __init__(self, transport: JsonRpcTransport) -> None

class SubprocessTransport(JsonRpcTransport):
    def __init__(self, command: list[str], *, cwd: str | None = None) -> None

class WebSocketTransport(JsonRpcTransport):
    def __init__(self, url: str) -> None

class JsonRpcError(Exception): ...
class JsonRpcErrorResponse(JsonRpcError): ...
class JsonRpcProtocolError(JsonRpcError): ...
class JsonRpcTimeoutError(JsonRpcError): ...
class JsonRpcTransportError(JsonRpcError): ...
```

### Methods (JsonRpcClient)

```python
async request(method: str, params: dict | list | None = None,
              timeout: float | None = None) -> Any
async notify(method: str, params: dict | list | None = None) -> None
async start() -> None
async stop() -> None
```

---

## toolkit.cost_accountant
**Consumers:** Diplomat, Phosphene

### Types

```python
class CostAccountant:
    def __init__(self, ledger_path: Path,
                 pricing: dict[str, ModelPricing] | None = None,
                 default_budget: CostBudget | None = None) -> None

@dataclass
class CostBudget:
    operation_name: str
    operation_budget_usd: float
    session_budget_usd: float = 100.0
    per_call_max_usd: float = 1.0
    abort_on_rate_limit: bool = True
    abort_on_spending_cap: bool = True

@dataclass
class CostEstimate:
    model: str
    input_tokens: int
    estimated_output_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_usd: float

@dataclass
class ModelPricing:
    input_per_mtok: float
    output_per_mtok: float

class BudgetExceededError(CostAccountantError): ...
class RateLimitAbortError(CostAccountantError): ...
class SpendingCapAbortError(CostAccountantError): ...
```

### Methods (CostAccountant)

```python
complete(messages: list[Message], config: LLMConfig, tier: ModelTier,
         budget: CostBudget | None = None) -> LLMResponse
estimate_cost(model: str, input_tokens: int,
              expected_output_tokens: int = 1000) -> CostEstimate
report(since: datetime | None = None) -> CostReport
session_total: float  # property — cumulative spend this session
```

### Notes
- `budget` is optional in `complete()`. Falls back to `default_budget` from constructor. Constructor default: $25 session / $25 operation / $2 per call.
- Unknown models use conservative fallback pricing ($15/$75 per Mtok) — matches the most expensive known model.
- Default pricing includes Anthropic (claude-sonnet-4-6, claude-haiku-4-5, claude-opus-4) and OpenAI (gpt-4.1, gpt-4.1-mini, gpt-4o, gpt-5.5, o3, o4-mini, etc.).

---

## toolkit.prompt_regression
**Consumers:** Diplomat

### Types

```python
@dataclass(frozen=True)
class PropertyCheck:
    type: str                    # "json_path_exists" | "json_path_equals" | "llm_judge"
    description: str
    path: str | None = None
    value: Any | None = None
    criteria: str | None = None
    pass_instruction: str | None = None
    fail_instruction: str | None = None

@dataclass(frozen=True)
class PropertyResult:
    passed: bool
    description: str
    expected: Any | None = None
    actual: Any | None = None
    judge_explanation: str | None = None

@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    description: str
    properties: list[PropertyResult]
    passed: bool

@dataclass(frozen=True)
class RunReport:
    results: list[ScenarioResult]
    total: int
    passed: int

@dataclass(frozen=True)
class JudgeResult:
    verdict: str                 # "PASS" | "FAIL"
    explanation: str
    criteria: str
```

### Functions

```python
load_scenario(path: str | Path) -> dict[str, Any]
load_scenarios(directory: str | Path) -> list[dict[str, Any]]
json_path_exists(data: Any, path: str) -> bool
json_path_get(data: Any, path: str) -> Any
```

### Classes

```python
class LLMJudge:
    def __init__(self, llm_client: Any, llm_config: dict[str, Any],
                 tier: str = "commodity") -> None
    async def evaluate(self, response_text: str, criteria: str,
                       pass_instruction: str, fail_instruction: str,
                       context: str = "") -> JudgeResult

class ScenarioRunner:
    def __init__(self, llm_client: Any, llm_config: dict[str, Any],
                 module_caller: Callable[[str, Any, dict], Awaitable[Any]]) -> None
    async def run_scenario(self, scenario: dict[str, Any]) -> ScenarioResult
    async def run_all(self, scenario_dir: str | Path,
                      module_filter: str | None = None) -> RunReport
```

---

## toolkit.structured_llm
**Consumers:** Diplomat

### Types

```python
@dataclass
class Example:
    input: str
    output: dict[str, Any]

@dataclass
class StructuredResult:
    success: bool
    data: dict[str, Any] | None = None
    raw: str = ""
    retries: int = 0
    error: str | None = None
```

### Functions

```python
# High-level: prompt assembly + schema injection + examples + validate + retry
async structured_call(llm_client: Any, config: dict[str, Any], tier: str, *,
                      schema: dict[str, Any], system_prompt: str,
                      user_prompt: str,
                      examples: list[Example] | list[dict] | None = None,
                      max_retries: int = 1) -> StructuredResult

# Low-level primitives (kept for backwards compatibility)
async structured_complete(llm_client: Any, config: dict[str, Any], tier: str,
                           messages: list[dict[str, str]]) -> str
parse_json_response(response_text: str) -> dict[str, Any]
validate_json_schema(data: dict[str, Any], schema: dict[str, Any],
                     label: str = "") -> None
load_prompt(path: str | Path) -> str
load_schema(path: str | Path) -> dict[str, Any]
```

---

## toolkit.gateway
**Consumers:** Phosphene

### Types

```python
@dataclass
class GatewayConfig:
    platforms: list[PlatformConfig]
    default_platform: str
    listen: bool = True

@dataclass
class PlatformConfig:
    name: str
    adapter_type: str            # "telegram" | "log" | "fake"
    credentials: dict
    params: dict = field(default_factory=dict)
    enabled: bool = True
    output_formats: list[str] = field(default_factory=lambda: ["text"])
                                 # supported: "text" | "markdown" | "thread" | "telegraph"

@dataclass
class InboundMessage:
    content: str
    platform: str
    message_id: str
    sender: str
    timestamp: datetime
    reply_to: str | None = None
    reactions: list[str] | None = None
    raw: dict | None = None

@dataclass
class OutboundMessage:
    content: str
    platform: str
    format: str = "text"
    reply_to: str | None = None
    intent_tag: str | None = None
    metadata: dict = field(default_factory=dict)

@dataclass
class DeliveryResult:
    success: bool
    platform: str
    message_id: str | None
    error: str | None = None

@dataclass(kw_only=True)
class FeedbackSignal:
    platform: str
    message_id: str
    signal_type: str             # "reaction" | "reply" | "edit" | adapter-specific
    value: str | None = None
    sender: str
    timestamp: datetime

class GatewayError(Exception): ...
class PlatformConfigError(GatewayError): ...
class PlatformConnectionError(GatewayError): ...
class PlatformNotFoundError(GatewayError): ...
class FormatNotSupportedError(GatewayError): ...
class DeliveryError(GatewayError): ...
```

### Class

```python
class Gateway:
    def __init__(self, config: GatewayConfig,
                 on_message: Callable[[InboundMessage], None],
                 on_feedback: Callable[[FeedbackSignal], None],
                 *,
                 _adapter_factories: Mapping[str, AdapterFactory] | None = None,
                 _telegram_client_factory: TelegramClientFactory | None = None) -> None
    def send(self, message: OutboundMessage) -> DeliveryResult
    def send_to_default(self, content: str, format: str = "text",
                        intent_tag: str | None = None) -> DeliveryResult
    def start_listener(self) -> None
    def stop_listener(self) -> None
```

### Notes
- Telegram adapter optionally imports `toolkit.telegram_client` at runtime — the second documented toolkit cross-module exception (alongside Cost Accountant → LLM Client). Log and fake adapters work without it.
- Inbound + feedback callbacks are isolated; adapter errors surface as `DeliveryResult.success=False` rather than exceptions out of `send()`.

---

## toolkit.source_ingestion
**Consumers:** Phosphene

### Types

```python
@dataclass
class ContentItem:
    content: str
    source: str
    timestamp: datetime
    url: str | None = None
    linked_urls: list[str] = field(default_factory=list)
    title: str | None = None
    author: str | None = None
    human_annotation: str | None = None

@dataclass
class AdapterConfig:
    adapter_type: str            # "rss" | "telegram_channel" | "reddit" | "human_share"
                                 # | "corpus_livejournal" | "corpus_blogspot"
                                 # | "corpus_text" | "corpus_facebook"
                                 # | "corpus_twitter"
    source_label: str
    poll_interval: timedelta = timedelta(hours=4)
    enabled: bool = True
    credentials: dict | None = None
    params: dict = field(default_factory=dict)

@dataclass
class IngestionConfig:
    adapters: list[AdapterConfig]
    fetch_timeout: timedelta = timedelta(seconds=30)
    max_content_length: int = 50_000
    extract_links: bool = True

@dataclass
class IngestionResult:
    items: list[ContentItem]
    adapter_label: str
    errors: list[IngestionError]
    poll_timestamp: datetime

@dataclass
class IngestionError:
    url: str | None
    error: str
    adapter_label: str

class SourceIngestionError(Exception): ...
class AdapterConfigError(SourceIngestionError): ...
class AdapterNotFoundError(SourceIngestionError): ...
```

### Class

```python
class SourceIngestion:
    def __init__(self, config: IngestionConfig) -> None
    def poll(self, adapter_label: str | None = None) -> list[IngestionResult]
    def poll_once(self, adapter_label: str) -> IngestionResult
```

### Notes
- Adapters use a durable `LastSeenMarker` (path configurable via `params["marker_store_path"]`) so polling is idempotent across restarts.
- Corpus adapters (LiveJournal, Blogspot, plain text, Facebook archive HTML) read static archives once and advance the marker to the last imported timestamp.
- Live adapters (RSS, Telegram channel, Reddit, human-share DM) advance the marker after every poll.

---

## toolkit.feedback_collector
**Consumers:** Phosphene

### Types

```python
@dataclass
class FeedbackEvent:
    output_message_id: str
    output_intent_tag: str
    output_mode: str
    signal_type: str             # "like" | "dislike" | "reply" | "forward" | "silence"
    signal_value: str | None = None
    source_note_ids: list[str] = field(default_factory=list)
    retention_criteria: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class FeedbackCollectorConfig:
    silence_window: timedelta = timedelta(hours=24)
    delayed_recheck_window: timedelta = timedelta(days=7)
    positive_reactions: list[str] = field(
        default_factory=lambda: ["👍", "❤️", "🔥", "💡", "🤔"]
    )
    negative_reactions: list[str] = field(default_factory=lambda: ["👎"])
    reply_is_positive: bool = True
    forward_is_positive: bool = True

@dataclass
class OutputRecord:
    message_id: str
    intent_tag: str
    output_mode: str
    source_note_ids: list[str]
    retention_criteria: list[str]
    delivered_at: datetime
    feedback_events: list[FeedbackEvent] = field(default_factory=list)
    silence_recorded: bool = False
```

### Class

```python
class FeedbackCollector:
    def __init__(self, memory_store, config: FeedbackCollectorConfig | None = None) -> None
    def register_output(self, output, delivery) -> None
    def process_signal(self, signal) -> FeedbackEvent | None
    def check_silence(self) -> list[FeedbackEvent]
    def check_delayed_engagement(self) -> list[FeedbackEvent]
    def update_unresolvedness_on_feedback(self, event: FeedbackEvent) -> None
```

### Memory store contract (duck-typed)

The injected `memory_store` must structurally support:

```python
get_note(note_id: str) -> object       # with .tags, .tier, .unresolvedness attrs
store_note(note) -> Any                # accepts any object with the field shape of
                                       # toolkit.feedback_collector.types._NoteInput
update_note(note_id: str, patch) -> Any
                                       # accepts any object with the field shape of
                                       # toolkit.feedback_collector.types._NotePatch
```

The `_NoteInput` / `_NotePatch` shapes are intentionally private — they mirror Phosphene's `memory_store.NoteInput` / `NotePatch` field names and types exactly so Phosphene's `MemoryStore` accepts them by duck typing without a Phosphene-side wiring change. Other consumers wire any memory store that satisfies the structural contract.

### Notes
- `register_output(output, delivery)` reads `output.source_note_ids`, `output.intent_tag`, `output.output_mode` and `delivery.success`, `delivery.message_id` — structural; works with `Gateway.DeliveryResult` and `GeneratorOutput` from any consumer.
- `process_signal(signal)` reads `signal.message_id`, `signal.signal_type`, `signal.value`, `signal.timestamp` — structural; works with `toolkit.gateway.FeedbackSignal`.
- `check_silence()` and `_prune_old_records()` use timezone-aware `datetime.now(timezone.utc)`. Consumers must deliver `OutputRecord.delivered_at` as timezone-aware (Phosphene currently has a pre-existing naive-vs-aware mismatch; see Phosphene `DESIGN_GLOBAL.md`).
