"""Pure scheduling helpers for the ``deep_research`` work list.

These are the parts of the pre-fork ``DynamicTopicQueue`` that survive the fork as
*pure functions over plain block dicts* — dedup and the block-count cap — rather
than methods on a mutable, lock-free shared object.  Keeping them pure is what lets
concurrent workers each compute appends independently and have the ``blocks``
reducer fold the results deterministically (see :mod:`agentkit.state.deep_research`).

Two dedup layers work together:

* :func:`block_id_for` gives every block a **deterministic content-hash id** from
  its normalized title.  Two workers that discover the *same* sub-topic in the same
  superstep therefore mint the *same* ``block_id``, so the reducer collapses them to
  one — the concurrency-safe replacement for the old shared-queue append.
* :func:`find_similar` is the *fuzzy* layer (SequenceMatcher + token Jaccard, a
  faithful port of the pre-fork algorithm) so an LLM can't keep re-proposing the
  same topic in slightly different words within a single worker's view.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from typing import Any

from agentkit.state.deep_research import DEFAULT_SIMILARITY_THRESHOLD

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "of",
        "on",
        "or",
        "the",
        "to",
        "vs",
        "with",
    }
)


def normalize_topic(text: str) -> str:
    """Collapse whitespace + lowercase (pre-fork ``_normalize_topic``)."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def block_id_for(title: str) -> str:
    """A deterministic id from a normalized title, stable across workers/processes.

    Content-addressing the title is what makes the ``blocks`` reducer idempotent
    under concurrent appends: identical sub-topics → identical id → one block.  A
    short blake2b hex is collision-safe for the handful of blocks in a run and keeps
    ids readable in event traces.
    """
    norm = normalize_topic(title)
    digest = hashlib.blake2b(norm.encode("utf-8"), digest_size=6).hexdigest()
    return f"block_{digest}"


def _tokens(text: str) -> set[str]:
    """Stopword-filtered, lightly-stemmed token set (pre-fork ``_topic_tokens``)."""
    tokens: set[str] = set()
    for raw in _TOKEN_RE.findall(normalize_topic(text)):
        token = raw.strip()
        if not token or token in _STOPWORDS:
            continue
        if len(token) > 4 and token.endswith("ies"):
            token = token[:-3] + "y"
        elif len(token) > 3 and token.endswith("s"):
            token = token[:-1]
        tokens.add(token)
    return tokens


def topic_similarity(left: str, right: str) -> float:
    """Blend sequence ratio with token overlap (pre-fork ``_topic_similarity``)."""
    left_norm = normalize_topic(left)
    right_norm = normalize_topic(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0

    sequence_score = difflib.SequenceMatcher(None, left_norm, right_norm).ratio()
    left_tokens = _tokens(left_norm)
    right_tokens = _tokens(right_norm)
    if not left_tokens or not right_tokens:
        return sequence_score

    overlap = left_tokens & right_tokens
    jaccard = len(overlap) / max(1, len(left_tokens | right_tokens))
    containment = len(overlap) / max(1, min(len(left_tokens), len(right_tokens)))
    token_score = jaccard
    if len(left_tokens) >= 2 and len(right_tokens) >= 2 and jaccard >= 0.5:
        token_score = max(token_score, containment * 0.95)
    return max(sequence_score, token_score)


def find_similar(
    title: str,
    existing_titles: list[str],
    *,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> str | None:
    """Return an existing title fuzzily matching ``title``, else ``None``.

    Exact normalized matches win immediately; otherwise the highest-scoring title
    at or above ``threshold`` is returned (pre-fork ``find_similar`` semantics).
    """
    target = normalize_topic(title)
    if not target:
        return None
    best: tuple[float, str] | None = None
    for candidate in existing_titles:
        candidate_norm = normalize_topic(candidate)
        if not candidate_norm:
            continue
        if candidate_norm == target:
            return candidate
        score = topic_similarity(target, candidate_norm)
        if score >= threshold and (best is None or score > best[0]):
            best = (score, candidate)
    return best[1] if best else None


def pending_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The blocks still awaiting research, in list order (pre-fork ``get_all_pending``)."""
    return [b for b in blocks if b.get("status") == "pending"]


__all__ = [
    "block_id_for",
    "find_similar",
    "normalize_topic",
    "pending_blocks",
    "topic_similarity",
]
