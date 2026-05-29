"""Local sentence embedding engine.

Loads the ``all-MiniLM-L6-v2`` model at init and encodes text strings into
384-dimensional float32 vectors for semantic similarity search.

Design notes
------------
- The model is loaded once at construction time and kept in memory for the
  lifetime of the application.
- If loading fails (missing files, OOM, etc.) the engine enters a *disabled*
  state; all encode() calls return zero vectors and callers should treat results
  as cache-misses.
- Empty / whitespace-only strings return a zero vector rather than running the
  model — avoids polluting the vector index with meaningless embeddings.
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_NAME = "all-MiniLM-L6-v2"
_DIMS = 384


class EmbeddingEngine:
    """Wraps ``sentence-transformers`` to produce 384-dim float32 vectors.

    Parameters
    ----------
    model_name:
        HuggingFace model identifier.  Defaults to ``all-MiniLM-L6-v2``.
    """

    def __init__(self, model_name: str = _MODEL_NAME) -> None:
        self.disabled = False
        self._model = None

        try:
            # Lazy import so the rest of the app can start even if
            # sentence-transformers is somehow missing.
            from sentence_transformers import SentenceTransformer  # type: ignore

            logger.info("Loading embedding model '%s'…", model_name)
            self._model = SentenceTransformer(model_name)
            logger.info("Embedding model '%s' loaded successfully.", model_name)
        except Exception as exc:  # pragma: no cover
            logger.error(
                "Failed to load embedding model '%s': %s — caching disabled.",
                model_name,
                exc,
            )
            self.disabled = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encode(self, text: str) -> np.ndarray:
        """Encode *text* into a 384-dimensional float32 vector.

        Returns a zero vector when the engine is disabled or the input is
        empty / whitespace-only.

        Parameters
        ----------
        text:
            The string to embed (typically the last user message).

        Returns
        -------
        np.ndarray
            Shape ``(384,)``, dtype ``float32``.
        """
        if self.disabled or not text or not text.strip():
            return np.zeros(_DIMS, dtype=np.float32)

        try:
            vector = self._model.encode(text, normalize_embeddings=True)
            return np.asarray(vector, dtype=np.float32)
        except Exception as exc:  # pragma: no cover
            logger.error("Embedding encode failed: %s", exc)
            return np.zeros(_DIMS, dtype=np.float32)
