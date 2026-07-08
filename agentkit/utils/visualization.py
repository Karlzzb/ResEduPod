"""Deterministic, local validation for the ``visualize`` text render types.

Ported from ``deeptutor/agents/visualize/utils.py``: cheap render-ability checks
that gate a single targeted repair pass (no LLM call needed to *discover* a
failure).
"""

from __future__ import annotations

import json
import re

import defusedxml.ElementTree as ET

_MERMAID_KEYWORDS = (
    "graph",
    "flowchart",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram-v2",
    "stateDiagram",
    "erDiagram",
    "gantt",
    "mindmap",
    "pie",
    "journey",
    "gitGraph",
    "timeline",
    "quadrantChart",
    "requirementDiagram",
    "sankey-beta",
    "xychart-beta",
    "block-beta",
    "C4Context",
)


def is_valid_html_document(html: str) -> bool:
    if not html:
        return False
    lowered = html.lower()
    return "<html" in lowered or "<!doctype" in lowered or "<body" in lowered or "<div" in lowered


def _strip_outer_fence(text: str) -> str:
    stripped = (text or "").strip()
    match = re.match(r"^```[A-Za-z]*\s*\n?([\s\S]*?)\n?```$", stripped)
    return match.group(1).strip() if match else stripped


def validate_visualization(code: str, render_type: str) -> tuple[bool, str]:
    """Return ``(ok, error)``; ``error`` is a short LLM-actionable repair hint."""
    text = (code or "").strip()
    if not text:
        return False, "Generated code is empty."

    if render_type == "svg":
        if "<svg" not in text.lower():
            return False, "SVG must contain a root <svg> element."
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            return False, f"SVG is not well-formed XML: {exc}"
        tag = root.tag.split("}")[-1].lower()
        if tag != "svg":
            return False, f"Root element must be <svg>, found <{tag}>."
        if "viewBox" not in root.attrib:
            return False, (
                "SVG root is missing a viewBox attribute (must be camelCase "
                "`viewBox`, required for responsive scaling)."
            )
        return True, ""

    if render_type == "chartjs":
        candidate = _strip_outer_fence(text)
        try:
            config = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            return False, (
                "Chart.js config must be strict JSON: double-quoted keys, no "
                "function callbacks, no comments, no trailing commas."
            )
        if not isinstance(config, dict):
            return False, "Chart.js config must be a JSON object."
        missing = [field for field in ("type", "data") if field not in config]
        if missing:
            return False, f"Chart.js config is missing required field(s): {', '.join(missing)}."
        return True, ""

    if render_type == "mermaid":
        first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        if (
            first_line.startswith(_MERMAID_KEYWORDS)
            or first_line.startswith("%%")
            or first_line.startswith("---")
        ):
            return True, ""
        return False, (
            "Mermaid code must start with a valid diagram keyword (graph, "
            "flowchart, sequenceDiagram, classDiagram, stateDiagram-v2, "
            "erDiagram, gantt, mindmap, ...)."
        )

    if render_type == "html":
        if is_valid_html_document(text):
            return True, ""
        return False, "Output does not look like a renderable HTML document."

    return True, ""


def build_fallback_html(*, title: str, summary: str = "", note: str = "") -> str:
    """Minimal self-contained fallback page when the model can't produce valid HTML."""
    safe_title = (title or "Visualization").strip() or "Visualization"
    safe_summary = (summary or "").replace("\n", "<br>") or (
        "The model did not return a renderable HTML document."
    )
    safe_note = (note or "").replace("\n", "<br>")
    note_block = f'<div class="note"><strong>Note:</strong><br>{safe_note}</div>' if safe_note else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{safe_title}</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:linear-gradient(135deg,#F8FAFC 0%,#EFF6FF 100%);
       min-height:100vh;padding:2rem;color:#1E293B;}}
  .card{{max-width:760px;margin:0 auto;background:#fff;border-radius:16px;
        padding:1.75rem 2rem;box-shadow:0 4px 6px -1px rgba(0,0,0,.08);}}
  h1{{color:#1E40AF;font-size:1.4rem;margin-bottom:1rem;}}
  .summary{{line-height:1.7;color:#475569;}}
  .note{{margin-top:1rem;padding:0.9rem 1rem;background:#FEF3C7;
        border-left:4px solid #F59E0B;border-radius:0 8px 8px 0;color:#92400E;}}
</style>
</head>
<body>
  <div class="card">
    <h1>{safe_title}</h1>
    <div class="summary">{safe_summary}</div>
    {note_block}
  </div>
</body>
</html>"""


__all__ = [
    "build_fallback_html",
    "is_valid_html_document",
    "validate_visualization",
]
