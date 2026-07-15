"""Deterministic scene timeline enrichment for story plan shots."""
import json

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from .story_timeline import enrich_story_timeline_with_target


async def timeline_enricher(ctx: Context) -> None:
    raw = ctx.state.get("story_plan_content")
    if not raw:
        print("⚠️ [timeline_enricher] story_plan_content missing, skipping")
        return

    from ._json_util import clean_json_str

    story = clean_json_str(raw) if isinstance(raw, str) else raw
    target = ctx.state.get("target_duration_seconds")
    enriched = enrich_story_timeline_with_target(story, target)
    ctx.state["story_plan_content"] = json.dumps(enriched, indent=2, ensure_ascii=False)
    print("📁 [timeline_enricher] Enriched story timeline in state")


timeline_enricher_node = FunctionNode(
    func=timeline_enricher, name="timeline_enricher_node"
)

# Re-export for tests and callers
from .story_timeline import enrich_story_timeline, enrich_story_timeline_with_target  # noqa: E402,F401
