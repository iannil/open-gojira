"""Prompt loader for v2 LLM Pipelines.

Loads prompt files from app/prompts/ directory structure:
  shared/{name}.md                    — cross-pipeline shared prompts
  {pipeline}/{version}/{name}.md      — pipeline-specific prompts

Versioning: research_reports.prompt_version records which version generated
the report, supporting A/B testing and rollback.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


@lru_cache(maxsize=128)
def _read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_shared(name: str) -> str:
    """Load a shared prompt: app/prompts/shared/{name}.md"""
    path = PROMPTS_DIR / "shared" / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Shared prompt not found: {path}")
    return _read_file(path)


def load_prompt(pipeline: str, name: str, version: str = "v1") -> str:
    """Load a pipeline-specific prompt.

    Args:
        pipeline: deep_research | thesis_tracker | news_pulse | earnings_review | quality_screen
        name: prompt name (without .md extension)
        version: version directory (default v1)
    """
    path = PROMPTS_DIR / pipeline / version / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return _read_file(path)


def build_system_prompt(pipeline: str, version: str = "v1") -> str:
    """Assemble full system prompt for a pipeline run.

    Layout:
      1. shared/system_base.md       — core principles, output contract
      2. shared/defense_methodology.md — 8 red lines, A/B/C grading, inverse test
      3. shared/evidence_grading.md   — evidence strength levels
      4. {pipeline}/{version}/system.md — pipeline-specific instructions (optional)
    """
    parts = [
        load_shared("system_base"),
        load_shared("defense_methodology"),
        load_shared("evidence_grading"),
    ]
    # Optional pipeline-specific system prompt
    pipeline_system_path = PROMPTS_DIR / pipeline / version / "system.md"
    if pipeline_system_path.exists():
        parts.append(_read_file(pipeline_system_path))
    return "\n\n---\n\n".join(parts)


def list_versions(pipeline: str) -> list[str]:
    """List all versions for a pipeline (for A/B testing / rollback)."""
    pipeline_dir = PROMPTS_DIR / pipeline
    if not pipeline_dir.exists():
        return []
    return sorted(
        d.name for d in pipeline_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    )
