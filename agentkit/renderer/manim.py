"""Self-contained Manim rendering service (implements the :class:`Renderer` protocol).

Faithfully ported from ``deeptutor/agents/math_animator/renderer.py``, with one
deliberate change for the hard fork: the DeepTutor global ``path_service``
singleton is replaced by an injected ``render_root`` directory, so the renderer
depends on nothing outside ``agentkit``.  Tests inject a scripted ``FakeRenderer``
instead of launching manim, so this real path is exercised only in live runs.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import re
import subprocess
import sys
import threading
from typing import Awaitable, Callable

from agentkit.models.math_animator import RenderedArtifact, RenderResult

YON_IMAGE_PATTERN = re.compile(
    r"###\s*YON_IMAGE_(\d+)_START\s*###\s*(.*?)\s*###\s*YON_IMAGE_\1_END\s*###",
    re.DOTALL | re.IGNORECASE,
)
SCENE_PATTERN = re.compile(r"class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*.*?Scene.*?\)\s*:")

QUALITY_FLAG_MAP = {"low": "-ql", "medium": "-qm", "high": "-qh"}

_MAX_ERROR_CHARS = 6000


class ManimRenderError(RuntimeError):
    """Raised when Manim rendering fails."""


def _is_non_retriable_environment_error(message: str) -> bool:
    """A missing local LaTeX install can never be fixed by regenerating code."""
    lowered = (message or "").lower()
    return (
        "no such file or directory: 'latex'" in lowered
        or 'no such file or directory: "latex"' in lowered
        or "latex could not be found" in lowered
    )


def _trim_error_message(message: str) -> str:
    text = (message or "").strip()
    if len(text) <= _MAX_ERROR_CHARS:
        return text
    return text[-_MAX_ERROR_CHARS:]


def _slugify_filename(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    return cleaned or fallback


class ManimRenderService:
    """Real manim renderer.  ``render_root`` roots all per-turn working dirs."""

    def __init__(
        self,
        *,
        render_root: str | Path,
        progress_callback: Callable[[str, bool], Awaitable[None]] | None = None,
    ) -> None:
        self.render_root = Path(render_root)
        self.progress_callback = progress_callback

    def supports_vision(self) -> bool:
        # Visual review requires ffmpeg/ffprobe frame extraction, which the
        # tracer bullet does not wire up; keep it off by default.
        return False

    async def render(self, *, code: str, output_mode: str, quality: str, turn_id: str) -> RenderResult:
        base_dir = self.render_root / turn_id
        source_dir = base_dir / "source"
        artifacts_dir = base_dir / "artifacts"
        media_dir = base_dir / "media"
        for path in (source_dir, artifacts_dir, media_dir):
            path.mkdir(parents=True, exist_ok=True)

        await self._emit_progress(f"Preparing {output_mode} render workspace (quality={quality}).")
        source_name = "scene.py" if output_mode == "video" else "scene_image.py"
        source_path = source_dir / source_name
        source_path.write_text(code, encoding="utf-8")

        if output_mode == "image":
            artifacts = await self._render_image_blocks(
                code=code, quality=quality, source_dir=source_dir, media_dir=media_dir,
                artifacts_dir=artifacts_dir,
            )
        else:
            artifacts = [
                await self._render_video(
                    code_path=source_path, quality=quality, media_dir=media_dir,
                    artifacts_dir=artifacts_dir, turn_id=turn_id,
                )
            ]

        return RenderResult(
            output_mode=output_mode,
            artifacts=artifacts,
            source_code_path=str(source_path),
            quality=quality,
        )

    async def _render_video(
        self, *, code_path: Path, quality: str, media_dir: Path, artifacts_dir: Path, turn_id: str
    ) -> RenderedArtifact:
        scene_name = self._extract_scene_name(code_path.read_text(encoding="utf-8"))
        await self._emit_progress(f"Launching Manim scene `{scene_name}`.")
        await self._run_manim(
            code_path=code_path, scene_name=scene_name, quality=quality,
            save_last_frame=False, media_dir=media_dir,
        )
        video_file = self._find_rendered_file(media_dir, ".mp4")
        target_name = _slugify_filename(f"{turn_id}-{scene_name}.mp4", f"{turn_id}.mp4")
        artifact_path = artifacts_dir / target_name
        artifact_path.write_bytes(video_file.read_bytes())
        await self._emit_progress(f"Saved rendered video as {artifact_path.name}.")
        return RenderedArtifact(
            type="video", filename=artifact_path.name, url=f"file://{artifact_path}",
            content_type="video/mp4", label="Animation video",
        )

    async def _render_image_blocks(
        self, *, code: str, quality: str, source_dir: Path, media_dir: Path, artifacts_dir: Path
    ) -> list[RenderedArtifact]:
        matches = list(YON_IMAGE_PATTERN.finditer(code))
        if not matches:
            raise ManimRenderError(
                "Image mode requires code blocks wrapped in ### YON_IMAGE_n_START ### / END ###."
            )
        residual = YON_IMAGE_PATTERN.sub("", code).strip()
        if residual:
            raise ManimRenderError("Image mode code must only contain YON_IMAGE anchor blocks.")

        artifacts: list[RenderedArtifact] = []
        for idx, match in enumerate(matches, start=1):
            block_code = match.group(2).strip()
            block_path = source_dir / f"image_block_{idx:02d}.py"
            block_path.write_text(block_code, encoding="utf-8")
            scene_name = self._extract_scene_name(block_code)
            await self._emit_progress(f"Rendering image block {idx}/{len(matches)} with scene `{scene_name}`.")
            await self._run_manim(
                code_path=block_path, scene_name=scene_name, quality=quality,
                save_last_frame=True, media_dir=media_dir,
            )
            image_file = self._find_rendered_file(media_dir, ".png")
            artifact_path = artifacts_dir / f"image-{idx:02d}.png"
            artifact_path.write_bytes(image_file.read_bytes())
            artifacts.append(
                RenderedArtifact(
                    type="image", filename=artifact_path.name, url=f"file://{artifact_path}",
                    content_type="image/png", label=f"Image {idx}",
                )
            )
        return artifacts

    async def _run_manim(
        self, *, code_path: Path, scene_name: str, quality: str, save_last_frame: bool, media_dir: Path
    ) -> None:
        quality_flag = QUALITY_FLAG_MAP.get(quality, "-qm")
        command = [
            sys.executable, "-m", "manim", quality_flag, str(code_path), scene_name,
            "--media_dir", str(media_dir), "--progress_bar", "none",
        ]
        command.append("-s") if save_last_frame else command.extend(["--format", "mp4"])

        # subprocess.Popen (not asyncio subprocess) keeps Windows SelectorEventLoop
        # compatibility; reader threads + asyncio.Queue preserve streaming output.
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _reader(stream, prefix: str) -> None:
            assert stream is not None
            for raw_line in stream:
                line = raw_line.decode(errors="ignore").strip()
                if line:
                    loop.call_soon_threadsafe(queue.put_nowait, (prefix, line))
            loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=_reader, args=(process.stdout, "stdout"), daemon=True).start()
        threading.Thread(target=_reader, args=(process.stderr, "stderr"), daemon=True).start()

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        streams_open = 2
        while streams_open > 0:
            item = await queue.get()
            if item is None:
                streams_open -= 1
                continue
            prefix, line = item
            (stdout_lines if prefix == "stdout" else stderr_lines).append(line)
            await self._emit_progress(f"[{prefix}] {line}", raw=True)

        return_code = process.wait()
        if return_code != 0:
            raise ManimRenderError(
                _trim_error_message(
                    "\n".join(p for p in ["\n".join(stdout_lines), "\n".join(stderr_lines)] if p)
                )
            )

    async def _emit_progress(self, message: str, raw: bool = False) -> None:
        if self.progress_callback is not None:
            await self.progress_callback(message, raw)

    @staticmethod
    def _find_rendered_file(media_dir: Path, suffix: str) -> Path:
        matches = [
            path for path in media_dir.rglob(f"*{suffix}") if "partial_movie_files" not in path.parts
        ]
        if not matches:
            matches = list(media_dir.rglob(f"*{suffix}"))
        if not matches:
            raise ManimRenderError(f"Rendered {suffix} artifact not found.")
        return max(matches, key=lambda path: path.stat().st_mtime)

    @staticmethod
    def _extract_scene_name(code: str) -> str:
        match = SCENE_PATTERN.search(code)
        if not match:
            raise ManimRenderError("Generated code does not define a renderable Manim Scene class.")
        return match.group(1)


__all__ = [
    "ManimRenderError",
    "ManimRenderService",
    "YON_IMAGE_PATTERN",
    "_is_non_retriable_environment_error",
]
