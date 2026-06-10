"""Cache key builder.

Constructs the composite metadata used to scope cached responses.  The key
has two parts:

1. **Filter fields** (stored as RediSearch TAG/NUMERIC fields):
   ``tenant_id``, ``sys_prompt_hash``, ``model``, ``temp_bucket``
   — used to narrow ANN search to semantically comparable requests.

2. **Context hash** (stored per-entry, checked after ANN):
   ``ctx_hash`` — SHA-256 of all messages except the last user message,
   used as a second gate to prevent false positive hits when conversation
   history differs.

The *vector* itself (embedding of the last user message) is the ANN search
target and is computed separately by ``EmbeddingEngine``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from src.models.chat import ChatCompletionRequest

_DEFAULT_TEMP_BUCKET = 10  # represents temperature ≈ 1.0


@dataclass(frozen=True)
class CacheKey:
    """Immutable composite cache key extracted from a request."""

    tenant_id: str
    sys_prompt_hash: str
    model: str
    temp_bucket: int
    ctx_hash: str


class CacheKeyBuilder:
    """Builds a :class:`CacheKey` from an incoming chat completion request."""

    def build(self, request: ChatCompletionRequest, tenant_id: str) -> CacheKey:
        """Extract the composite cache key from *request*.

        Parameters
        ----------
        request:
            The validated, OpenAI-compatible chat completion request.
        tenant_id:
            The tenant identifier resolved by the middleware.

        Returns
        -------
        CacheKey
            Immutable key struct ready for Redis filter construction.
        """
        messages = request.messages or []

        # 1. System prompt hash — SHA-256 of all system messages concatenated
        system_texts = [
            m.content or ""
            for m in messages
            if m.role == "system" and isinstance(m.content, str)
        ]
        sys_prompt_hash = _sha256("".join(system_texts))

        # 2. Model name
        model = request.model

        # 3. Temperature bucket: round(temperature * 10)
        #    Null / missing temperature → default bucket 10 (≈ 1.0)
        if request.temperature is not None:
            temp_bucket = round(request.temperature * 10)
        else:
            temp_bucket = _DEFAULT_TEMP_BUCKET

        # 4. Context hash — SHA-256 of full conversation EXCLUDING last user msg
        #    We drop the last message (the current query) so that the hash
        #    represents the conversation "state" up to this point.
        context_messages = _drop_last_user_message(messages)
        ctx_hash = _sha256(_serialize_messages(context_messages))

        return CacheKey(
            tenant_id=tenant_id,
            sys_prompt_hash=sys_prompt_hash,
            model=model,
            temp_bucket=temp_bucket,
            ctx_hash=ctx_hash,
        )

    def last_user_text(self, request: ChatCompletionRequest) -> str:
        """Return the text of the last user-role message in *request*.

        This is the text that gets embedded for ANN search.
        Returns empty string if no user message is found.
        """
        for msg in reversed(request.messages or []):
            if msg.role == "user":
                if isinstance(msg.content, str):
                    return msg.content
                # Multimodal content: join text parts
                if isinstance(msg.content, list):
                    return " ".join(
                        part.get("text", "") if isinstance(part, dict) else str(part)
                        for part in msg.content
                    )
        return ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _serialize_messages(messages) -> str:
    """Stable JSON serialisation of a message list for hashing."""
    return json.dumps(
        [{"role": m.role, "content": m.content} for m in messages],
        sort_keys=True,
        ensure_ascii=False,
    )


def _drop_last_user_message(messages) -> list:
    """Return *messages* with the last user-role message removed."""
    result = list(messages)
    for i in range(len(result) - 1, -1, -1):
        if result[i].role == "user":
            result.pop(i)
            break
    return result
