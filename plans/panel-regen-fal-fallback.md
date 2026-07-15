# Panel regen: Replicate primary → fal fallback

## Goal
Keep shot/panel stills on **Replicate** by default, but when Replicate edit fails (E005 / content policy / provider errors), retry the **same edit job on fal GPT Image 2** with the same resolution/quality and reference images — never bare T2I.

## Defaults
- `PROVIDER=replicate` (chars/locs/default)
- `STORYBOARD_IMAGE_PROVIDER=fal` (album sheets; unchanged)
- `PANEL_IMAGE_PROVIDER` → defaults to `PROVIDER` (replicate)
- `PANEL_IMAGE_FALLBACK_PROVIDER=fal` (new)
- Same still geometry: `PANEL_IMAGE_SIZE=2048x1152`, `REPLICATE_PANEL_QUALITY=low`

## Per-shot ladder
1. **Primary edit** — crop + character sheets on `PANEL_IMAGE_PROVIDER`
2. **Primary safe edit** — softened prompt + crop-only on primary
3. **Fallback edit** (if fallback ≠ primary) — re-upload crop/chars for fal.media URLs, full refs on fal
4. **Fallback safe edit** — crop-only on fal
5. **Last resort** — crop-copy soft-fail (`PANEL_REGEN_ALLOW_SOFT_FAIL=1`) or mark failed

## Persistence
On fal success after primary failure:
- `image_provider: "fal"`
- `fallback_mode: "fal_after_primary_failure"`
- `fallback_reason: <primary error>`

## Non-goals
- Do not add storyboard T2I fallback (already removed)
- Do not change storyboard primary (stays fal)
