"""``FakeDeps`` — scripted, network-free dependencies for behavior tests.

Per the PRD Testing Decisions, orchestrations are driven by a ``FakeDeps`` bundle
(scripted LLM + inline prompts + a fake renderer) so assertions are deterministic
with no network and no external services.  Because :class:`InlinePromptProvider`
returns ``None`` for every key, tests exercise the *real inlined default prompts*
shipped with each Agent — proving the "self-contained" property (user-story 9).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import json
from typing import Any, AsyncIterator

from agentkit.deps import AgentDeps, AgentParams
from agentkit.models.math_animator import RenderedArtifact, RenderResult
from agentkit.renderer.manim import ManimRenderError


@dataclass
class FakeLLM:
    """Scripted LLM.  ``scripts`` maps an agent name to an ordered list of responses.

    Each call to :meth:`stream` / :meth:`complete` pops the next scripted response
    for that agent and records the call in :attr:`calls` (call order is asserted in
    tests).  A response is chunked so ``llm_chunk`` events are emitted.

    A scripted response may be a ``str`` (normal), or an ``Exception`` instance to
    script a **pre-first-chunk provider failure** (issue #3 fallback / salvage): the
    call is recorded, then the exception is raised before any chunk is yielded, so a
    downstream fallback provider is tried instead of the partial output.
    """

    scripts: dict[str, list[Any]]
    calls: list[str] = field(default_factory=list)
    # The messages passed to each call, in order — lets a test assert the context
    # actually sent to the provider was bounded by the context-window guard.
    seen_messages: list[list[dict[str, Any]]] = field(default_factory=list)
    _cursor: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def _next(self, agent: str | None) -> Any:
        key = agent or "?"
        self.calls.append(key)
        bucket = self.scripts.get(key)
        if not bucket:
            raise AssertionError(f"FakeLLM has no scripted response for agent {key!r}")
        idx = self._cursor[key]
        if idx >= len(bucket):
            raise AssertionError(f"FakeLLM ran out of scripted responses for agent {key!r}")
        self._cursor[key] = idx + 1
        return bucket[idx]

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        response_format: dict[str, Any] | None = None,
        model: str | None = None,
        agent: str | None = None,
    ) -> str:
        self.seen_messages.append(list(messages))
        response = self._next(agent)
        if isinstance(response, BaseException):
            raise response
        return response

    async def stream(
        self,
        *,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        response_format: dict[str, Any] | None = None,
        model: str | None = None,
        agent: str | None = None,
    ) -> AsyncIterator[str]:
        self.seen_messages.append(list(messages))
        response = self._next(agent)
        if isinstance(response, BaseException):
            raise response  # scripted provider failure before any output
        # Chunk into a few pieces so streaming (and llm_chunk events) is exercised.
        size = max(1, len(response) // 3 or 1)
        for i in range(0, len(response), size):
            yield response[i : i + size]


class InlinePromptProvider:
    """Never overrides — forces every Agent to use its own inline default prompt."""

    def get(self, *, agent: str, key: str, language: str) -> str | None:
        return None


@dataclass
class StaticAgentConfig:
    temperature: float = 0.0
    max_tokens: int = 1024
    model: str | None = "fake-model"
    context_window: int | None = None

    def params(self, *, agent: str) -> AgentParams:
        return AgentParams(
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            model=self.model,
            context_window=self.context_window,
        )


@dataclass
class FakeRenderer:
    """Scriptable renderer.

    * ``render_fail_times`` — raise a *retryable* :class:`ManimRenderError` this many
      times, then succeed (drives the visible in-graph retry cycle, AC #4).
    * ``crash_times`` — raise a non-``ManimRenderError`` (a killed-subprocess style
      crash) this many times, then succeed (drives the checkpoint-resume path, AC #5).
    * ``latex_missing`` — the render error text names a missing LaTeX install, so the
      router treats it as non-retryable (AC #3).
    """

    render_fail_times: int = 0
    crash_times: int = 0
    latex_missing: bool = False
    supports_vision_flag: bool = False
    calls: int = 0

    def supports_vision(self) -> bool:
        return self.supports_vision_flag

    async def render(
        self, *, code: str, output_mode: str, quality: str, turn_id: str
    ) -> RenderResult:
        self.calls += 1
        if self.calls <= self.crash_times:
            raise RuntimeError(f"renderer subprocess killed (crash {self.calls})")
        if self.calls <= self.crash_times + self.render_fail_times:
            if self.latex_missing:
                raise ManimRenderError("OSError: [Errno 2] No such file or directory: 'latex'")
            raise ManimRenderError(f"NameError: undefined symbol on attempt {self.calls}")
        artifact_type = "image" if output_mode == "image" else "video"
        content_type = "image/png" if output_mode == "image" else "video/mp4"
        return RenderResult(
            output_mode=output_mode,
            artifacts=[
                RenderedArtifact(
                    type=artifact_type,
                    url=f"file:///fake/{turn_id}.{'png' if output_mode == 'image' else 'mp4'}",
                    filename=f"{turn_id}.{'png' if output_mode == 'image' else 'mp4'}",
                    content_type=content_type,
                    label="Fake artifact",
                )
            ],
            source_code_path=f"/fake/{turn_id}/scene.py",
            quality=quality,
        )


# --- canned JSON payloads for the scripted agents ---


def analysis_json() -> str:
    return json.dumps(
        {
            "learning_goal": "Show the unit circle",
            "math_focus": ["sine", "cosine"],
            "visual_targets": ["rotating radius"],
            "narrative_steps": ["draw circle", "sweep angle"],
            "reference_usage": "",
            "output_intent": "short teaching video",
        }
    )


def design_json() -> str:
    return json.dumps(
        {
            "title": "Unit Circle",
            "scene_outline": ["circle", "radius sweep"],
            "visual_style": "clean",
            "animation_notes": ["ease in"],
            "image_plan": [],
            "code_constraints": ["no LaTeX"],
        }
    )


def code_json(marker: str = "v1") -> str:
    code = f"from manim import *\n\nclass UnitCircle(Scene):\n    def construct(self):  # {marker}\n        self.add(Circle())\n"
    return json.dumps({"code": code, "rationale": f"generation {marker}"})


def summary_json() -> str:
    return json.dumps(
        {
            "summary_text": "Here is your unit circle animation.",
            "user_request": "animate the unit circle",
            "generated_output": "video",
            "key_points": ["sine and cosine as projections"],
        }
    )


# --- canned payloads for the deep_research scripted agents ---


def research_worker_json(
    knowledge: str,
    *,
    citations: list[dict[str, str]] | None = None,
    append: list[dict[str, str]] | None = None,
) -> str:
    """A scripted ``research_worker`` output: findings + citations + appended sub-topics.

    ``citations`` items are ``{"source","title","snippet"}``; ``append`` items are
    ``{"title","overview"}`` — the freshly discovered sub-topics the reducer folds
    into the shared work list for the next supervisor round.
    """
    return json.dumps(
        {
            "knowledge": knowledge,
            "citations": citations or [],
            "append": append or [],
        }
    )


def research_report(text: str = "# Research Report\n\nSynthesized findings.") -> str:
    """A scripted ``research_report`` free-text output (the report writer is text, not JSON)."""
    return text


def make_fake_deps(
    *,
    llm_scripts: dict[str, list[Any]] | None = None,
    fallback_scripts: list[dict[str, list[Any]]] | None = None,
    context_window: int | None = None,
    render_fail_times: int = 0,
    crash_times: int = 0,
    latex_missing: bool = False,
) -> AgentDeps:
    """Build an :class:`AgentDeps` wired with scripted fakes.

    ``fallback_scripts`` supplies ordered secondary :class:`FakeLLM` scripts for the
    multi-level provider degradation path (issue #3); each entry becomes one
    ``deps.llm_fallbacks`` client.  ``context_window`` sets the model's effective
    window so the context-window guard can be exercised deterministically.
    """
    renderer = FakeRenderer(
        render_fail_times=render_fail_times, crash_times=crash_times, latex_missing=latex_missing
    )
    fallbacks = tuple(FakeLLM(scripts=scripts) for scripts in (fallback_scripts or []))
    return AgentDeps(
        llm=FakeLLM(scripts=llm_scripts or {}),
        prompts=InlinePromptProvider(),
        config=StaticAgentConfig(context_window=context_window),
        renderer=renderer,
        llm_fallbacks=fallbacks,
    )


__all__ = [
    "FakeLLM",
    "FakeRenderer",
    "InlinePromptProvider",
    "StaticAgentConfig",
    "analysis_json",
    "code_json",
    "design_json",
    "make_fake_deps",
    "research_report",
    "research_worker_json",
    "summary_json",
]
