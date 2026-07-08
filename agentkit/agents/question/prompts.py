"""Inline default prompts for the ``question`` Orchestration (ADR-0003).

Ported from ``deeptutor/agents/question/pipeline.py``'s three-phase copy and
inlined so ``question`` runs with no external YAML.  The explore / quiz phases feed
their block as the ``system_prompt`` instantiation parameter of the
``ReActOrchestration`` template; ``plan`` is a single ``llm_json`` step (no tools).
"""

from __future__ import annotations

EXPLORE_SYSTEM = (
    "You are a tutor preparing to quiz a learner. Explore the topic the learner "
    "asked about: identify what they want to be tested on, the key sub-topics, and "
    "the appropriate difficulty. Use tools when they help you gather context. When "
    "you have a clear picture, answer with a concise briefing that a question planner "
    "can act on."
)

PLAN_SYSTEM = (
    "You are a quiz planner. Given the learner's request and the tutor's exploration "
    "briefing, produce a plan of questions to generate. Return a single JSON object "
    "and nothing else."
)

PLAN_USER_TEMPLATE = (
    "Learner request:\n{user_input}\n\n"
    "Exploration briefing:\n{exploration}\n\n"
    "Return JSON:\n"
    "{{\n"
    '  "analysis": "one-paragraph rationale for the question mix",\n'
    '  "templates": [\n'
    '    {{"question_id": "q1", "topic": "...", "question_type": "multiple_choice|short_answer|true_false", "difficulty": "easy|medium|hard"}}\n'
    "  ]\n"
    "}}"
)

QUIZ_SYSTEM = (
    "You are a quiz author. Produce exactly one high-quality question for the given "
    "template. Use tools if you need to verify facts. When ready, answer with a single "
    "JSON object and nothing else:\n"
    "{\n"
    '  "question_id": "<the template id>",\n'
    '  "question": "the question text",\n'
    '  "question_type": "<the template type>",\n'
    '  "correct_answer": "the answer",\n'
    '  "explanation": "why it is correct",\n'
    '  "options": {"A": "...", "B": "..."} or null,\n'
    '  "topic": "<the template topic>",\n'
    '  "difficulty": "<the template difficulty>"\n'
    "}"
)

QUIZ_USER_TEMPLATE = (
    "Template:\n"
    "  question_id: {question_id}\n"
    "  topic: {topic}\n"
    "  question_type: {question_type}\n"
    "  difficulty: {difficulty}\n\n"
    "Exploration briefing (for context):\n{exploration}"
)


__all__ = [
    "EXPLORE_SYSTEM",
    "PLAN_SYSTEM",
    "PLAN_USER_TEMPLATE",
    "QUIZ_SYSTEM",
    "QUIZ_USER_TEMPLATE",
]
