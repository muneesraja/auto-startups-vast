"""White/black-gutter panel cropping for storyboard album sheets.

Extracted from skills/story-maker/scripts/nodes/storyboard_nodes.py (the proven
reel_v2 crop path) and retargeted to v3's 3 rows x 3 cols grid. Pure PIL logic,
no LLM calls. ``detect_album_panel_bboxes`` finds thin white or black gutters;
when it can't resolve them confidently it falls back to a uniform grid.

v3 grid: 3 rows x 3 cols visually. Each LTX Director session is one row of
3 panels (start, middle, end). Panel order is row-major within the full grid:
index 0..2 = row 1 cols 1..3 (session 1), index 3..5 = row 2 cols 1..3
(session 2), index 6..8 = row 3 cols 1..3 (session 3).
"""

from __future__ import annotations

import os
from typing import Any

from .duration_budget import SCENE_PANELS, ROW_PANELS, SCENE_COLS

# v3 default: 3 rows x 3 cols.
DEFAULT_COLS = SCENE_COLS  # 3
DEFAULT_ROWS = SCENE_PANELS // SCENE_COLS  # 3


def album_grid_shape(panel_count: int, *, cols: int = DEFAULT_COLS) -> tuple[int, int]:
    """Derive album rows x cols from painted panel count (v3: 3 x 3)."""
    count = max(0, int(panel_count))
    cols = max(1, int(cols))
    if count <= 0:
        return 1, cols
    rows = max(1, (count + cols - 1) // cols)
    return rows, cols


def _grid_bbox_row_major(
    panel_index: int, *, cols: int = DEFAULT_COLS, rows: int | None = None,
    panel_count: int | None = None,
) -> dict[str, float]:
    """Deterministic row-major fallback bbox (normalized {x,y,w,h})."""
    if rows is None:
        count = panel_count if panel_count is not None else max(panel_index + 1, 1)
        rows, cols = album_grid_shape(count, cols=cols)
    col = panel_index % cols
    row = panel_index // cols
    w = 1.0 / cols
    h = 1.0 / rows
    return {"x": col * w, "y": row * h, "w": w, "h": h}


def fallback_panel_bboxes(expected: int, *, cols: int = DEFAULT_COLS) -> list[dict[str, float]]:
    """Uniform grid bboxes for ``expected`` panels."""
    rows, cols = album_grid_shape(expected, cols=cols)
    return [_grid_bbox_row_major(i, cols=cols, rows=rows) for i in range(expected)]


def _contiguous_bands(indices: list[int]) -> list[tuple[int, int]]:
    """Collapse sorted indices into inclusive (start, end) runs."""
    if not indices:
        return []
    bands: list[tuple[int, int]] = []
    start = prev = indices[0]
    for idx in indices[1:]:
        if idx == prev + 1:
            prev = idx
            continue
        bands.append((start, prev))
        start = prev = idx
    bands.append((start, prev))
    return bands


def _axis_white_fractions(
    image, *, axis: str, sample_step: int = 8, white_threshold: int = 240,
) -> list[float]:
    """Fraction of near-white samples along each row (axis='y') or column ('x')."""
    return _axis_separator_fractions(
        image, axis=axis, sample_step=sample_step, threshold=white_threshold, bright=True
    )


def _axis_dark_fractions(
    image, *, axis: str, sample_step: int = 8, dark_threshold: int = 40,
) -> list[float]:
    """Fraction of near-black samples along each row (axis='y') or column ('x')."""
    return _axis_separator_fractions(
        image, axis=axis, sample_step=sample_step, threshold=dark_threshold, bright=False
    )


def _axis_separator_fractions(
    image, *, axis: str, sample_step: int = 8, threshold: int = 240, bright: bool = True,
) -> list[float]:
    """Fraction of near-white (bright=True) or near-black (bright=False) samples."""
    width, height = image.size
    pixels = image.load()
    if axis == "y":
        length, cross = height, width
    elif axis == "x":
        length, cross = width, height
    else:
        raise ValueError(f"Unsupported axis: {axis!r}")

    fractions: list[float] = []
    for i in range(length):
        count = 0
        samples = 0
        for j in range(0, cross, sample_step):
            if axis == "y":
                r, g, b = pixels[j, i][:3]
            else:
                r, g, b = pixels[i, j][:3]
            if bright:
                hit = r >= threshold and g >= threshold and b >= threshold
            else:
                hit = r <= threshold and g <= threshold and b <= threshold
            if hit:
                count += 1
            samples += 1
        fractions.append(count / samples if samples else 0.0)
    return fractions


def _select_gutter_bands(
    bands: list[tuple[int, int]], *, expected: int, size: int, cells: int,
    max_thickness: int = 8,
) -> list[tuple[int, int]] | None:
    """Pick exactly ``expected`` thin gutters nearest the uniform grid separators."""
    thin = [(a, b) for a, b in bands if 1 <= (b - a + 1) <= max_thickness]
    if expected <= 0:
        return []
    if len(thin) < expected:
        return None

    targets = [((i + 1) * size / cells) - 0.5 for i in range(expected)]

    def center(band: tuple[int, int]) -> float:
        return (band[0] + band[1]) / 2.0

    remaining = list(thin)
    chosen: list[tuple[int, int]] = []
    for target in targets:
        best_idx = min(range(len(remaining)), key=lambda i: abs(center(remaining[i]) - target))
        chosen.append(remaining.pop(best_idx))
    chosen.sort(key=lambda band: band[0])

    min_gap = max(8, size // (cells * 8))
    for left, right in zip(chosen, chosen[1:]):
        if right[0] - left[1] < min_gap:
            return None
    return chosen


def _cell_edges_from_gutters(
    size: int, gutters: list[tuple[int, int]], *, cells: int,
) -> list[tuple[int, int]] | None:
    """Convert gutter bands into inclusive cell ranges covering [0, size)."""
    if len(gutters) != cells - 1:
        return None
    edges: list[tuple[int, int]] = []
    cursor = 0
    for start, end in gutters:
        if start <= cursor:
            return None
        edges.append((cursor, start - 1))
        cursor = end + 1
    if cursor >= size:
        return None
    edges.append((cursor, size - 1))
    if len(edges) != cells:
        return None
    if any(b < a for a, b in edges):
        return None
    return edges


def detect_album_panel_bboxes(
    image_path: str,
    expected: int,
    *,
    cols: int | None = None,
    rows: int | None = None,
    inset_px: int = 2,
    white_threshold: int = 240,
    white_fraction: float = 0.85,
    dark_threshold: int = 40,
    dark_fraction: float = 0.85,
    max_gutter_thickness: int = 16,
) -> list[dict[str, float]] | None:
    """Detect panel boxes from thin white or black gutters on an album storyboard sheet.

    Returns normalized {x,y,w,h} boxes in row-major order, or None if gutters
    cannot be resolved confidently (caller falls back to a uniform grid).
    """
    from PIL import Image

    if expected <= 0:
        return []
    derived_rows, derived_cols = album_grid_shape(expected, cols=DEFAULT_COLS)
    rows = derived_rows if rows is None else int(rows)
    cols = derived_cols if cols is None else int(cols)
    max_panels = cols * rows
    if expected > max_panels:
        raise ValueError(f"expected={expected} exceeds {rows}x{cols} grid ({max_panels})")

    with Image.open(image_path) as img:
        image = img.convert("RGB")
        width, height = image.size
        row_frac = _axis_white_fractions(image, axis="y", white_threshold=white_threshold)
        col_frac = _axis_white_fractions(image, axis="x", white_threshold=white_threshold)
        row_dark = _axis_dark_fractions(image, axis="y", dark_threshold=dark_threshold)
        col_dark = _axis_dark_fractions(image, axis="x", dark_threshold=dark_threshold)

    row_hits = [
        i for i, (frac, dark) in enumerate(zip(row_frac, row_dark))
        if frac >= white_fraction or dark >= dark_fraction
    ]
    col_hits = [
        i for i, (frac, dark) in enumerate(zip(col_frac, col_dark))
        if frac >= white_fraction or dark >= dark_fraction
    ]
    row_bands = _contiguous_bands(row_hits)
    col_bands = _contiguous_bands(col_hits)

    row_gutters = _select_gutter_bands(
        row_bands, expected=rows - 1, size=height, cells=rows,
        max_thickness=max_gutter_thickness,
    )
    col_gutters = _select_gutter_bands(
        col_bands, expected=cols - 1, size=width, cells=cols,
        max_thickness=max_gutter_thickness,
    )
    if row_gutters is None or col_gutters is None:
        return None

    row_edges = _cell_edges_from_gutters(height, row_gutters, cells=rows)
    col_edges = _cell_edges_from_gutters(width, col_gutters, cells=cols)
    if row_edges is None or col_edges is None:
        return None

    inset = max(0, int(inset_px))
    bboxes: list[dict[str, float]] = []
    for panel_index in range(expected):
        col = panel_index % cols
        row = panel_index // cols
        x0, x1 = col_edges[col]
        y0, y1 = row_edges[row]
        left = x0 + inset
        top = y0 + inset
        right = x1 - inset
        bottom = y1 - inset
        if right <= left or bottom <= top:
            return None
        bboxes.append(
            {
                "x": left / width,
                "y": top / height,
                "w": (right - left + 1) / width,
                "h": (bottom - top + 1) / height,
            }
        )
    return bboxes


def _sanitize_panel_bboxes(bboxes: list[dict]) -> list[dict]:
    """Replace zero-area vision bboxes with grid fallbacks."""
    rows, cols = album_grid_shape(len(bboxes))
    fixed: list[dict] = []
    for idx, bbox in enumerate(bboxes):
        w = float(bbox.get("w", 0))
        h = float(bbox.get("h", 0))
        if w <= 0 or h <= 0:
            fallback = _grid_bbox_row_major(idx, cols=cols, rows=rows)
            print(f"  ⚠️ Panel {idx + 1} bbox invalid ({bbox}) — using grid fallback {fallback}")
            fixed.append(fallback)
        else:
            fixed.append(bbox)
    return fixed


def _normalize_panels(data: dict, expected: int) -> list[dict]:
    """Validate a vision crop-analyzer JSON panel list."""
    panels = data.get("panels")
    if not isinstance(panels, list):
        raise ValueError(f"Crop analyzer JSON missing panels list: {data!r}")
    if len(panels) != expected:
        raise ValueError(f"Crop analyzer returned {len(panels)} panels, expected {expected}")
    normalized: list[dict] = []
    for idx, panel in enumerate(panels):
        if not isinstance(panel, dict):
            raise ValueError(f"Panel {idx} is not an object: {panel!r}")
        try:
            x = float(panel["x"]); y = float(panel["y"])
            w = float(panel["w"]); h = float(panel["h"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid bbox for panel {idx}: {panel!r}") from exc
        normalized.append({"x": x, "y": y, "w": w, "h": h})
    return normalized


def resolve_panel_bboxes(
    image_path: str, expected: int, *, mode: str | None = None, cols: int = DEFAULT_COLS,
) -> tuple[list[dict[str, float]], str]:
    """Resolve panel bboxes. Returns (bboxes, method) where method is
    'gutter' | 'grid'. (v3 has no vision crop mode — Claude authors panels, so
    python gutter/grid is the only path; kept the signature for parity.)"""
    crop_mode = (mode or os.getenv("STORYBOARD_CROP_MODE") or "python").strip().lower()
    if crop_mode not in {"python", "auto"}:
        crop_mode = "python"
    detected = detect_album_panel_bboxes(image_path, expected, cols=cols)
    if detected is not None and len(detected) == expected:
        return detected, "gutter"
    return fallback_panel_bboxes(expected, cols=cols), "grid"


def crop_panel(image_path: str, bbox: dict, out_path: str) -> None:
    """Crop one panel from a sheet image to ``out_path`` (normalized bbox)."""
    from PIL import Image

    with Image.open(image_path) as img:
        width, height = img.size
        left = max(0, int(bbox["x"] * width))
        top = max(0, int(bbox["y"] * height))
        right = min(width, int((bbox["x"] + bbox["w"]) * width))
        bottom = min(height, int((bbox["y"] + bbox["h"]) * height))
        if right <= left or bottom <= top:
            raise ValueError(f"Invalid crop box {bbox} for image {width}x{height}")
        crop = img.crop((left, top, right, bottom))
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        crop.save(out_path)


def _session_panel_id(visual_row: int, visual_col: int) -> str:
    """Map 3×3 visual grid position to panel id.

    Returns a simple row/column id: panel_<row><col> (e.g. panel_11, panel_33).
    """
    return f"panel_{visual_row + 1}{visual_col + 1}"


def crop_storyboard_sheet(
    sheet_path: str,
    out_dir: str,
    *,
    expected: int = SCENE_PANELS,
    cols: int = DEFAULT_COLS,
    panel_id_prefix: str = "panel",
    panel_ids: list[str] | None = None,
    mode: str | None = None,
) -> list[dict[str, Any]]:
    """Crop a storyboard sheet into ``expected`` panel PNGs (row-major).

    Returns a list of ``{panel_id, path, bbox, method}`` in row-major order.
    Panel ids default to row/column ids (panel_11..panel_33) on the 3×3 visual
    grid. Pass an explicit ``panel_ids`` list to override.
    """
    bboxes, method = resolve_panel_bboxes(sheet_path, expected, mode=mode, cols=cols)
    os.makedirs(out_dir, exist_ok=True)
    results: list[dict[str, Any]] = []
    rows, cols_eff = album_grid_shape(expected, cols=cols)
    for idx, bbox in enumerate(bboxes):
        col = idx % cols_eff
        row = idx // cols_eff
        if panel_ids:
            panel_id = panel_ids[idx]
        elif panel_id_prefix == "panel":
            panel_id = _session_panel_id(row, col)
        else:
            panel_id = f"{panel_id_prefix}_{row + 1}{col + 1}"
        out_path = os.path.join(out_dir, f"{panel_id}.png")
        crop_panel(sheet_path, bbox, out_path)
        results.append({"panel_id": panel_id, "path": out_path, "bbox": bbox, "method": method})
    return results