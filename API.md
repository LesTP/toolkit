# Toolkit API Contracts

Canonical API signatures for all toolkit modules. Use these when building fakes
in consumer projects where toolkit is not importable.

Last synced: 2026-05-28

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
    provider: str                # "anthropic" | "openai" | "google"
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
                 pricing: dict[str, ModelPricing] | None = None) -> None

@dataclass
class CostBudget:
    per_call_usd: float | None = None
    operation_usd: float | None = None
    session_usd: float | None = None
    abort_on_rate_limit: bool = False
    abort_on_spending_cap: bool = False

@dataclass
class CostEstimate:
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float

@dataclass
class ModelPricing:
    input_per_million: float
    output_per_million: float

class BudgetExceededError(CostAccountantError): ...
class RateLimitAbortError(CostAccountantError): ...
class SpendingCapAbortError(CostAccountantError): ...
```

### Methods (CostAccountant)

```python
complete(messages: list[Message], config: LLMConfig, tier: ModelTier, *,
         budget: CostBudget | None = None, operation: str | None = None) -> LLMResponse
estimate_cost(model: str, input_tokens: int, output_tokens: int) -> CostEstimate
report(since: datetime | None = None) -> CostReport
```

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

### Functions

```python
async structured_complete(llm_client: Any, config: dict[str, Any], tier: str,
                           messages: list[dict[str, str]]) -> str
parse_json_response(response_text: str) -> dict[str, Any]
validate_json_schema(data: dict[str, Any], schema: dict[str, Any],
                     label: str = "") -> None
load_prompt(path: str | Path) -> str
load_schema(path: str | Path) -> dict[str, Any]
```
