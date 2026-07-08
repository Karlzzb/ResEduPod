"""Context-window budgeting for the ReAct loop (chat robustness, issue #3).

Ported from ``deeptutor/services/llm/context_window.py`` (window resolution) and
the ``_estimate_messages_tokens`` / ``_guard_context_window`` helpers of
``deeptutor/agents/chat/agentic_pipeline.py`` (token estimate + snip policy).

The loop guards *before* each LLM call: when the conversation would overflow the
model's effective window, the oldest ``role=tool`` results are replaced with a
short marker (their content is recoverable by re-calling the tool) until the
estimate fits.  This is the "上下文窗口保护" behaviour of PRD US 25 — long context
is truncated by policy instead of overflowing the provider.

All helpers here are pure (no LLM, no I/O): token counting uses ``tiktoken`` when
installed and falls back to a chars/4 heuristic otherwise, matching the pre-fork
``ChatAgent.count_tokens`` fallback.
"""

from __future__ import annotations

from typing import Any

# Fraction of the effective window we allow the prompt to fill before snipping;
# the remainder is headroom for the completion.  Ported from
# ``agentic_pipeline.CONTEXT_WINDOW_GUARD_RATIO``.
CONTEXT_WINDOW_GUARD_RATIO = 0.9

# Marker substituted for a snipped tool result (recoverable by re-calling the tool).
TOOL_RESULT_SNIP_MARKER = (
    "[earlier tool result snipped to stay within context window; "
    "call the same tool again if the content is still needed]"
)

DEFAULT_CONTEXT_WINDOW_FALLBACK = 16_384
MAX_EFFECTIVE_CONTEXT_WINDOW = 1_000_000
LARGE_CONTEXT_MODEL_DEFAULT = 65_536
KNOWN_LARGE_CONTEXT_MARKERS = (
    "gpt-4.1",
    "gpt-4o",
    "gpt-5",
    "o1",
    "o3",
    "o4",
    "claude",
    "gemini",
    "qwen",
    "deepseek",
    "moonshot",
    "kimi",
)


def coerce_positive_int(value: Any) -> int | None:
    """Parse a positive integer from arbitrary input, else ``None``."""
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def looks_like_large_context_model(model: str) -> bool:
    """Return True when a model family is typically backed by a large window."""
    normalized = (model or "").strip().lower()
    return any(marker in normalized for marker in KNOWN_LARGE_CONTEXT_MARKERS)


def default_context_window_for_model(*, model: str, max_tokens: Any = None) -> int:
    """Return the fallback window used when no explicit model metadata exists."""
    if looks_like_large_context_model(model):
        return LARGE_CONTEXT_MODEL_DEFAULT
    output_limit = coerce_positive_int(max_tokens) or 4096
    return max(DEFAULT_CONTEXT_WINDOW_FALLBACK, output_limit * 4)


def resolve_effective_context_window(
    *,
    context_window: Any = None,
    model: str,
    max_tokens: Any = None,
) -> int:
    """Resolve the bounded history-planning window for the current model."""
    configured = coerce_positive_int(context_window)
    if configured is not None:
        return min(configured, MAX_EFFECTIVE_CONTEXT_WINDOW)
    return min(
        default_context_window_for_model(model=model, max_tokens=max_tokens),
        MAX_EFFECTIVE_CONTEXT_WINDOW,
    )


def count_tokens(text: str) -> int:
    """Estimate the token count of *text*.

    Uses ``tiktoken`` (cl100k_base) when available; otherwise falls back to the
    chars/4 heuristic (the pre-fork ``ChatAgent.count_tokens`` fallback).
    """
    if not text:
        return 0
    try:
        import tiktoken

        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return len(text) // 4


def _message_tokens(message: dict[str, Any]) -> int:
    content = message.get("content")
    if isinstance(content, str):
        return count_tokens(content)
    if isinstance(content, list):
        total = 0
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                total += count_tokens(str(part.get("text") or ""))
        return total
    return 0


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """Sum the estimated token count across a message list."""
    return sum(_message_tokens(message) for message in messages)


def snip_to_context_budget(
    messages: list[dict[str, Any]],
    *,
    context_window: int,
    guard_ratio: float = CONTEXT_WINDOW_GUARD_RATIO,
    marker: str = TOOL_RESULT_SNIP_MARKER,
) -> bool:
    """Snip oldest ``role=tool`` results in place until the estimate fits the budget.

    Returns ``True`` iff at least one message was snipped (so the caller can emit a
    single warning).  Mutates *messages* in place, mirroring the pre-fork
    ``_guard_context_window`` policy: only tool results are dropped (recoverable by
    re-calling the tool); user/assistant/system turns are preserved.
    """
    if context_window <= 0:
        return False
    budget = int(context_window * guard_ratio)
    if estimate_messages_tokens(messages) <= budget:
        return False
    snipped = False
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        if msg.get("content") == marker:
            continue
        msg["content"] = marker
        snipped = True
        if estimate_messages_tokens(messages) <= budget:
            break
    return snipped


__all__ = [
    "CONTEXT_WINDOW_GUARD_RATIO",
    "DEFAULT_CONTEXT_WINDOW_FALLBACK",
    "KNOWN_LARGE_CONTEXT_MARKERS",
    "LARGE_CONTEXT_MODEL_DEFAULT",
    "MAX_EFFECTIVE_CONTEXT_WINDOW",
    "TOOL_RESULT_SNIP_MARKER",
    "coerce_positive_int",
    "count_tokens",
    "default_context_window_for_model",
    "estimate_messages_tokens",
    "looks_like_large_context_model",
    "resolve_effective_context_window",
    "snip_to_context_budget",
]
