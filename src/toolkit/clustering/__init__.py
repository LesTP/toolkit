"""
toolkit.clustering — semantic grouping over embeddings.

Public API:
    cluster             — embeddings → ClusterResult (labels + metadata)
    ClusterConfig       — strategy, min_cluster_size, min_samples, metric, reduce_dims
    ClusterResult       — labels (ndarray), n_clusters, n_noise, strategy, tree
    ClusterStrategy     — HDBSCAN, RAPTOR
    ClusterLayer        — RAPTOR tree node (depth, cluster_ids, summaries)
    ClusterInputError   — input validation failed
    ClusterStrategyError — unsupported or misconfigured strategy
"""

from toolkit.clustering.core import cluster
from toolkit.clustering.types import (
    ClusterConfig,
    ClusterInputError,
    ClusterLayer,
    ClusterResult,
    ClusterStrategy,
    ClusterStrategyError,
)

__all__ = [
    "cluster",
    "ClusterConfig",
    "ClusterResult",
    "ClusterStrategy",
    "ClusterLayer",
    "ClusterInputError",
    "ClusterStrategyError",
]
