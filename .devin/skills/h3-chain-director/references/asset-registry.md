# H3-Chain Director — Global Asset Registry

The canonical, cross-episode, cross-run registry for character plates,
location locks, and style anchors. Replaces the per-run
`AssetRegistry` with a versioned, approval-gated, repo-root store.

---

## The problem

`skills/story-maker-v3/tools/image_pipeline.py` ships an
`AssetRegistry` class (line 105). It is **per-run**:

- Persisted at `<run_dir>/asset_registry.json`.
- Stores only `{output_path, fal_image_url}` per entity.
- No lock hash, no version history, no approval state.
- No visibility across episodes or runs — each run starts blank and
  re-uploads/re-generates.

Consequences: the same character plate is regenerated every episode,
approved plates cannot be pinned, and a changed `appearance_lock` is
not detected (silent drift across episodes).

---

## The design

A single registry at repo root: `assets/registry.json`, keyed by
`lock_hash = sha256(appearance_lock)`. One entry per entity+variant.
The registry is the source of truth; the pipeline reads from it before
generating anything.

### Directory layout

```
assets/
  registry.json
  <series>/
    characters/<entity>/<variant>/v3.webp
    locations/<entity>/<variant>/v3.webp
  _shared/
    styles/<entity>/<variant>/v3.webp
```

`<series>` is the `series` field from `series_state.json`. `_shared`
holds cross-series assets (off by default — see rules). `<variant>` is
`base` for the first plate, then `v2`, `alt-casual`, etc. Version files
are `v<n>.webp` inside the variant dir.

---

## Registry entry schema

One object per entity+variant in `assets/registry.json`:

```json
{
  "asset_id": "bamboo-the-dino.characters.bamboo.base",
  "kind": "character",
  "series": "bamboo-the-dino",
  "entity_id": "bamboo",
  "variant": "base",
  "appearance_lock": "<full lock string>",
  "lock_hash": "sha256(...)",
  "status": "approved",
  "current": true,
  "versions": [
    { "version": 3, "path": "assets/bamboo-the-dino/characters/bamboo/base/v3.webp",
      "approved_at": "2025-01-12T09:14:00Z", "approved_by": "gate-1" }
  ],
  "usage": [
    { "episode": 1, "run_id": "20250110-abc", "role": "on-screen" }
  ],
  "derived_from": ["bamboo-the-dino.characters.bamboo.base@v2"],
  "shared": false
}
```

| Field | Meaning |
|---|---|
| `asset_id` | `<series>.<kind>.<entity>.<variant>` — the stable handle |
| `kind` | `character` \| `location` \| `style` |
| `status` | `planned` \| `draft` \| `approved` \| `superseded` \| `rejected` |
| `current` | exactly one variant per entity has `current: true` |
| `versions[]` | append-only history; highest `version` is the latest |
| `usage[]` | every episode/run that consumed this asset |
| `derived_from[]` | parent asset_ids this plate was built from (edits, upscaling) |
| `shared` | true only if it lives under `_shared/` and is cross-series |

---

## The 8 rules

1. **Registry-first, always.** Before generating any plate, query the
   registry by `lock_hash`. If an `approved` entry exists, use it. Do
   not generate.
2. **Changed lock = new variant.** If `appearance_lock` differs from
   the current entry's lock, create a new variant (new `asset_id`),
   do not mutate the old one.
3. **Approved = immutable.** An `approved` version's file and lock are
   frozen. To change it, supersede: new variant, old gets
   `status: superseded`, `current: false`.
4. **`--force-regen` must name an asset_id.** Forced regeneration
   targets one entry; it creates a new version under that entry, never
   a blind overwrite.
5. **Reference by `asset_id@version`.** All downstream stages cite
   `bamboo-the-dino.characters.bamboo.base@v3`, never a raw path. The
   registry resolves to the file.
6. **Cross-series off by default.** An asset is `shared: false` and
   lives under `<series>/` unless explicitly promoted to `_shared/`.
   Promotion requires the entry's `series` field to become `_shared`.
7. **GATE 1 reviews draft only.** GATE 1 approval flips `status:
   draft → approved` and stamps `approved_at`/`approved_by`. GATE 1
   never touches `planned` or `superseded` entries.
8. **Atomic writes.** Registry mutations write to
   `assets/registry.json.tmp` then rename. Never partial-write the
   live file.

---

## Adoption — `assetctl index`

`assetctl index` walks `outputs/story-maker-v3/*/assets/**` and
registers existing plates **in place**. Nothing moves; no files are
copied. Per plate:

- `origin: legacy`
- `status: draft`
- `lock_hash` = `sha256` of the lock string found in the run's
  `developed_story.md` (or `null` if no lock is recoverable)
- `.tmp_bak` and `.DS_Store` files are skipped
- `current: true` on the highest-numbered file per entity

After indexing, run `assetctl doctor` to flag entries missing a lock,
duplicates, or plates with no matching registry row.

---

## Pipeline touch points

| Stage | Touch point |
|---|---|
| W1 (plan) | read registry; list required `asset_id`s; mark missing as `planned` |
| W4→S1 (storyboard) | resolve `asset_id@version` → file path for each ref slot |
| S2 (character/location gen) | registry-first; only generate if no `approved` entry; write new `draft` version on output |
| S8 (video prompt) | cite `asset_id@version` in `subject_definitions`, not raw paths |
| GATE 1 | review `draft` entries; flip to `approved`; rejected → `rejected` |
| S11 (end-state writeback) | append to `usage[]` with episode + run_id |
| S13 (finalize) | run `assetctl doctor`; fail the run on unresolved registry errors |

---

## `assetctl` CLI

| Command | Action |
|---|---|
| `assetctl index` | walk legacy outputs, register plates in place (`origin: legacy`, `status: draft`) |
| `assetctl plan <series>` | list `planned` + missing assets required by the latest `series_state.json` |
| `assetctl resolve <asset_id@version>` | print the absolute file path for a reference |
| `assetctl add <kind> <series> <entity> <variant> --lock <file>` | create a new `draft` entry + version |
| `assetctl approve <asset_id>@<version>` | GATE 1: `draft → approved`, stamp audit fields |
| `assetctl supersede <asset_id>` | mark current variant `superseded`, `current: false`; expects a new variant to take `current` |
| `assetctl doctor` | report missing locks, orphan files, duplicate `current`, broken `derived_from` |
| `assetctl usage <asset_id>` | print the `usage[]` log for an asset |
