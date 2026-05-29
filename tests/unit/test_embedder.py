"""Tests for src/cache/embedder.py."""

from __future__ import annotations

import numpy as np
import pytest

from src.cache.embedder import EmbeddingEngine, _DIMS


class TestEmbeddingEngine:
    """Unit tests for EmbeddingEngine.

    The all-MiniLM-L6-v2 model is loaded once for the whole test session via
    the module-scoped fixture so the download/load cost is paid only once.
    """

    @pytest.fixture(scope="module")
    def engine(self) -> EmbeddingEngine:
        return EmbeddingEngine()

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def test_engine_loads_successfully(self, engine: EmbeddingEngine) -> None:
        assert not engine.disabled, "EmbeddingEngine should load without error"
        assert engine._model is not None

    # ------------------------------------------------------------------
    # Vector encoding
    # ------------------------------------------------------------------

    def test_encode_returns_correct_dimensionality(self, engine: EmbeddingEngine) -> None:
        vec = engine.encode("explain recursion")
        assert vec.shape == (_DIMS,), f"Expected ({_DIMS},), got {vec.shape}"

    def test_encode_returns_float32(self, engine: EmbeddingEngine) -> None:
        vec = engine.encode("hello world")
        assert vec.dtype == np.float32

    def test_encode_produces_unit_vector(self, engine: EmbeddingEngine) -> None:
        """normalize_embeddings=True should produce a unit-norm vector."""
        vec = engine.encode("test sentence")
        norm = float(np.linalg.norm(vec))
        assert abs(norm - 1.0) < 1e-5, f"Expected unit norm, got {norm}"

    def test_similar_texts_have_high_cosine_similarity(self, engine: EmbeddingEngine) -> None:
        v1 = engine.encode("what is the capital of France")
        v2 = engine.encode("which city is the capital of France")
        similarity = float(np.dot(v1, v2))  # both unit vectors → cosine similarity
        assert similarity > 0.85, f"Expected high similarity, got {similarity:.4f}"

    def test_different_texts_have_lower_similarity(self, engine: EmbeddingEngine) -> None:
        v1 = engine.encode("what is the capital of France")
        v2 = engine.encode("write a merge sort implementation in Python")
        similarity = float(np.dot(v1, v2))
        assert similarity < 0.70, f"Expected lower similarity, got {similarity:.4f}"

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_empty_string_returns_zero_vector(self, engine: EmbeddingEngine) -> None:
        vec = engine.encode("")
        assert np.all(vec == 0.0), "Empty string should return zero vector"

    def test_whitespace_string_returns_zero_vector(self, engine: EmbeddingEngine) -> None:
        vec = engine.encode("   \t\n  ")
        assert np.all(vec == 0.0), "Whitespace-only string should return zero vector"

    # ------------------------------------------------------------------
    # Disabled engine
    # ------------------------------------------------------------------

    def test_disabled_engine_returns_zero_vector(self) -> None:
        engine = EmbeddingEngine.__new__(EmbeddingEngine)
        engine.disabled = True
        engine._model = None
        vec = engine.encode("this should return zeros")
        assert np.all(vec == 0.0)
        assert vec.shape == (_DIMS,)
