"""
Core clustering function: embeddings → cluster assignments via pluggable strategies.
"""

from __future__ import annotations

import numpy as np

from .types import (
    ClusterConfig,
    ClusterInputError,
    ClusterLayer,
    ClusterResult,
    ClusterStrategy,
    ClusterStrategyError,
)


def cluster(
    embeddings: np.ndarray,
    config: ClusterConfig | None = None,
    texts: list[str] | None = None,
) -> ClusterResult:
    """Cluster embeddings into semantically coherent groups.

    Args:
        embeddings: Matrix of embeddings, shape (n_items, embedding_dim). Must have >= 2 rows.
        config: Strategy and parameters. Uses HDBSCAN defaults if None.
        texts: Original text items corresponding to each embedding row.
               Required for RAPTOR strategy (used by raptor_summarizer). Ignored for HDBSCAN.

    Returns:
        ClusterResult with labels, cluster count, noise count.

    Raises:
        ClusterInputError: If fewer than 2 embeddings, or texts length doesn't match.
        ClusterStrategyError: If strategy is unknown, or RAPTOR is missing callbacks/texts.
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
        return _cluster_raptor(embeddings, config, texts)

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


def _cluster_raptor(
    embeddings: np.ndarray,
    config: ClusterConfig,
    texts: list[str] | None,
) -> ClusterResult:
    """Run RAPTOR recursive clustering: cluster → summarize → embed → recurse.

    Builds a tree of ClusterLayer objects from leaf (depth 0) to root.
    Recursion stops when max_depth is reached or when only one cluster remains.
    """
    if config.raptor_summarizer is None:
        raise ClusterStrategyError(
            "RAPTOR strategy requires raptor_summarizer callback"
        )
    if config.raptor_embedder is None:
        raise ClusterStrategyError(
            "RAPTOR strategy requires raptor_embedder callback"
        )
    if texts is None:
        raise ClusterStrategyError(
            "RAPTOR strategy requires texts parameter"
        )
    if len(texts) != embeddings.shape[0]:
        raise ClusterInputError(
            f"texts length ({len(texts)}) must match embeddings rows "
            f"({embeddings.shape[0]})"
        )

    tree: list[ClusterLayer] = []
    current_texts = list(texts)

    # Run HDBSCAN at the leaf level to get initial labels
    leaf_result = _cluster_hdbscan(embeddings, config)
    leaf_labels = leaf_result.labels

    # Build leaf layer (depth 0) — original items grouped by HDBSCAN
    leaf_cluster_ids = sorted(set(int(l) for l in leaf_labels if l >= 0))
    leaf_member_counts = {
        cid: int(np.sum(leaf_labels == cid)) for cid in leaf_cluster_ids
    }
    tree.append(
        ClusterLayer(
            depth=0,
            cluster_ids=leaf_cluster_ids,
            member_counts=leaf_member_counts,
            summaries=None,
        )
    )

    # Config without UMAP for recursive levels — summary embeddings may have
    # fewer dimensions than reduce_dims, which would crash UMAP.
    from dataclasses import replace

    recurse_config = replace(config, reduce_dims=None)

    # Recurse: summarize clusters → embed summaries → re-cluster
    for depth in range(1, config.raptor_max_depth + 1):
        if len(leaf_cluster_ids) <= 1:
            break

        # Summarize each cluster
        summaries: dict[int, str] = {}
        summary_texts: list[str] = []

        for cid in leaf_cluster_ids:
            mask = leaf_labels == cid
            cluster_texts = [current_texts[i] for i, m in enumerate(mask) if m]
            summary = config.raptor_summarizer(cluster_texts)
            summaries[cid] = summary
            summary_texts.append(summary)

        # Update previous layer with summaries
        tree[-1].summaries = summaries

        # Embed summaries for next level
        summary_embeddings = config.raptor_embedder(summary_texts)
        summary_embeddings = np.asarray(summary_embeddings)

        # If fewer than 2 summaries or fewer than min_cluster_size, stop
        if summary_embeddings.shape[0] < max(2, config.min_cluster_size):
            break

        # Re-cluster the summary embeddings (no UMAP on recursive levels)
        next_result = _cluster_hdbscan(summary_embeddings, recurse_config)
        next_labels = next_result.labels

        next_cluster_ids = sorted(set(int(l) for l in next_labels if l >= 0))
        next_member_counts = {
            cid: int(np.sum(next_labels == cid)) for cid in next_cluster_ids
        }

        tree.append(
            ClusterLayer(
                depth=depth,
                cluster_ids=next_cluster_ids,
                member_counts=next_member_counts,
                summaries=None,
            )
        )

        # Prepare for next iteration
        current_texts = summary_texts
        leaf_labels = next_labels
        leaf_cluster_ids = next_cluster_ids

    return ClusterResult(
        labels=leaf_result.labels,
        n_clusters=leaf_result.n_clusters,
        n_noise=leaf_result.n_noise,
        strategy=config.strategy.value,
        tree=tree,
    )
