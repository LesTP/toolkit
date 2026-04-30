# ARCH: Clustering

## Purpose
Group embeddings into semantically coherent clusters. Strategy-agnostic — consumers specify which algorithm and parameters to use. Supports flat clustering (HDBSCAN) and hierarchical recursive clustering (RAPTOR-style). Does not embed text — accepts pre-computed embeddings from the Embedding module.

## Public API

### cluster
- **Signature:** `cluster(embeddings: ndarray, config: ClusterConfig | None = None, texts: list[str] | None = None) -> ClusterResult`
- **Parameters:**
  - embeddings: ndarray — shape (n_items, embedding_dim). Must have at least 2 rows.
  - config: ClusterConfig | None — strategy and parameters. If None, uses HDBSCAN defaults.
    ```python
    @dataclass
    class ClusterConfig:
        strategy: ClusterStrategy = ClusterStrategy.HDBSCAN
        min_cluster_size: int = 5
        min_samples: int = 3
        metric: str = "euclidean"
        reduce_dims: int | None = None       # UMAP reduction before clustering. None = skip
        raptor_max_depth: int = 3             # RAPTOR only: max recursion depth
        raptor_summarizer: Callable | None = None  # RAPTOR only: function to summarize a cluster
        raptor_embedder: Callable | None = None    # RAPTOR only: function to embed summaries into vectors
    ```
  - texts: list[str] | None — original text items corresponding to each embedding row. Required for RAPTOR strategy (passed to raptor_summarizer). Ignored for HDBSCAN.
- **Returns:** ClusterResult
- **Errors:**
  - `ClusterInputError` — fewer than 2 embeddings, embedding_dim mismatch across rows, or texts length doesn't match embeddings rows
  - `ClusterStrategyError` — unknown strategy, or RAPTOR missing required callbacks (raptor_summarizer, raptor_embedder) or texts parameter
  - `ValueError` — min_cluster_size < 2 or min_samples < 1

### ClusterStrategy enum
```python
class ClusterStrategy(str, Enum):
    HDBSCAN = "hdbscan"       # flat density-based clustering
    RAPTOR = "raptor"         # recursive: cluster → summarize → re-cluster
```

## Inputs
- Pre-computed embeddings (ndarray from Embedding module)
- ClusterConfig specifying strategy and parameters
- For RAPTOR strategy: a `raptor_summarizer` callable that takes a list of texts and returns a summary string, and a `raptor_embedder` callable that takes a list of strings and returns an ndarray of embeddings. The clustering module calls these but does not implement them — consumers provide their own logic (typically via Embedding and LLM Client modules).

## Outputs
- **ClusterResult:**
  ```python
  @dataclass
  class ClusterResult:
      labels: ndarray               # shape (n_items,) — cluster assignment per item. -1 = noise
      n_clusters: int               # number of clusters found (excluding noise)
      n_noise: int                  # number of items labeled as noise
      strategy: str                 # strategy used
      tree: list[ClusterLayer] | None  # RAPTOR only: hierarchy of cluster layers. None for flat strategies

  @dataclass
  class ClusterLayer:
      depth: int                    # 0 = leaf (original items), 1 = first summary, etc.
      cluster_ids: list[int]        # cluster IDs at this layer
      member_counts: dict[int, int] # cluster_id → number of members
      summaries: dict[int, str] | None  # cluster_id → summary text (RAPTOR only)
  ```
- Guarantees:
  - `labels.shape[0] == embeddings.shape[0]` — one label per input
  - Labels are integers: 0 to n_clusters-1 for assigned items, -1 for noise
  - For HDBSCAN: results are deterministic for a given input + config
  - For RAPTOR: `tree` is populated with layers from leaf to root. Each layer's summaries are produced by the consumer-provided summarizer

## State
None. Clustering is stateless — each call is independent.

## Usage Example
```python
from clustering import cluster, ClusterConfig, ClusterStrategy
from embedding import embed

# Flat clustering (Year-in-Search style)
result = embed(titles)
clusters = cluster(result.vectors, ClusterConfig(
    strategy=ClusterStrategy.HDBSCAN,
    min_cluster_size=5,
    reduce_dims=50,
))
print(f"Found {clusters.n_clusters} clusters, {clusters.n_noise} noise items")

# Hierarchical clustering (Phosphene distillation style)
def summarize_cluster(texts: list[str]) -> str:
    return llm_client.complete(f"Summarize these observations: {texts}").content

def embed_texts(texts: list[str]) -> np.ndarray:
    return embed(texts).vectors

clusters = cluster(result.vectors, ClusterConfig(
    strategy=ClusterStrategy.RAPTOR,
    raptor_max_depth=3,
    raptor_summarizer=summarize_cluster,
    raptor_embedder=embed_texts,
), texts=titles)
for layer in clusters.tree:
    print(f"Depth {layer.depth}: {len(layer.cluster_ids)} clusters")
```
