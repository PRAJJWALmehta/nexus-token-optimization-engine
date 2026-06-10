"""Pruning pipeline orchestrator.

Chains all pruning transforms in the defined order and returns a
:class:`PruningResult` with metadata about what was applied and how
many tokens were saved.

Transform order
---------------
1. :class:`~src.pruning.normalizer.WhitespaceNormalizer`
2. :class:`~src.pruning.comments.CommentStripper`
3. :class:`~src.pruning.dedup.SystemDeduplicator`
4. :class:`~src.pruning.truncation.ConversationTruncator`

Error handling
--------------
Each transform is wrapped in a ``try / except``.  If a transform raises an
unexpected exception, the error is logged at ``ERROR`` level, that transform
is skipped, and the pipeline continues with the remaining transforms.  The
request is **never** blocked by a pruning failure.

Short-circuit per transform
----------------------------
Individual transforms implement their own short-circuit checks (e.g. dedup
skips when ≤ 1 system message).  The pipeline itself additionally skips
disabled transforms before calling into them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.models.chat import ChatCompletionRequest
from src.pruning.comments import CommentStripper
from src.pruning.dedup import SystemDeduplicator
from src.pruning.normalizer import WhitespaceNormalizer
from src.pruning.truncation import ConversationTruncator, _estimate_total_tokens

logger = logging.getLogger(__name__)


@dataclass
class PruningResult:
    """Result returned by :meth:`PruningPipeline.run`."""

    request: ChatCompletionRequest
    """The pruned (or unchanged) request."""

    tokens_before: int
    """Estimated token count before pruning."""

    tokens_after: int
    """Estimated token count after pruning."""

    transforms_applied: list[str] = field(default_factory=list)
    """Names of transforms that were invoked (even if they made no change)."""

    @property
    def tokens_saved(self) -> int:
        """Number of tokens saved (non-negative)."""
        return max(0, self.tokens_before - self.tokens_after)


class PruningPipeline:
    """Orchestrates all pruning transforms in sequence.

    Parameters
    ----------
    normalize_whitespace:
        Enable :class:`~src.pruning.normalizer.WhitespaceNormalizer`.
    strip_comments:
        Enable :class:`~src.pruning.comments.CommentStripper`.
    deduplicate_system:
        Enable :class:`~src.pruning.dedup.SystemDeduplicator`.
    truncate_conversation:
        Enable :class:`~src.pruning.truncation.ConversationTruncator`.
    token_budget:
        Token budget passed to :class:`~src.pruning.truncation.ConversationTruncator`.
    """

    def __init__(
        self,
        *,
        normalize_whitespace: bool = True,
        strip_comments: bool = True,
        deduplicate_system: bool = True,
        truncate_conversation: bool = True,
        token_budget: int = 16000,
    ) -> None:
        self._normalize = normalize_whitespace
        self._strip = strip_comments
        self._dedup = deduplicate_system
        self._truncate = truncate_conversation
        self._budget = token_budget

        self._normalizer = WhitespaceNormalizer()
        self._stripper = CommentStripper()
        self._deduplicator = SystemDeduplicator()
        self._truncator = ConversationTruncator(budget=token_budget)

    def run(
        self,
        request: ChatCompletionRequest,
        *,
        tenant_id: str = "unknown",
    ) -> PruningResult:
        """Run the pruning pipeline on *request*.

        Parameters
        ----------
        request:
            The incoming chat completion request to prune.
        tenant_id:
            Tenant identifier for structured logging.

        Returns
        -------
        PruningResult
            Contains the (possibly pruned) request, token counts, and the
            list of transforms that were applied.
        """
        tokens_before = _estimate_total_tokens(request.messages)
        current = request.model_copy(deep=True)
        applied: list[str] = []

        # 1. Whitespace normalisation
        if self._normalize:
            try:
                current = self._normalizer.transform(current)
                applied.append("whitespace")
            except Exception:
                logger.error(
                    "WhitespaceNormalizer failed for tenant=%s — skipping",
                    tenant_id,
                    exc_info=True,
                )

        # 2. Comment stripping
        if self._strip:
            try:
                current = self._stripper.transform(current)
                applied.append("comments")
            except Exception:
                logger.error(
                    "CommentStripper failed for tenant=%s — skipping",
                    tenant_id,
                    exc_info=True,
                )

        # 3. System deduplication
        if self._dedup:
            try:
                current = self._deduplicator.transform(current)
                applied.append("dedup")
            except Exception:
                logger.error(
                    "SystemDeduplicator failed for tenant=%s — skipping",
                    tenant_id,
                    exc_info=True,
                )

        # 4. Conversation truncation
        if self._truncate:
            try:
                current = self._truncator.transform(current)
                applied.append("truncation")
            except Exception:
                logger.error(
                    "ConversationTruncator failed for tenant=%s — skipping",
                    tenant_id,
                    exc_info=True,
                )

        tokens_after = _estimate_total_tokens(current.messages)
        result = PruningResult(
            request=current,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            transforms_applied=applied,
        )

        logger.info(
            "Pruning complete: tenant=%s transforms=%s tokens_before=%d "
            "tokens_after=%d tokens_saved=%d",
            tenant_id,
            ",".join(applied) or "none",
            tokens_before,
            tokens_after,
            result.tokens_saved,
        )
        return result
