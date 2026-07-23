"""Deterministic storyboard sheet map from scene_paper.md (no LLM)."""
from __future__ import annotations

import re
from dataclasses import dataclass


_SCENE_RE = re.compile(
    r"^##\s+Scene\s+(\d+[a-z]?)\s*[:\-]?\s*(.*)$",
    re.IGNORECASE | re.MULTILINE,
)
_PANEL_RE = re.compile(r"^###\s+Panel\s+(\d+)\b", re.IGNORECASE | re.MULTILINE)
_DURATION_RE = re.compile(
    r"(?:\*\*)?Duration budget(?:\*\*)?\s*:\s*(?:\*\*)?\s*~?(\d+)\s*s",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class SheetChunk:
    sheet_index: int
    source_scene_label: str
    scene_number: str
    subtitle: str
    duration_budget_seconds: int
    panel_count: int
    panel_start: int
    panel_end: int
    part_index: int
    part_total: int
    source_panel_count: int


def _scene_blocks(scene_paper: str) -> list[tuple[str, str, str]]:
    """Return list of (scene_number, title, body)."""
    matches = list(_SCENE_RE.finditer(scene_paper))
    if not matches:
        return []
    blocks: list[tuple[str, str, str]] = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(scene_paper)
        blocks.append((match.group(1), (match.group(2) or "").strip(), scene_paper[start:end]))
    return blocks


def count_panels(body: str) -> list[int]:
    nums = [int(m.group(1)) for m in _PANEL_RE.finditer(body)]
    return nums


def build_sheet_chunks(
    scene_paper: str,
    *,
    panels_per_sheet: int = 8,
) -> list[SheetChunk]:
    if panels_per_sheet <= 0:
        return []
    chunks: list[SheetChunk] = []
    sheet_index = 0
    for scene_number, title, body in _scene_blocks(scene_paper):
        panel_nums = count_panels(body)
        if not panel_nums:
            continue
        panel_count = len(panel_nums)
        dur_match = _DURATION_RE.search(body)
        duration = int(dur_match.group(1)) if dur_match else max(panel_count, 1)
        sheets_needed = (panel_count + panels_per_sheet - 1) // panels_per_sheet
        for part in range(sheets_needed):
            sheet_index += 1
            start_idx = part * panels_per_sheet
            end_idx = min(start_idx + panels_per_sheet, panel_count)
            part_panels = end_idx - start_idx
            part_duration = max(
                1,
                int(round(duration * (part_panels / panel_count))),
            )
            chunks.append(
                SheetChunk(
                    sheet_index=sheet_index,
                    source_scene_label=f"Scene {scene_number}",
                    scene_number=scene_number,
                    subtitle=title or f"Scene {scene_number}",
                    duration_budget_seconds=part_duration,
                    panel_count=part_panels,
                    panel_start=panel_nums[start_idx],
                    panel_end=panel_nums[end_idx - 1],
                    part_index=part + 1,
                    part_total=sheets_needed,
                    source_panel_count=panel_count,
                )
            )
    return chunks


def render_sheet_map_markdown(
    scene_paper: str,
    *,
    panels_per_sheet: int = 8,
) -> str:
    title_match = _TITLE_RE.search(scene_paper)
    title = (title_match.group(1).strip() if title_match else "Story").removeprefix(
        "Scene Paper:"
    ).strip()
    chunks = build_sheet_chunks(scene_paper, panels_per_sheet=panels_per_sheet)
    lines = [
        f"# Storyboard Sheet Map: {title}",
        "",
        "**Source:** scene_paper.md",
        f"**Panels per sheet (max):** {panels_per_sheet}",
        f"**Total sheets:** {len(chunks)}",
        "",
        "---",
        "",
    ]
    for chunk in chunks:
        lines.extend(
            [
                f"## Sheet {chunk.sheet_index:02d}",
                (
                    f"**Source scene:** {chunk.source_scene_label} "
                    f"(panels {chunk.panel_start}–{chunk.panel_end} of "
                    f"{chunk.source_panel_count}) — part {chunk.part_index}/{chunk.part_total}"
                ),
                f"**Subtitle:** {chunk.subtitle}",
                f"**Duration budget:** {chunk.duration_budget_seconds}s",
                f"**Panel count:** {chunk.panel_count}",
                (
                    f"**Panel range:** Panel {chunk.panel_start:02d} – "
                    f"Panel {chunk.panel_end:02d}"
                ),
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def sheet_map_context_for_prompt(
    scene_paper: str,
    *,
    panels_per_sheet: int = 8,
) -> str:
    """Compact sheet constraints injected into the production plan prompt."""
    chunks = build_sheet_chunks(scene_paper, panels_per_sheet=panels_per_sheet)
    if not chunks:
        return ""
    rows = max(1, (panels_per_sheet + 1) // 2)
    lines = [
        f"Deterministic sheet map (law): exactly {len(chunks)} storyboard scene(s)/sheet(s).",
        (
            f"Each sheet defaults to {panels_per_sheet} panels in a "
            f"{rows}×2 photo-album grid (8:9 page, 16:9 panels)."
        ),
        "",
    ]
    for chunk in chunks:
        lines.append(
            f"- Sheet {chunk.sheet_index:02d} / scene order {chunk.sheet_index}: "
            f"{chunk.subtitle} | panels {chunk.panel_count} | "
            f"budget ~{chunk.duration_budget_seconds}s | "
            f"source {chunk.source_scene_label} part {chunk.part_index}/{chunk.part_total}"
        )
    return "\n".join(lines)
