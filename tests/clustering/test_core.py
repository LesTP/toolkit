"""Tests for toolkit.clustering — cluster function, types, and error paths."""

import numpy as np
import pytest

from toolkit.clustering import (
    ClusterConfig,
    ClusterInputError,
    ClusterLayer,
    ClusterResult,
    ClusterStrategy,
    ClusterStrategyError,
    cluster,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_clusters(n_clusters: int = 3, points_per: int = 20, dims: int = 10):
    """Generate well-separated synthetic clusters."""
    rng = np.random.RandomState(42)
    groups = []
    for i in range(n_clusters):
        center = np.zeros(dims)
        center[i % dims] = 5.0
        groups.append(rng.randn(points_per, dims) * 0.1 + center)
    return np.vstack(groups).astype(np.float32)


# ---------------------------------------------------------------------------
# Basic cluster behavior
# ---------------------------------------------------------------------------


class TestCluster:
    def test_finds_correct_cluster_count(self):
        data = _make_clusters(3)
        result = cluster(data)
        assert result.n_clusters == 3

    def test_labels_shape_matches_input(self):
        data = _make_clusters(3, points_per=15)
        result = cluster(data)
        assert result.labels.shape == (45,)

    def test_labels_are_integers(self):
        data = _make_clusters(2)
        result = cluster(data)
        assert result.labels.dtype == np.int32

    def test_noise_count_non_negative(self):
        data = _make_clusters(2)
        result = cluster(data)
        assert result.n_noise >= 0

    def test_noise_count_matches_labels(self):
        data = _make_clusters(2)
        result = cluster(data)
        assert result.n_noise == int(np.sum(result.labels == -1))

    def test_n_clusters_excludes_noise(self):
        data = _make_clusters(3)
        result = cluster(data)
        unique_labels = set(result.labels)
        expected = len(unique_labels - {-1})
        assert result.n_clusters == expected

    def test_strategy_is_hdbscan(self):
        data = _make_clusters(2)
        result = cluster(data)
        assert result.strategy == "hdbscan"

    def test_tree_is_none_for_hdbscan(self):
        data = _make_clusters(2)
        result = cluster(data)
        assert result.tree is None

    def test_default_config(self):
        data = _make_clusters(2)
        r1 = cluster(data)
        r2 = cluster(data, ClusterConfig())
        np.testing.assert_array_equal(r1.labels, r2.labels)

    def test_deterministic(self):
        data = _make_clusters(3)
        r1 = cluster(data)
        r2 = cluster(data)
        np.testing.assert_array_equal(r1.labels, r2.labels)

    def test_custom_min_cluster_size(self):
        data = _make_clusters(3, points_per=20)
        result = cluster(data, ClusterConfig(min_cluster_size=10))
        assert result.n_clusters >= 1  # larger min_cluster_size still finds clusters

    def test_items_in_same_cluster_are_neighbors(self):
        """Items from the same synthetic group should share a cluster."""
        data = _make_clusters(3, points_per=20)
        result = cluster(data)
        # First 20 points are group 0 — majority should share one label
        group_labels = result.labels[:20]
        most_common = np.bincount(group_labels[group_labels >= 0]).argmax()
        agreement = np.sum(group_labels == most_common)
        assert agreement >= 15  # at least 75% agreement


# ---------------------------------------------------------------------------
# UMAP dimensionality reduction
# ---------------------------------------------------------------------------


def _make_high_dim_clusters(n_clusters=3, points_per=20, dims=384):
    """Generate well-separated clusters in high-dimensional space."""
    rng = np.random.RandomState(42)
    groups = []
    for i in range(n_clusters):
        center = np.zeros(dims)
        center[i % dims] = 5.0
        groups.append(rng.randn(points_per, dims) * 0.1 + center)
    return np.vstack(groups).astype(np.float32)


class TestUMAPReduction:
    def test_reduce_dims_finds_clusters(self):
        data = _make_high_dim_clusters(3)
        result = cluster(data, ClusterConfig(reduce_dims=50))
        assert result.n_clusters == 3

    def test_labels_shape_with_reduction(self):
        data = _make_high_dim_clusters(3, points_per=15)
        result = cluster(data, ClusterConfig(reduce_dims=10))
        assert result.labels.shape == (45,)

    def test_reduce_dims_none_skips_reduction(self):
        """Default reduce_dims=None should not change behavior."""
        data = _make_clusters(3)
        r1 = cluster(data)
        r2 = cluster(data, ClusterConfig(reduce_dims=None))
        np.testing.assert_array_equal(r1.labels, r2.labels)

    def test_noise_handling_with_reduction(self):
        data = _make_high_dim_clusters(2)
        result = cluster(data, ClusterConfig(reduce_dims=20))
        assert result.n_noise == int(np.sum(result.labels == -1))

    def test_tree_still_none_with_reduction(self):
        data = _make_high_dim_clusters(2)
        result = cluster(data, ClusterConfig(reduce_dims=30))
        assert result.tree is None


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestErrors:
    def test_single_row_raises_input_error(self):
        with pytest.raises(ClusterInputError, match="at least 2"):
            cluster(np.array([[1.0, 2.0]]))

    def test_1d_array_raises_input_error(self):
        with pytest.raises(ClusterInputError, match="2-D"):
            cluster(np.array([1.0, 2.0]))

    def test_empty_array_raises_input_error(self):
        with pytest.raises(ClusterInputError):
            cluster(np.empty((0, 10)))

    def test_min_cluster_size_one_raises_value_error(self):
        data = _make_clusters(2)
        with pytest.raises(ValueError, match="min_cluster_size"):
            cluster(data, ClusterConfig(min_cluster_size=1))

    def test_min_samples_zero_raises_value_error(self):
        data = _make_clusters(2)
        with pytest.raises(ValueError, match="min_samples"):
            cluster(data, ClusterConfig(min_samples=0))

    def test_raptor_raises_strategy_error(self):
        data = _make_clusters(2)
        with pytest.raises(ClusterStrategyError, match="not yet implemented"):
            cluster(data, ClusterConfig(strategy=ClusterStrategy.RAPTOR))


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class TestTypes:
    def test_config_defaults(self):
        c = ClusterConfig()
        assert c.strategy == ClusterStrategy.HDBSCAN
        assert c.min_cluster_size == 5
        assert c.min_samples == 3
        assert c.metric == "euclidean"
        assert c.reduce_dims is None
        assert c.raptor_max_depth == 3
        assert c.raptor_summarizer is None

    def test_strategy_enum_values(self):
        assert ClusterStrategy.HDBSCAN.value == "hdbscan"
        assert ClusterStrategy.RAPTOR.value == "raptor"

    def test_result_fields(self):
        r = ClusterResult(
            labels=np.array([0, 1, -1]),
            n_clusters=2,
            n_noise=1,
            strategy="hdbscan",
        )
        assert r.labels.shape == (3,)
        assert r.n_clusters == 2
        assert r.n_noise == 1
        assert r.strategy == "hdbscan"
        assert r.tree is None

    def test_cluster_layer_fields(self):
        layer = ClusterLayer(
            depth=0,
            cluster_ids=[0, 1, 2],
            member_counts={0: 10, 1: 8, 2: 12},
            summaries={0: "topic A", 1: "topic B", 2: "topic C"},
        )
        assert layer.depth == 0
        assert len(layer.cluster_ids) == 3
        assert layer.member_counts[0] == 10
        assert layer.summaries[1] == "topic B"

    def test_input_error_attributes(self):
        e = ClusterInputError("bad input")
        assert e.message == "bad input"
        assert str(e) == "bad input"

    def test_strategy_error_attributes(self):
        e = ClusterStrategyError("unknown")
        assert e.message == "unknown"
        assert str(e) == "unknown"
