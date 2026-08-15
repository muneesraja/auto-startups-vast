# H3-Chain Director — Tier 0 Series Continuity

How the director maintains canon, threads, and hook cadence across
episodes of a series. This is Tier 0: the layer above any single
episode's clip chain.

---

## `series_state.json` schema

One file per series at `stories/<series>/series_state.json`. It is the
single source of truth the writer prompt reads before drafting any
episode.

```json
{
  "series": "bamboo-the-dino",
  "canon": {
    "cast": [
      { "id": "bamboo", "name": "Bamboo", "appearance_lock": "...",
        "first_episode": 1, "status": "active" }
    ],
    "relationships": [
      { "a": "bamboo", "b": "the-boy", "type": "found-family parent/child" }
    ],
    "world_rules": [
      "The dino is frightened by direct sunlight and hides under furniture."
    ],
    "tone": "loose, playful, present-tense fable",
    "audience_knowledge": "no prior lore assumed; each episode is self-contained"
  },
  "unresolved_threads": [
    { "id": "egg-origin", "opened_episode": 1, "summary": "Where did the basement egg come from?" }
  ],
  "episode_end_states": {
    "1": "boy and dino sit together in the basement, fear melted into friendship",
    "2": "boy and dino laugh together over a warm bottle of milk"
  },
  "episode_loglines": [
    "A baby finds a hatching egg and befriends the tiny dino inside.",
    "The boy helps the sun-shy dino and bottle-feeds it milk."
  ]
}
```

### `cast[]` entries

| Field | Meaning |
|---|---|
| `id` | stable entity id, reused in every episode + asset registry |
| `name` | display name |
| `appearance_lock` | the canonical appearance string; changing it spawns a new asset variant |
| `first_episode` | episode where the character debuted |
| `status` | `active` \| `absent` \| `written-out` |

`appearance_lock` MUST match the `appearance_lock` stored in the asset
registry entry for that entity. They are the same string.

---

## Thread bookkeeping

Every `threads_opened` entry across episodes 1…N-1 must, by the time
episode N is finalized, be in exactly one of three states:

1. **Closed** — listed in episode N's `threads_closed[]` (or an earlier
   episode's). The thread is resolved on screen.
2. **Still open** — present in `series_state.unresolved_threads[]`.
3. **Parked** — explicitly marked `parked` with a one-line reason in the
   sidecar. A parked thread is neither resolved nor forgotten; it is
   intentionally deferred.

No thread may silently vanish. The director audits this before signing
off an episode: `sum(opened in 1..N-1) == closed-by-N + unresolved + parked`.

---

## Hook cadence

Short-form series episodes live or die on retention. The writer prompt
must structure beats to this cadence:

| Beat | Timing |
|---|---|
| Cold-open hook | first ~1.5s of screen time (clip 1, `[Shot 1]`) |
| Re-hook | every ~10s of screen time |
| Payoff | before the cliffhanger, not after |
| Loopable final beat | last 1–2s must restate the hook so a reel loop hits it again |

The cold-open hook is a visual/auditory jolt — the cracking egg, the
dino's "Mama!" — not exposition. Re-hooks are a new question, reversal,
or sight gag. The cliffhanger is a NEW hook, not the payoff.

---

## Episode prose style

Episodes are written as loose, playful, **present-tense** prose — not
screenplay format, not rigid beat sheets. The writer prompt MUST carry
2–3 verbatim excerpts from existing episodes as house-style exemplars.
Use these (from `stories/bamboo-the-dino/`):

> "the boy realises that dino is scared of sun light and helps him get
> used to it. the boy pampering the dino with treats and gentle
> touches."

> "he rushed like a cartoon character into kitchen and started
> searching foor here and there, fridge, shelves, under the sofa for no
> reason."

> "the kid jumps to grab it the dino stands near to it, but the fridge
> was soo in height the kid couldn't reach it."

House rules the excerpts demonstrate: present tense, casual
capitalization tolerated, similes over literalism, physical comedy
described as action not labeled, run-on energy is acceptable. The
writer prompt should instruct: match this voice; do not polish it into
formal screenwriting.

---

## `episode-N.meta.json` sidecar

Each episode has a sidecar at `stories/<series>/episode-N.meta.json`
alongside `episode-N.md`:

```json
{
  "episode": 2,
  "end_state": "boy and dino laugh together over a warm bottle of milk",
  "threads_opened": ["dino-diet"],
  "threads_closed": ["sun-fear"],
  "hook": "the dino hides under a table from the sunlight",
  "beats": [
    "boy walks out of basement; dino hides from sun",
    "boy remembers his own mother via flashback",
    "boy hunts for milk powder like a cartoon",
    "boy climbs a ladder to reach the milk powder",
    "boy mixes warm milk; dino sips; both laugh"
  ],
  "format": "short-form reel",
  "target_runtime_s": 60
}
```

`end_state` here is the **scripted** end state. It is a claim, not yet
ground truth (see below).

---

## Observed vs planned end state

Episode N+1 is written against the **rendered** end state written back
by stage S11 of the previous run — NOT the scripted `end_state` in the
sidecar. Flow:

1. Writer drafts episode N with a scripted `end_state`.
2. The clip chain renders; S11 extracts the actual final-frame state
   from the rendered last clip and writes it back as
   `episode_end_states[N]` in `series_state.json` (overriding the
   scripted claim if they diverge).
3. Episode N+1's writer reads `episode_end_states[N]` from
   `series_state.json` and continues from THAT.

If the render drifted (dino facing the wrong way, prop missing), the
next episode absorbs the drift as canon rather than contradicting the
render. The rendered video is the ground truth.

---

## W4 audit mode

If `stories/<series>/episode-N.md` **already exists** (hand-written or
previously generated), the workflow skips W3 (draft) and runs W4 as an
**audit** instead:

- W4 reads the existing episode prose + its sidecar.
- It checks: thread bookkeeping balances, hook cadence present, cast
  ids match `series_state.canon.cast`, `end_state` matches the last
  beat, no canon violations.
- Output is an audit report (`episode-N.audit.json`), not a rewrite.
  It lists `ok: bool` and a `findings[]` array of issues to fix
  manually or flag for a re-draft.

A missing sidecar in audit mode is itself a finding (W4 cannot verify
threads without it).
