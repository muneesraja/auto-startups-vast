# Production rules (canonical) — story-maker-v5

Single source of truth for the four policies that used to be duplicated across
`SKILL.md`, `story_developer.md`, `storyboard_planner.md`, `image_prompter.md`,
`video_prompter.md`, and `storyboard_sheet_template.md`. Those files cite this
one; edit rules here only.

## 1. Dynamic Shot Depth & Story-First Pacing (MANDATORY)

Before assigning cuts, analyze the scene beats, dialogue, and physical
choreography to determine the natural dramatic pacing. **1 to 8 shots per
generation** (validator-enforced hard limits: `SHOTS_PER_GEN_MIN=1`,
`SHOTS_PER_GEN_MAX=8`).

- **1-Shot Master Take / Oner (typically 10.0s–15.0s):** when the narrative
  beat is a continuous physical sequence (continuous slide down a cavern,
  sovereign entrance, unbroken falling action, high-stakes continuous
  tracking, sustained emotional dialogue), the shot **MUST NOT be cut**.
  Author it as an unbroken single-shot master take filling the whole
  generation. The sheet's panels become *temporal milestones* of the take
  (opening staging → mid-take peak → concluding settle).
- **Asymmetric 2-Shot Dynamic (2 shots / gen):** unequal dramatic division —
  11.5s setup + 3.5s punchy reaction, 9.0s statement + 6.0s rebuttal, etc.
- **Dynamic Action Arc (3 shots / gen):** varying tempo physical sequences —
  6.0s approach + 2.5s impact + 6.5s standoff.
- **Rapid Montage (4+ shots / gen):** reserved strictly for high-tempo
  preparation, chaotic impacts, or rapid flashbacks.
- **Slow-paced / emotional / tension (1–2 shots):** **MANDATORY HIGH
  DETAIL** — the generation must never feel static or boring. `acting_beat:`
  describes multi-phase progression (`initial stillness → breathing catches →
  eyes widen → subtle lip tremor → tear spills → head lowers`), `camera:`
  carries continuous evolving motion (`Push In slow with subtle parallax
  drift`), and `audio:` layers atmospheric sound (room tone, breath, fabric
  shifts). The validator warns when a ≤2-shot generation is under-detailed.
- **STRICT PROHIBITION:** never mechanically slice a generation into equal
  intervals (2×7.5s, 4×3.75s). Never default blindly to 2 shots per
  generation. Vary shot durations organically.

## 2. Multi-Character Prop Staging & Ergonomics (MANDATORY)

When multiple characters eat, drink, or use tools simultaneously:

- **Allocate distinct individual props/vessels** in distinct spatial zones
  ("two bark drinking cups, one squarely in front of each Pookoo"), never
  one shared vessel — shared-vessel staging creates limb distortion and
  merged hands in image/video generation.
- Describe each character interacting with their *own* dedicated prop and
  utensils ("Ollie tips his helmet-cup frame-left; Caloo cradles his bark
  cup frame-right with both paws").
- Distinguish the **serving vessel** (Caloo holding a central waterskin,
  pouring) from the **drinking vessels** (two separate cups on the bank).
- Single shared props are strictly reserved for physical tug-of-war
  conflict beats.

## 3. Dialogue Progression & Anti-Loop Rule

- Dialogue must move forward with every cut. Never repeat the same blame,
  accusation, or question across consecutive shots ("He broke it! / No, he
  broke it!" must not persist once a parent enters).
- **Authority Arrival Pivot:** when an authority figure enters, immediately
  pivot from mutual squabbling to a shared plea, appeal, excuse, or silence,
  letting the newcomer deliver the knowing, witty response that triggers
  the resolution.

## 4. 10-Second Commercial Button Formula (branded stories / ads)

Structure commercial button generations (10.0–15.0s) for brand elegance and
authentic swagger:

- **Shot 1 — Setup & Hook (2.0–3.0s):** characters reacting, smelling food,
  or locking eyes with the hero product.
- **Shot 2 — Authentic Slogan / Maternal Swagger (5.0–7.0s):** the speaker
  delivers the core tagline in natural regional vernacular inside
  `dialogue:`, confident posture, warm lighting.
- **Shot 3 — Sensory Crunch / Brand Button (3.0–5.0s):** close-up on the
  hero product / satisfying crunch, beaming smile, held brand tableau.
