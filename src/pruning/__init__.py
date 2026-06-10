"""Prompt pruning package.

Deterministic, non-ML token reduction pipeline for the Nexus gateway.

Transforms are applied in order:
1. WhitespaceNormalizer  — collapses redundant whitespace outside code blocks
2. CommentStripper       — removes code comments from fenced code blocks
3. SystemDeduplicator    — collapses duplicate system messages
4. ConversationTruncator — trims old messages to fit a token budget

Public API
----------
    from src.pruning import PruningPipeline, PruningResult
"""

from src.pruning.pipeline import PruningPipeline, PruningResult

__all__ = ["PruningPipeline", "PruningResult"]
