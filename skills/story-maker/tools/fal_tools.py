"""Backward-compatible shim — use grok_tools for provider-aware Grok image gen."""
from .grok_image_common import NO_TEXT_CLAUSE, ensure_no_text
from .grok_tools import generate_grok_edit, generate_grok_t2i

# Legacy alias used by tests
_ensure_no_text = ensure_no_text
