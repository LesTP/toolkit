"""
Core clustering function: embeddings → cluster assignments via pluggable strategies.
"""

import numpy as np

from .types import (
    ClusterConfig,
    ClusterInputError,
    ClusterResult,
    ClusterStrategy,
    ClusterStrategyError,
)


def cluster(
    embeddings: np.ndarray,
    config: ClusterConfig | None = None,
) -> ClusterResult:
    """Cluster embeddings into semantically coherent groups.

    Args:
        embeddings: Matrix of embeddings, shape (n_items, embedding_dim). Must have >= 2 rows.
        config: Strategy and parameters. Uses HDBSCAN defaults if None.

    Returns:
        ClusterResult with labels, cluster count, noise count.

    Raises:
        ClusterInputError: If fewer than 2 embeddings.
        ClusterStrategyError: If strategy is not yet supported.
        ValueError: If min_cluster_size < 2 or min_samples < 1.
    """
    if config is None:
        config = ClusterConfig()

    if embeddings.ndim != 2 or embeddings.shape[0] < 2:
        raise ClusterInputError(
            f"embeddings must be a 2-D array with at least 2 rows, "
            f"got shape {embeddings.shape}"
        )

    if config.min_cluster_size < 2:
        raise ValueError(
            f"min_cluster_size must be >= 2, got {config.min_cluster_size}"
        )

    if config.min_samples < 1:
        raise ValueError(f"min_samples must be >= 1, got {config.min_samples}")

    if config.strategy == ClusterStrategy.HDBSCAN:
        return _cluster_hdbscan(embeddings, config)

    if config.strategy == ClusterStrategy.RAPTOR:
        raise ClusterStrategyError(
            "RAPTOR strategy is not yet implemented"
        )

    raise ClusterStrategyError(f"Unknown strategy: {config.strategy}")


def _cluster_hdbscan(
    embeddings: np.ndarray,
    config: ClusterConfig,
) -> ClusterResult:
    """Run HDBSCAN flat clustering, with optional UMAP reduction."""
    import hdbscan

    data = embeddings
    if config.reduce_dims is not None:
        import umap

        reducer = umap.UMAP(n_components=config.reduce_dims, random_state=42)
        data = reducer.fit_transform(data)

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=config.min_cluster_size,
        min_samples=config.min_samples,
        metric=config.metric,
    )
    labels = clusterer.fit_predict(data)
    labels = np.asarray(labels, dtype=np.int32)

    n_noise = int(np.sum(labels == -1))
    n_clusters = len(set(labels) - {-1})

    return ClusterResult(
        labels=labels,
        n_clusters=n_clusters,
        n_noise=n_noise,
        strategy=config.strategy.value,
        tree=None,
    )
