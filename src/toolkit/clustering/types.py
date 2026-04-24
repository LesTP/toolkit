"""
Clustering types: configuration, result, strategy, and error classes.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------


class ClusterStrategy(str, Enum):
    """Clustering algorithm selection."""

    HDBSCAN = "hdbscan"  # flat density-based clustering
    RAPTOR = "raptor"  # recursive: cluster → summarize → re-cluster


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class ClusterConfig:
    """Configuration for the clustering module.

    Args:
        strategy: Clustering algorithm to use.
        min_cluster_size: Minimum number of items to form a cluster. Must be >= 2.
        min_samples: Controls density requirement. Must be >= 1.
        metric: Distance metric for clustering.
        reduce_dims: UMAP reduction before clustering. None = skip.
        raptor_max_depth: RAPTOR only: max recursion depth.
        raptor_summarizer: RAPTOR only: function to summarize a cluster's texts.
        raptor_embedder: RAPTOR only: function to embed summary texts into vectors.
    """

    strategy: ClusterStrategy = ClusterStrategy.HDBSCAN
    min_cluster_size: int = 5
    min_samples: int = 3
    metric: str = "euclidean"
    reduce_dims: Optional[int] = None
    raptor_max_depth: int = 3
    raptor_summarizer: Optional[Callable] = None
    raptor_embedder: Optional[Callable] = None


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class ClusterLayer:
    """A single layer in a RAPTOR cluster hierarchy.

    depth=0 is the leaf layer (original items), depth=1 is the first
    summary layer, etc.
    """

    depth: int
    cluster_ids: list[int]
    member_counts: dict[int, int]  # cluster_id → number of members
    summaries: Optional[dict[int, str]] = None  # cluster_id → summary text


@dataclass
class ClusterResult:
    """Result of a cluster() call.

    Guarantees:
        - labels.shape[0] == number of input embeddings (same order)
        - Labels are integers: 0 to n_clusters-1 for assigned, -1 for noise
        - tree is None for flat strategies (HDBSCAN)
    """

    labels: np.ndarray  # shape (n_items,) — cluster assignment per item
    n_clusters: int  # number of clusters found (excluding noise)
    n_noise: int  # number of items labeled as noise
    strategy: str  # strategy used
    tree: Optional[list[ClusterLayer]] = None  # RAPTOR only


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ClusterInputError(Exception):
    """Input validation failed (e.g. fewer than 2 embeddings)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ClusterStrategyError(Exception):
    """Unknown or unsupported strategy, or missing required parameter."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
