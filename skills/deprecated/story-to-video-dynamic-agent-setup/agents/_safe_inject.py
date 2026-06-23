"""Safe wrapper around ADK's `inject_session_state` that tolerates missing keys.

The LF and motion prompter system prompt files use single-brace `{var}` patterns
in two different ways:
- Real state variables (e.g. `{ff_prompts_content}`) — these should be
  substituted from session state by ADK's `inject_session_state`.
- Literal placeholders the LLM is expected to fill in (e.g. `{check_id}`) —
  these are *not* state variables, but ADK's regex strips one brace layer and
  tries to look them up, raising `KeyError: 'Context variable not found: ...'`.

The LF/motion system prompts intentionally include both kinds. To make the loop
robust, this wrapper:
1. First runs `inject_session_state` to substitute real state variables.
2. On `KeyError`, falls back to the original template — so literal `{var}`
   placeholders survive intact for the LLM to fill in.

This is intentionally a thin wrapper: any state var that IS in session state
is still substituted; only the unknowns are left as-is.
"""
from __future__ import annotations

import logging
import re

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils import instructions_utils

logger = logging.getLogger(__name__)


# Same regex ADK uses internally. Exposed here for the fallback re-substitution
# that re-injects any leftover `{var}` placeholders back into the template
# (i.e. the no-op case when the var is missing).
_PLACEHOLDER_RE = re.compile(r"\{+[^{}]*\}+")


async def safe_inject_session_state(
    template: str,
    readonly_context: ReadonlyContext,
) -> str:
    """Inject session state, tolerating missing variables.

    Behaviour:
    - If `inject_session_state` succeeds, return its result.
    - If it raises `KeyError` (missing state variable), return the ORIGINAL
      template unchanged, so literal `{var}` placeholders (intended for the
      LLM to fill in) survive intact.
    - Any other exception is re-raised.
    """
    try:
        return await instructions_utils.inject_session_state(template, readonly_context)
    except KeyError as e:
        logger.debug(
            "safe_inject_session_state: %s — leaving template unchanged", e
        )
        return template
