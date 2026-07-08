"""Thinking-tag filtering for streamed LLM output (chat robustness, issue #3).

Some providers surface their reasoning inline in the *content* channel wrapped in
``<think>`` / ``<thinking>`` tags instead of a separate ``reasoning_content``
field.  Two helpers keep that scratchpad from leaking into the user-facing answer
(PRD US 25, one of the four ``chat`` robustness behaviours ported onto the
``ReActOrchestration`` template):

* :class:`InlineThinkFilter` splits a *stream* into ``content`` / ``thinking``
  segments at chunk boundaries, holding back a partial trailing tag until the next
  chunk so a tag split across chunks is never mis-emitted;
* :func:`clean_thinking_tags` scrubs a *complete* string (closed blocks, and any
  unclosed trailing block from an interrupted stream) — the final belt-and-braces
  pass before a decision's text becomes ``final_text``.

Both are ported verbatim in behaviour from ``deeptutor/agents/chat/agent_loop.py``
(``InlineThinkFilter``) and ``deeptutor/services/llm/utils.py``
(``clean_thinking_tags``) so filtering matches the pre-fork implementation.
"""

from __future__ import annotations

import re

_THINK_OPEN_RE = re.compile(r"<\s*think(?:ing)?\b[^>]*>", re.IGNORECASE)
_THINK_CLOSE_RE = re.compile(r"<\s*/\s*think(?:ing)?\s*>", re.IGNORECASE)
# Longest partial tag worth holding a chunk for (e.g. "</thinking" + slack).
_TAG_HOLDBACK_CHARS = 24


class InlineThinkFilter:
    """Incremental ``<think>``/``<thinking>`` splitter for streamed content.

    Splitting at streaming time keeps the user-facing content channel clean
    everywhere downstream — the live stream, the parsed decision, and the loop's
    finish detection — in one place.  The raw text (tags included) still rides the
    LLM conversation untouched so the model sees its own scratchpad next turn.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._in_think = False

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        """Consume *chunk*; return ``(kind, text)`` segments, ``kind`` in
        ``{"content", "thinking"}``.  May hold back a partial trailing tag until
        the next chunk (:meth:`flush` releases it at stream end)."""
        self._buffer += chunk
        segments: list[tuple[str, str]] = []
        while True:
            pattern = _THINK_CLOSE_RE if self._in_think else _THINK_OPEN_RE
            match = pattern.search(self._buffer)
            if match is None:
                break
            if match.start() > 0:
                segments.append((self._kind(), self._buffer[: match.start()]))
            self._buffer = self._buffer[match.end() :]
            self._in_think = not self._in_think
        emit_upto = len(self._buffer)
        tag_start = self._buffer.rfind("<")
        if (
            tag_start != -1
            and len(self._buffer) - tag_start <= _TAG_HOLDBACK_CHARS
            and ">" not in self._buffer[tag_start:]
        ):
            emit_upto = tag_start
        if emit_upto > 0:
            segments.append((self._kind(), self._buffer[:emit_upto]))
            self._buffer = self._buffer[emit_upto:]
        return segments

    def flush(self) -> list[tuple[str, str]]:
        """Release whatever is still buffered (the stream ended)."""
        if not self._buffer:
            return []
        segments = [(self._kind(), self._buffer)]
        self._buffer = ""
        return segments

    def _kind(self) -> str:
        return "thinking" if self._in_think else "content"


def clean_thinking_tags(content: str) -> str:
    """Remove ``<think>`` / ``<thinking>`` blocks from a complete string.

    Handles closed blocks, an unclosed trailing block (a stream interrupted after
    reasoning began — never expose that scratchpad), and any orphan closing tag.
    """
    if not content:
        return ""

    closed_pattern = re.compile(
        r"`?<\s*(?P<tag>think(?:ing)?)\b[^>]*>`?.*?`?<\s*/\s*(?P=tag)\s*>`?",
        re.DOTALL | re.IGNORECASE,
    )
    cleaned = re.sub(closed_pattern, "", content)
    unclosed_pattern = re.compile(
        r"`?<\s*think(?:ing)?\b[^>]*>`?.*$",
        re.DOTALL | re.IGNORECASE,
    )
    cleaned = re.sub(unclosed_pattern, "", cleaned)
    cleaned = re.sub(r"`?<\s*/\s*think(?:ing)?\s*>`?", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


__all__ = ["InlineThinkFilter", "clean_thinking_tags"]
