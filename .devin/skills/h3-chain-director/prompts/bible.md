# Bible Keeper — Continuity Bible

**Input:** `<run_dir>/story.md` + global asset registry
(`assets/registry.json`).
**Output:** `<run_dir>/bible.json`.

## Job

Lock appearance strings, wardrobe, label assignments (`<Subject N>`), and
anti-bleed text for every character, location, and item in the treatment.
Resolve every cast id to a concrete `asset_id@version` from the registry.
This is the single source of truth the cutter, sheet author, and prompt
writer all read.

## Rules

- **SCORE static entity state.** For each item/prop in the treatment,
  record its initial state (`active`/`lost`/`destroyed`), `held_by`
  (cast id or null), and `since_clip` (0 at the start). The cutter
  updates this per clip; the bible establishes the baseline.
- **Registry-first, always.** Before planning any new asset, query the
  registry by `lock_hash = sha256(appearance_lock)`. If an `approved`
  entry exists, use its `asset_id@version` — do NOT generate. See
  [`references/asset-registry.md`](../references/asset-registry.md).
- **Resolve every cast id.** Each `char_NN` in `story.md` must resolve
  to `asset_id@version` from the registry. If no entry exists, register
  a `planned` entry (do not generate images here — that happens at the
  storyboard stage).
- **Lock mismatch = hard error.** If the `appearance_lock` in `story.md`
  differs from the registry entry's lock, this is a hard error. Emit:
  `"lock_mismatch": {"cast_id": "char_01", "registry_lock": "...",
  "story_lock": "...", "prompt": "create variant?"}`. Do NOT silently
  pick one. The user must approve a new variant.
- **Label assignment.** Assign `<Subject N>` labels in order of first
  appearance in the treatment. One label per character; locations get
  `<Subject N>` too if they are tracked visually. These labels flow
  unchanged into the prompt prefix and every clip prompt.
- **Anti-bleed text.** For each character, write a one-clause anti-bleed
  string that pins their distinct features against other cast members.
  Used by the prompt writer when ≥2 cast share a frame. See
  [`references/prompt-craft.md`](../references/prompt-craft.md)
  §Anti-bleed text.
- **Wardrobe per arc/clip.** If wardrobe changes across the episode,
  note the per-clip wardrobe. Default: one wardrobe for the whole
  episode.

## Output format

```json
{
  "cast": [
    {"id": "char_01", "label": "<Subject 1>", "name": "...",
     "appearance_lock": "...", "wardrobe": "...",
     "asset_ref": "bamboo-the-dino.characters.bamboo.base@v3",
     "anti_bleed": "<distinctive features vs other cast>"}
  ],
  "locations": [
    {"id": "loc_01", "label": "<Subject 3>", "name": "...",
     "description": "...", "light": "...", "props": [...],
     "asset_ref": "bamboo-the-dino.locations.basement.base@v1"}
  ],
  "items": [
    {"id": "item_01", "name": "glowing egg", "state": "active",
     "held_by": null, "since_clip": 0}
  ],
  "label_map": {
    "<Subject 1>": "char_01",
    "<Subject 2>": "char_02",
    "<Subject 3>": "loc_01"
  },
  "lock_mismatches": []
}
```

## What invalidates the ledger

Changing any `appearance_lock`, `asset_ref`, or `<Subject N>` label
assignment after the cutter has built the clip grid breaks every
downstream prompt's `subject_definitions` and `retention_analysis`. A
`lock_mismatch` that is silently resolved (picking one lock without
creating a registry variant) causes silent identity drift across all
clips — the rendered character will not match the registry plate.
