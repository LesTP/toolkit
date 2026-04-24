"""Tests for toolkit.embedding — embed function, types, and error paths."""

import numpy as np
import pytest

from toolkit.embedding import (
    EmbeddingConfig,
    EmbeddingInputError,
    EmbeddingModelError,
    EmbeddingResult,
    batch_similarity,
    embed,
    similarity,
)


# ---------------------------------------------------------------------------
# Basic embed behavior
# ---------------------------------------------------------------------------


class TestEmbed:
    def test_single_text_shape(self):
        result = embed(["hello world"])
        assert result.vectors.shape == (1, 384)

    def test_multiple_texts_shape(self):
        result = embed(["alpha", "beta", "gamma"])
        assert result.vectors.shape == (3, 384)

    def test_dimension_matches_vectors(self):
        result = embed(["test"])
        assert result.dimension == result.vectors.shape[1]

    def test_model_default(self):
        result = embed(["test"])
        assert result.model == "all-MiniLM-L6-v2"

    def test_model_from_config(self):
        config = EmbeddingConfig(model="all-MiniLM-L6-v2")
        result = embed(["test"], config)
        assert result.model == config.model

    def test_computed_count(self):
        result = embed(["a", "b", "c"])
        assert result.computed == 3
        assert result.from_cache == 0

    def test_l2_normalized(self):
        result = embed(["hello world", "another sentence"])
        norms = np.linalg.norm(result.vectors, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5)

    def test_deterministic(self):
        r1 = embed(["determinism check"])
        r2 = embed(["determinism check"])
        np.testing.assert_array_equal(r1.vectors, r2.vectors)

    def test_empty_string_produces_vector(self):
        result = embed([""])
        assert result.vectors.shape == (1, 384)


# ---------------------------------------------------------------------------
# Batching
# ---------------------------------------------------------------------------


class TestBatching:
    TEXTS = [
        "autonomous agent memory",
        "Zettelkasten slip box",
        "neural network training",
        "raspberry pi deployment",
        "semantic clustering algorithm",
    ]

    def test_batch_size_does_not_affect_output(self):
        r_default = embed(self.TEXTS)
        r_small = embed(self.TEXTS, EmbeddingConfig(batch_size=2))
        np.testing.assert_allclose(
            r_default.vectors, r_small.vectors, atol=1e-6
        )

    def test_batch_size_one(self):
        r_default = embed(self.TEXTS)
        r_one = embed(self.TEXTS, EmbeddingConfig(batch_size=1))
        np.testing.assert_allclose(
            r_default.vectors, r_one.vectors, atol=1e-6
        )


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestErrors:
    def test_empty_list_raises_input_error(self):
        with pytest.raises(EmbeddingInputError, match="non-empty"):
            embed([])

    def test_batch_size_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="batch_size"):
            embed(["test"], EmbeddingConfig(batch_size=0))

    def test_batch_size_negative_raises_value_error(self):
        with pytest.raises(ValueError, match="batch_size"):
            embed(["test"], EmbeddingConfig(batch_size=-1))

    def test_bad_model_raises_model_error(self):
        with pytest.raises(EmbeddingModelError) as exc_info:
            embed(["test"], EmbeddingConfig(model="nonexistent-model-xyz"))
        assert exc_info.value.model == "nonexistent-model-xyz"


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class TestTypes:
    def test_config_defaults(self):
        c = EmbeddingConfig()
        assert c.model == "all-MiniLM-L6-v2"
        assert c.batch_size == 256
        assert c.cache_dir is None
        assert c.device == "cpu"

    def test_result_fields(self):
        r = EmbeddingResult(
            vectors=np.zeros((2, 384)),
            model="test-model",
            dimension=384,
            from_cache=1,
            computed=1,
        )
        assert r.vectors.shape == (2, 384)
        assert r.model == "test-model"
        assert r.dimension == 384
        assert r.from_cache == 1
        assert r.computed == 1

    def test_model_error_attributes(self):
        e = EmbeddingModelError("failed", model="bad-model")
        assert e.model == "bad-model"
        assert str(e) == "failed"

    def test_input_error_attributes(self):
        e = EmbeddingInputError("empty")
        assert e.message == "empty"
        assert str(e) == "empty"


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------


class TestSimilarity:
    def test_identical_vectors(self):
        v = np.array([1.0, 0.0, 0.0])
        assert similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.0, 1.0, 0.0])
        assert similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        a = np.array([1.0, 0.0])
        b = np.array([-1.0, 0.0])
        assert similarity(a, b) == pytest.approx(-1.0)

    def test_returns_float(self):
        a = np.array([0.5, 0.5])
        b = np.array([0.5, 0.5])
        result = similarity(a, b)
        assert isinstance(result, float)

    def test_dimension_mismatch_raises(self):
        a = np.array([1.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        with pytest.raises(ValueError, match="mismatch"):
            similarity(a, b)

    def test_with_real_embeddings(self):
        result = embed(["cat", "dog", "quantum physics"])
        # cat and dog should be more similar than cat and quantum physics
        sim_close = similarity(result.vectors[0], result.vectors[1])
        sim_far = similarity(result.vectors[0], result.vectors[2])
        assert sim_close > sim_far


# ---------------------------------------------------------------------------
# Batch similarity
# ---------------------------------------------------------------------------


class TestBatchSimilarity:
    def test_sorted_descending(self):
        query = np.array([1.0, 0.0, 0.0])
        candidates = np.array([
            [0.0, 1.0, 0.0],  # orthogonal
            [1.0, 0.0, 0.0],  # identical
            [0.5, 0.5, 0.0],  # partial
        ])
        results = batch_similarity(query, candidates)
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    def test_top_k(self):
        query = np.array([1.0, 0.0])
        candidates = np.array([
            [1.0, 0.0],
            [0.5, 0.5],
            [0.0, 1.0],
        ])
        results = batch_similarity(query, candidates, top_k=2)
        assert len(results) == 2

    def test_top_k_none_returns_all(self):
        query = np.array([1.0, 0.0])
        candidates = np.array([
            [1.0, 0.0],
            [0.5, 0.5],
            [0.0, 1.0],
        ])
        results = batch_similarity(query, candidates, top_k=None)
        assert len(results) == 3

    def test_returns_index_score_tuples(self):
        query = np.array([1.0, 0.0])
        candidates = np.array([[1.0, 0.0], [0.0, 1.0]])
        results = batch_similarity(query, candidates)
        for idx, score in results:
            assert isinstance(idx, int)
            assert isinstance(score, float)

    def test_best_match_index(self):
        query = np.array([1.0, 0.0])
        candidates = np.array([
            [0.0, 1.0],  # index 0: orthogonal
            [1.0, 0.0],  # index 1: identical
        ])
        results = batch_similarity(query, candidates)
        assert results[0][0] == 1  # best match is index 1

    def test_dimension_mismatch_raises(self):
        query = np.array([1.0, 0.0])
        candidates = np.array([[1.0, 0.0, 0.0]])
        with pytest.raises(ValueError, match="mismatch"):
            batch_similarity(query, candidates)
