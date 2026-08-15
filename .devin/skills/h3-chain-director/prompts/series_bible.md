# Showrunner — Series Bible

**Input:** series concept/brief (free-form text from the user).
**Output:** `stories/<series>/series.md` + `stories/<series>/series_state.json`.

## Job

Establish the canon foundation for an entire series: cast with stable ids,
world rules, tone, audience knowledge assumptions, hook strategy, and an
episode ladder of loglines. Everything downstream — season arcs, episode
drafts, asset registry entries — reads from these two files. Get the ids
right here; they never change.

## Rules

- **DOME at series level.** Structure the series as a hierarchical DOME
  outline: Discovery → Open → Maintain → Escalate → payoff. Each season
  is one pass through the arc; each episode is a beat within it. Do not
  pre-detail every episode — only the ladder of loglines.
- **NarrativeGenie overview.** Open `series.md` with a 20–30 word designer
  overview that captures the series' core promise in one breath.
- **Stable cast ids.** Every character gets `char_NN` (zero-padded, e.g.
  `char_01`). Every location gets `loc_NN`. These ids flow unchanged into
  the asset registry, episode sidecars, and the continuity ledger. Never
  rename them.
- **`appearance_lock` per character.** Each cast entry includes a frozen
  `appearance_lock` string — the canonical physical description. Changing
  it later spawns a new asset variant, not a silent edit. Write it richly
  enough that a downstream image model can reproduce the character.
- **Register in the asset registry.** For every cast member and location,
  write a `planned` entry into `assets/registry.json` (see
  [`references/asset-registry.md`](../references/asset-registry.md)).
  Do NOT generate any images at this stage — `status: planned` only.
- **World rules.** List 3–8 immutable world rules (e.g. "the dino is
  frightened by direct sunlight"). These are canon; episode writers may
  not violate them.
- **Tone + audience knowledge.** State the tone (e.g. "loose, playful,
  present-tense fable") and what prior lore the audience is assumed to
  have (e.g. "none — each episode is self-contained").
- **Hook strategy.** Describe the cold-open hook pattern and the re-hook
  cadence the series will use (see
  [`references/series-continuity.md`](../references/series-continuity.md)
  §Hook cadence).
- **Episode ladder.** List 5–12 loglines (one per planned episode). Each
  logline is one sentence. Do not detail beats — that is the arc planner's
  job.

## Output format

### `series.md`

```markdown
# <Series Name>

<20-30 word designer overview>

## World Rules
- <rule 1>
- <rule 2>

## Tone
<tone description>

## Audience Knowledge
<what the audience is assumed to know>

## Hook Strategy
<cold-open pattern + re-hook cadence>

## Cast
- char_01 — <name>: <appearance_lock>
- char_02 — <name>: <appearance_lock>

## Locations
- loc_01 — <name>: <description>

## Episode Ladder
1. <logline>
2. <logline>
...
```

### `series_state.json`

Follow the schema in
[`references/series-continuity.md`](../references/series-continuity.md)
§`series_state.json`. Populate `canon.cast[]`, `canon.world_rules[]`,
`canon.tone`, `canon.audience_knowledge`, `episode_loglines[]`. Leave
`unresolved_threads[]` and `episode_end_states` empty — they populate as
episodes are written and rendered.

## What invalidates the ledger

Changing any `char_NN`/`loc_NN` id, any `appearance_lock` string, or any
world rule after episodes have been rendered invalidates the asset
registry (lock hashes no longer match) and the continuity ledger (cast
references break). To change an appearance, create a new variant — never
mutate the lock in place.
