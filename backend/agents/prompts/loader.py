"""Shared loader for agent system-prompt files kept as markdown next to this
module instead of inlined as Python string literals.

Same rationale as `utils.version_file.read_version_file`: content that is
large, hand-authored/edited outside the codebase, and unrelated to code
logic belongs in its own file, not in a giant string constant buried in a
class body -- editing the Darius Twin manual (see
`darius_twin_manual.md`) should never require touching
`agents/darius_twin_agent.py`. Cached per filename: prompt files are
static for the life of the running process, same as VERSION.json.

Unlike `read_version_file`, a missing prompt file here is a hard failure
(no silent fallback): an agent silently booting with an empty or
placeholder system prompt is worse than failing to start, especially for
an impersonation agent (see `agents.darius_twin_agent`) where a missing
manual would mean the model free-generating persona and safety rules on
its own.
"""

from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def load_prompt(filename: str) -> str:
    path = _PROMPTS_DIR / filename
    try:
        content = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Agent prompt file not found: {path}. This file is required "
            "content, not optional configuration -- restore it before the "
            "agent that depends on it can run."
        ) from exc
    if not content:
        raise ValueError(f"Agent prompt file is empty: {path}")
    return content
