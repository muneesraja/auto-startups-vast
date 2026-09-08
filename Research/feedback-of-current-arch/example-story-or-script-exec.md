# Comprehensive Plan for Story Maker V3

The script is already well-suited to the architecture: it has explicit scenes, shot intent, emotional progression, visual restrictions, character introductions, and a strong final image.

The main adaptation is to treat the user script as a **director-authored source document**, not as raw prose that Agent 1 should freely rewrite. Story Maker V3 should extract, normalize, validate, and only expand missing production details.

The script estimates approximately **310 seconds**, or **5 minutes 10 seconds**, while the header says **3 minutes**. This must be resolved before planning.

## 1. Resolve the Duration First

The scene estimates add up approximately as follows:

| Scene | Estimated duration |
|---|---:|
| Scene 1 | 15-20s |
| Scene 2 | 20-25s |
| Scene 3 | 20s |
| Scene 4 | 15-20s |
| Scene 5 | 20-25s |
| Scene 6 | 20s |
| Scene 7 | 15-20s |
| Scene 8 | 15s |
| Scene 9 | 20-25s |
| Scene 10 | 20s |
| Scene 11 | 25-30s |
| Scene 12 | 20s |
| Scene 13 | 25-30s |
| Scene 14 | 15-20s |
| **Approximate total** | **280-310s** |

The script therefore describes a film closer to **4:40-5:10**, not 3 minutes.

Story Maker should support an explicit input mode:

```text
TARGET_DURATION_MODE: preserve_script
TARGET_DURATION: 310
```

or:

```text
TARGET_DURATION_MODE: compress
TARGET_DURATION: 180
```

Recommended behavior:

- `preserve_script`: retain all scenes and shot intent; fit the final duration within a tolerance.
- `compress`: preserve story-critical scenes and beats, but merge or shorten shots.
- `expand`: preserve all required story beats and add visual breathing room where needed.
- `exact`: force the final scene/generation timing to match an exact target.

For this script, I recommend initially using:

```text
target_seconds: 300
duration_mode: compress_lightly
```

That gives enough room to preserve the narrative while trimming roughly 10 seconds.

## 2. Add a Script Intake Layer

The current Agent 1 prompt assumes a high-level story file. This script is more detailed and should enter through a dedicated intake stage.

Add:

```text
Agent 0 — Script Intake / Normalizer
```

Agent 0 should not creatively rewrite the story. It should extract the user's intent into a normalized production brief.

### Agent 0 input

```text
raw_story.md
target_duration
optional user constraints
```

### Agent 0 output

```text
script_intake.md
script_intake.json
```

The normalized document should contain:

```markdown
# Script Intake — KUTTY KARUPU

title: KUTTY KARUPU
episode_id: epi-1
target_duration_seconds: 300
duration_mode: compress_lightly
tone_arc: emotional → lonely → suspenseful → supernatural → heroic → warm
visual_style: cinematic 3D animation
language: English
dialogue_present: false

## User Constraints
- Do not show the girl and wild dogs together before Scene 8.
- Girl must not be visible in Scene 5's extreme-long shot.
- First joint frame is Scene 8.
- Kutty Karupu and the black dog must be visually associated.
- Black dog must be threatening toward wild dogs but gentle toward the girl.
- The ending must show the girl no longer alone.
- Final title card is editorial output, not part of the generated visual sheet.

## Source Scenes
...
```

This layer prevents important instructions from being lost during rewriting.

## 3. Treat Explicit User Instructions as Hard Constraints

The script contains several constraints that must not be treated as ordinary creative suggestions.

Create a constraint classification:

```text
HARD:
  must never be violated

SOFT:
  preserve unless duration or generation limits require adjustment

PREFERENCE:
  may be improved downstream

EDITORIAL:
  should not be rendered into storyboard sheets or video prompts
```

### Hard constraints from this script

```text
H1:
The girl is not visible in Scene 5's extreme-long road shot.

H2:
The girl and brown wild dogs must not share a frame before Scene 8.

H3:
Scene 8 is the first frame where the girl and wild dogs appear together.

H4:
The yellow eyes appear before the black guardian dog is fully revealed.

H5:
The black guardian dog stands between the girl and the brown wild dogs.

H6:
Kutty Karupu appears after the guardian dog is established.

H7:
Kutty Karupu and the black guardian dog must be visually associated.

H8:
The guardian's behavior changes from threatening toward the wild dogs to gentle toward the girl.

H9:
The final trio consists of the girl, Kutty Karupu, and the black guardian dog.

H10:
The final image communicates that the girl is no longer alone.

H11:
The title card must not be painted into the storyboard sheet or used as a visual reference for Minimax.
```

These constraints should be stored in machine-readable form:

```json
{
  "constraints": [
    {
      "id": "H2",
      "type": "co_presence_exclusion",
      "subjects": ["girl", "brown_wild_dogs"],
      "valid_from_scene": "s1",
      "valid_until_scene": "s7",
      "severity": "BLOCKER"
    }
  ]
}
```

Validators and visual QA should explicitly check these constraints.

## 4. Normalize the Story Into Canonical Entities

The story should produce a canonical identity manifest before any downstream agent works.

Recommended output:

```text
story.json
characters.json
locations.json
objects.json
constraints.json
```

### Characters

```yaml
characters:
  - id: char_01
    name: Little Girl
    role: protagonist
    species: human
    age: 6-7
    appearance:
      skin: warm brown
      hair: dark black, slightly unkempt
      wardrobe: simple Tamil village dress
      footwear: barefoot or simple village sandals
      defining_features:
        - small childlike build
        - expressive eyes
        - tear-prone emotional face
    movement_profile:
      early: playful
      middle: hesitant, frightened, crawling
      late: cautious, then trusting

  - id: char_02
    name: Kutty Karupu
    role: supernatural guardian
    species: human deity-like guardian
    age: young boy
    appearance:
      skin: deep brown
      hair: curly black
      forehead: three horizontal vibhuthi lines
      wardrobe: dark dhoti with red details
      ornaments: traditional gold ornaments
      expression: fierce eyes, gentle smile when helping girl

  - id: char_03
    name: Black Guardian Dog
    role: guardian companion
    species: large black dog
    appearance:
      coat: muscular black coat
      eyes: amber-yellow
      forehead: three white vibhuthi lines
      collar: traditional collar
    movement_profile:
      threat_mode: deliberate, dominant, low growl
      gentle_mode: calm, watchful, non-threatening

  - id: char_04
    name: Brown Wild Dog Pack
    role: antagonist group
    species: brown wild dogs
    cardinality: group
    appearance:
      coat: varied brown
      eyes: aggressive
      behavior: coordinated pack approach
```

Important: the wild dogs should probably be represented as a **group entity**, not several independently tracked characters, unless you need individual continuity.

Use:

```text
char_04 = brown_wild_dog_pack
```

rather than:

```text
char_04, char_05, char_06, char_07
```

This reduces identity drift and avoids unnecessary character sheets.

## 5. Normalize Locations

The script visually moves through the same broad village region, but the production system should distinguish locations based on visual geography and lighting.

Recommended locations:

```yaml
locations:
  - id: loc_01
    name: Village House Exterior
    scenes: [s1]
    time: evening
    landmarks:
      - girl_house
      - front_step
      - clay_pot_play_area
      - neighboring_houses
      - village_children_area

  - id: loc_02
    name: Village Exit Road
    scenes: [s2, s3]
    landmarks:
      - receding_village
      - narrow_dirt_road
      - roadside_trees
      - field_edge

  - id: loc_03
    name: Lonely Streetlight Road
    scenes: [s4, s5, s6, s7, s8, s9, s10, s11, s12, s13, s14]
    landmarks:
      - old_streetlight
      - light_pool
      - dark_road
      - tree_line
      - ditch_or_road_edge
```

Scenes 2 and 3 should reuse `loc_02` if the same road is intended. Scenes 4-14 should use the same location lock if the streetlight road is meant to be continuous.

However, changing from evening to deep night is not necessarily a location change. It should be modeled as:

```text
location_id: loc_03
lighting_state:
  - dusk
  - blue_hour
  - night
```

This allows continuity while letting the spatial planner track lighting evolution.

## 6. Normalize Objects

The broken clay pot is a story-critical prop and must have persistent state.

```yaml
objects:
  - id: obj_01
    name: Small Clay Cooking Pot
    role: emotional_trigger
    appearance:
      material: handmade terracotta
      color: muted reddish brown
      scale: small enough for a six-year-old
    states:
      - intact
      - falling
      - broken
      - abandoned_at_house
```

Do not carry the pot into the road scenes unless the script explicitly says the girl takes it. The prop validator should ensure that the broken pot is not accidentally regenerated in later scenes.

Potential environmental assets:

```yaml
  - id: obj_02
    name: Old Yellow Streetlight
    role: location_anchor
    appearance:
      material: aged metal
      light: weak flickering yellow
```

The streetlight may be better modeled as a **landmark**, not a hero prop.

## 7. Revised Agent Pipeline

The pipeline should become:

```text
Agent 0: Script Intake
    ↓
story_intake.md/json
    ↓
Agent 1: Story Normalizer / Developer
    ↓
developed_story.md + story.json
    ↓
Agent 1b: Beat Board
    ↓
beat_board.md/json
    ↓
Agent 2: Scene Writer
    ↓
scenes.md/json
    ↓
Agent 3a: Spatial Planner
    ↓
spatial_plan_sN.md/json
    ↓
Agent 3: Storyboard Planner
    ↓
storyboard_sN.md/json
    ↓
Cross-artifact validation
    ↓
Agent 6: Critique
    ↓
GATE 0
    ↓
Python: Build shared assets
    ↓
Python: Build storyboard sheets
    ↓
Agent 7: Visual QA
    ↓
GATE 1
    ↓
Agent 5: Video Prompter
    ↓
Video prompt validation
    ↓
GATE 2
    ↓
Render manifest approval
    ↓
Python: Sequential Minimax H3 render
    ↓
Media QA
    ↓
Concat
```

The most important addition is the **Cross-artifact validation** stage before critique. Many constraints in this script are not local to one artifact.

## 8. Scene Plan for This Script

The 14 source scenes should remain 14 logical scenes. Do not automatically merge them into five 60-80 second scenes merely because the current architecture uses a 70-second scene budget.

The source scene boundaries are meaningful:

- Scene 1: emotional trigger
- Scene 2: departure
- Scene 3: realization of isolation
- Scene 4: refuge under streetlight
- Scene 5: threat introduction
- Scene 6: threat escalation
- Scene 7: helplessness
- Scene 8: first co-presence
- Scene 9: supernatural reveal
- Scene 10: guardian intervention
- Scene 11: Kutty Karupu reveal
- Scene 12: threat resolution
- Scene 13: trust and rescue
- Scene 14: warm final image

These are closer to **story sequences** than traditional 60-second scenes.

Update the hierarchy:

```text
episode
  └── sequences
        └── scenes
              └── generations
                    └── shots
                          └── panels
```

Recommended grouping:

```text
Sequence 1 — Departure
  s1, s2, s3

Sequence 2 — The Threat
  s4, s5, s6, s7, s8

Sequence 3 — The Guardians
  s9, s10, s11, s12

Sequence 4 — The Rescue
  s13, s14
```

A sequence can contain multiple locations or lighting states. A scene should remain a continuous production unit with one primary location and one coherent spatial state.

## 9. Per-Scene Generation Budget

Every source scene must be split into 5-15 second generations. No generation may exceed 15 seconds.

A useful target is:

```text
generation duration: 10-15 seconds
```

Avoid making every generation exactly 15 seconds. Shorter generations are appropriate for:
- reveal moments
- reaction beats
- handoff points
- exact first co-presence moments
- visual climax shots

### Suggested generation breakdown

| Scene | Source duration | Suggested generations |
|---|---:|---:|
| s1 Broken Pot | 18s | g1 9s, g2 9s |
| s2 Walking Out | 22s | g1 12s, g2 10s |
| s3 Daylight Disappears | 20s | g1 10s, g2 10s |
| s4 Streetlight | 18s | g1 10s, g2 8s |
| s5 Something Is Coming | 23s | g1 12s, g2 11s |
| s6 Walking Becomes Running | 20s | g1 10s, g2 10s |
| s7 Girl Crawls Back | 17s | g1 9s, g2 8s |
| s8 Dogs Enter Frame | 15s | g1 15s |
| s9 Yellow Eyes | 23s | g1 12s, g2 11s |
| s10 Black Guardian Dog | 20s | g1 10s, g2 10s |
| s11 Kutty Karupu Arrives | 28s | g1 14s, g2 14s |
| s12 Guardians | 20s | g1 10s, g2 10s |
| s13 Guardian Becomes Gentle | 28s | g1 14s, g2 14s |
| s14 Three Characters | 18s | g1 9s, g2 9s |

This produces approximately 28 generations. That is manageable and preserves the script's editorial structure.

The exact durations should be generated from shot durations rather than manually rounded afterward.

## 10. Special Handling for Scenes 5-8

Scenes 5-8 contain the most important visibility constraint in the script.

### Scene 5

The first generation should establish the distant pack without the girl:

```text
g1:
  characters_present: [char_04]
  visible_landmarks: [dark_road, road_vanishing_point]
  forbidden_subjects: [char_01]
```

The girl should not be included in the reference image list for that generation if the image model is likely to insert her.

The second generation can cut to the girl hearing the dogs:

```text
g2:
  characters_present: [char_01]
  visible_landmarks: [streetlight, light_pool]
  forbidden_subjects: [char_04]
```

Do not attach a previous sheet that contains both subjects if the sheet generator may leak them into the next panel. Use a controlled reference policy for hard exclusions.

### Scene 6

Maintain separate visual coverage:

```text
g1:
  dog pack only

g2:
  girl only
```

The dog's perspective and the girl's reaction can be intercut editorially, but they must remain separate images until Scene 8.

### Scene 7

Keep:

```text
girl only
dog paws / dog eyes as isolated inserts
```

The dog inserts must not accidentally include the girl's streetlight or body in the same panel.

### Scene 8

This is the first intentional co-presence:

```text
g1:
  girl + wild dog pack
  girl under streetlight
  dogs entering from darkness
  pack stops and looks behind her
```

Add a validator rule:

```text
co_presence(char_01, char_04) is forbidden before s8
co_presence(char_01, char_04) is required in s8
```

## 11. Storyboard Strategy

The storyboard sheet should not simply reproduce every script heading as a panel. It must select **key poses** that Minimax can interpret.

For each generation, use:

```text
6 panels for 8-12 second generations
9 panels for 13-15 second generations
```

### Example: Scene 9, Generation 1

```text
duration: 12s
panel_grid: 3x2
```

Panel progression:

```text
Panel 1:
  empty darkness behind the girl

Panel 2:
  first amber-yellow eye opens

Panel 3:
  second amber-yellow eye opens

Panel 4:
  both eyes remain still in darkness

Panel 5:
  black paw steps into the dirt

Panel 6:
  partial black-dog silhouette emerges
```

The image prompt should describe only visible frozen states. The video prompt should describe:

```text
darkness holds → one eye opens → second eye opens → silence → paw steps forward
```

### Example: Scene 13, Generation 2

```text
Panel 1:
  Kutty Karupu's hand remains extended

Panel 2:
  girl studies his hand

Panel 3:
  girl reaches hesitantly

Panel 4:
  their hands touch

Panel 5:
  Kutty Karupu gently pulls her upright

Panel 6:
  girl stands, still cautious but safe
```

This is more reliable than trying to paint every micro-beat into a single panel.

## 12. Correct the “Action Fidelity” Rule

The current prompts require action words from the storyboard to appear in the image prompt. That is useful, but the script has actions that cannot literally be represented in a still panel:

```text
walking becomes running
eyes open
gradually becomes darker
starts crying
slowly emerges
```

Represent these using two levels:

```yaml
action_contract:
  semantic_action: approach
  visible_pose: wild dogs frozen mid-step, bodies leaning forward
  motion_direction: toward_camera
  intensity: increasing
```

The storyboard sheet prompt should use `visible_pose`. The video prompt should use `semantic_action` and `motion_direction`.

This avoids awkward image prompts such as trying to “paint gradual darkening” as if it were a static object.

## 13. Scene-Specific Spatial Plan

Use the streetlight as the primary anchor for Scenes 4-14:

```yaml
location_ref_id: loc_03
primary_anchor: streetlight_01
world_axis: road extends from deep background toward foreground; streetlight sits on screen-left side of the road
landmarks:
  - streetlight_01
  - light_pool_01
  - road_vanishing_point
  - tree_line_left
  - tree_line_right
  - ditch_edge
```

Suggested zones:

```yaml
zones:
  - zone_id: deep_road
    x_range: [2500, 3600]
    z_range: [25, 80]

  - zone_id: mid_road
    x_range: [1500, 2500]
    z_range: [10, 30]

  - zone_id: light_pool
    x_range: [700, 1700]
    z_range: [2, 12]

  - zone_id: road_edge
    x_range: [300, 900]
    z_range: [0, 12]

  - zone_id: tree_darkness
    x_range: [0, 3840]
    z_range: [20, 100]
```

However, do not use precise pixel placement as if it guarantees visual compliance. Treat the values as coarse continuity signals and have Agent 7 validate broad relationships:

```text
left / center / right
near / middle / far
inside / outside streetlight pool
approaching / retreating
visible / hidden
```

## 14. Character Behavior State Machine

The black guardian dog and Kutty Karupu need state transitions that downstream agents can preserve.

### Black guardian dog

```text
HIDDEN
→ WATCHING
→ REVEALED
→ THREATENING_WILD_DOGS
→ DOMINANT_STANDOFF
→ GUARDING_GIRL
→ GENTLE_COMPANION
```

### Kutty Karupu

```text
ABSENT
→ APPROACHING
→ FIERCE_GUARDIAN
→ THREAT_RESOLVED
→ GENTLE_HELPER
→ COMPANION
```

### Girl

```text
PLAYFUL
→ HURT
→ LONELY
→ FRIGHTENED
→ FROZEN
→ HELPLESS
→ CURIOUS
→ HESITANT
→ TRUSTING
→ SAFE
```

Add these states to the canonical story model. They give Agents 3, 4, 5, and 7 a stable way to reason about emotional and physical continuity.

## 15. Critique Rules for This Story

The generic 214-question bank should be supplemented with story-specific checks.

Create:

```text
assets/story_constraints_epi1.md
```

or:

```text
constraints_epi1.json
```

Additional questions:

```text
K1:
Is the broken pot clearly shown as the cause of the girl's departure?

K2:
Is the girl emotionally alone before the supernatural characters appear?

K3:
Is the girl absent from the Scene 5 extreme-long dog shot?

K4:
Are the girl and wild dogs kept separate through Scene 7?

K5:
Is Scene 8 the first shared frame?

K6:
Are the yellow eyes shown before the black dog is fully visible?

K7:
Is the black dog's vibhuthi and collar readable?

K8:
Is Kutty Karupu's entrance staged after the black dog is established?

K9:
Is the relationship between Kutty Karupu and the black dog unambiguous?

K10:
Does the guardian's threat posture soften before he reaches for the girl?

K11:
Does the girl initiate or visibly accept the hand contact?

K12:
Does the final composition show the girl, Kutty Karupu, and the black dog as a group?

K13:
Does the ending visually resolve the opening loneliness?

K14:
Are the title and subtitle excluded from all generated reference images?
```

These checks should be `BLOCKER` where violation would damage the narrative.

## 16. Fix the Critique Workflow

For this script, Agent 6 should not be allowed to simply mark every plausible item PASS.

Use this process:

```text
1. Run structural validators.
2. Run story-specific constraint validator.
3. Agent 6 evaluates generic directing questions.
4. Agent 6 evaluates story-specific questions.
5. Produce unresolved findings.
6. Agent 1/2/3/3a fixes artifacts.
7. Re-run affected validators.
8. Re-run only affected critique sections plus dependency checks.
9. Freeze an approval snapshot.
```

The critique report should record artifact hashes:

```markdown
artifact_snapshot:
- developed_story.md: sha256:...
- beat_board.md: sha256:...
- scenes.md: sha256:...
- storyboard_s1.md: sha256:...
```

If any dependency changes, the critique report becomes stale automatically.

## 17. Image Asset Generation Plan

### Shared character assets

Generate once:

```text
assets/characters/char_01.webp
assets/characters/char_02.webp
assets/characters/char_03.webp
assets/characters/char_04.webp
```

For the wild dog pack, use a group reference sheet showing:
- three to five brown dogs
- consistent pack color range
- different silhouettes
- no unnecessary individual identity

### Shared location assets

Generate:

```text
assets/locations/loc_01_village_house.webp
assets/locations/loc_02_village_exit_road.webp
assets/locations/loc_03_streetlight_road.webp
```

For `loc_03`, create a clean environment plate with:
- road vanishing point
- streetlight
- light pool
- tree line
- surrounding darkness
- readable left-to-right geography

Do not ask the model for literal 360-degree coverage. Use:

```text
wide establishing environment plate with readable geography and visible anchor landmarks
```

### Prop asset

Generate:

```text
assets/objects/obj_01_clay_pot.webp
```

The broken state may be represented in the storyboard sheet, but the identity reference should primarily establish the intact pot.

## 18. Reference Image Policy

The current reference policy needs special handling for hard exclusions.

### Normal generations

Use:

```text
previous sheet
location lock when needed
character identity sheets
named references
```

### Exclusion-sensitive generations

For Scenes 5-7:

```text
Do not attach character sheets for subjects that must not appear.
Do not attach a previous sheet containing forbidden co-presence.
Use location references only when they do not introduce the forbidden subject.
```

For example, Scene 5's dog-only generation should not receive the girl character sheet unless the model requires it for style consistency.

This is a major practical change. Reference ordering must be **constraint-aware**, not always “attach all scene cast references.”

## 19. Video Prompt Plan

Agent 5 should use two authorities:

```text
storyboard:
  editorial timing, shot order, actions, audio, transitions

rendered sheet:
  actual appearance, composition, visible identity, spatial evidence
```

For each generation:

```text
If the sheet matches the storyboard:
  produce the video prompt.

If the sheet differs in a non-critical way:
  describe the actual sheet while preserving the intended action.

If the sheet violates a hard constraint:
  block video prompt generation and regenerate the sheet.
```

For this episode, never allow Agent 5 to “fix” a missing visual through text alone. If Scene 8's sheet fails to show the girl and dogs together, the generation must be regenerated.

## 20. Transition and Handoff Plan

The existing `scene-end handoff` should carry explicit physical state.

Example:

```markdown
## Scene-end handoff -> scene s5
on_screen: [char_01]
mood: fragile isolation
position: seated beneath streetlight_01 inside light_pool_01
facing: toward deep_road
lighting: yellow streetlight against blue-black night
audio: crying fades into wind and distant night insects
transition: hard_cut
```

For Scene 7:

```markdown
## Scene-end handoff -> scene s8
on_screen: [char_01]
mood: helpless terror
position: fallen near edge of light_pool_01
facing: toward deep_road
wild_dogs_visible: false
audio: approaching paws growing louder
transition: hard_cut
```

For Scene 8:

```markdown
## Scene-end handoff -> scene s9
on_screen: [char_01, char_04]
mood: suspended fear
position: girl in light_pool_01, dogs at edge of frame
facing: girl toward darkness behind her; dogs toward off-screen threat
audio: pack falls silent
transition: match_cut
```

This gives the next generation and scene a concrete continuation state.

## 21. Title Card Handling

The final text:

```text
KUTTY KARUPU
THE LITTLE GUARDIAN
END OF INTRODUCTION
```

should not be included in:
- storyboard sheets
- character sheets
- location sheets
- Minimax reference images
- H3 video prompts

Instead, generate it in post-production using ffmpeg or a separate title-card renderer.

Recommended final sequence:

```text
final scene video
→ 0.5-1.0s hold or fade to black
→ externally rendered title card
→ optional end fade
```

Store it as an editorial artifact:

```text
editorial/title_card.json
editorial/title_card.png
editorial/title_card_spec.md
```

## 22. New Validators Required

Add the following validators.

### Script intake validator

Checks:

```text
title exists
episode exists
target duration exists
source scenes detected
hard constraints extracted
characters detected
locations detected
```

### Constraint validator

Checks:

```text
forbidden co-presence
required co-presence
first-appearance ordering
character reveal ordering
prop state transitions
scene-specific visibility rules
```

### State continuity validator

Checks:

```text
character state transitions are legal
black dog does not become gentle before the threat resolves
Kutty Karupu is absent before his entrance
girl is not safe before rescue
broken pot is not intact later
```

### Generation budget validator

Checks:

```text
every generation is 5-15 seconds
no shot crosses a generation boundary
scene target equals generation sum
generation timestamps are contiguous
```

### Reference policy validator

Checks:

```text
forbidden subjects are not attached as references where prohibited
required identity references are attached when needed
previous-sheet references do not violate exclusion constraints
```

### Final media validator

Checks:

```text
video duration
audio duration
audio channels
sample rate
A/V sync
frame rate
resolution
black-frame anomalies
missing clips
concat order
title-card placement
```

## 23. Recommended File Structure

```text
outputs/story-maker-v3/kutty-karupu/
├── story.json
├── constraints.json
├── run_manifest.json
├── approvals/
│   ├── gate0.json
│   ├── gate1.json
│   └── gate2.json
├── source/
│   └── raw_story.md
├── intake/
│   ├── script_intake.md
│   └── script_intake.json
├── planning/
│   ├── developed_story.md
│   ├── beat_board.md
│   ├── scenes.md
│   ├── characters.json
│   ├── locations.json
│   └── objects.json
├── constraints/
│   ├── story_constraints.md
│   └── story_constraints.json
├── spatial/
│   ├── spatial_plan_s1.md
│   ├── spatial_plan_s2.md
│   └── ...
├── storyboards/
│   ├── storyboard_s1.md
│   ├── storyboard_s2.md
│   └── ...
├── image_prompts/
│   ├── characters/
│   ├── locations/
│   ├── objects/
│   └── sheets/
├── assets/
│   ├── characters/
│   ├── locations/
│   ├── objects/
│   └── asset_registry.json
├── sheets/
│   ├── s1/
│   ├── s2/
│   └── ...
├── qa/
│   ├── critique_report.md
│   ├── constraint_qa_report.md
│   ├── spatial_qa_report.md
│   └── media_qa_report.md
├── video_prompts/
│   ├── s1_g1.txt
│   └── ...
├── render/
│   ├── manifest.json
│   ├── clips/
│   ├── tails/
│   └── jobs/
├── editorial/
│   ├── title_card_spec.md
│   └── title_card.png
└── final/
    ├── scene_s1.mp4
    ├── final_film_without_title.mp4
    └── final_film.mp4
```

## 24. Concrete Changes to the Existing Prompts

### Add to `story_developer.md`

```text
If the input is already a detailed screenplay or scene script:
- preserve explicit scene order and hard constraints;
- do not invent a different plot;
- do not remove named visual restrictions;
- extract the script into normalized story data first;
- identify contradictions between stated target duration and scene estimates;
- ask for or select a duration mode before compressing;
- preserve source scene boundaries unless explicitly instructed otherwise.
```

### Add to `beat_board.md`

```text
Each beat must include:
- source_scene_id
- beat_type
- visible_goal
- obstacle
- stakes
- state_before
- state_after
- required_characters
- forbidden_characters
- required_props
- hard_constraints
```

### Add to `scene_writer.md`

```text
When source scenes are explicit:
- use source scene boundaries as the initial scene boundaries;
- do not force all scenes into 60-80 seconds;
- treat 60-80 seconds as a grouping recommendation only;
- preserve source scene IDs where possible;
- allow scenes between 5 and 80 seconds;
- split only when required by location, continuity, or generation constraints.
```

### Add to `storyboard_planner.md`

```text
Every source-script constraint must be attached to the affected scene,
generation, or shot. Hard constraints take priority over shot variety,
camera preferences, and generic directing questions.
```

### Add to `image_prompter.md`

```text
Reference selection is constraint-aware. Do not attach character references
for subjects that are explicitly forbidden from appearing in the generation,
unless the implementation can guarantee that the reference will not be
rendered into the sheet.
```

### Add to `video_prompter.md`

```text
If the rendered storyboard sheet violates a hard visual constraint, do not
write the video prompt. Return a BLOCKED status with the violated constraint
and regenerate the sheet.
```

## 25. Final Recommended Operating Mode

For this script, the run should execute as follows:

```text
1. Ingest the complete script.
2. Detect that the source is screenplay-like and detailed.
3. Detect the 3-minute versus 280-310-second duration conflict.
4. Select `compress_lightly` with a 300-second target.
5. Extract 14 source scenes.
6. Extract four characters and one hero prop.
7. Create three location locks.
8. Extract hard visibility and reveal constraints.
9. Generate the beat board with source scene references.
10. Generate scenes without collapsing the 14 source scenes.
11. Generate one spatial plan per scene.
12. Split each scene into 5-15 second generations.
13. Create storyboard sheets with only key frozen poses.
14. Run structural, constraint, and spatial QA.
15. Obtain Gate 0 approval.
16. Generate assets and sheets.
17. Enforce Scenes 5-8 visual exclusion rules.
18. Obtain Gate 1 approval.
19. Generate video prompts from approved sheets.
20. Validate dialogue, shot count, timestamps, and spatial language.
21. Obtain Gate 2 approval.
22. Render generations sequentially with tail conditioning.
23. Run media QA.
24. Concatenate scenes.
25. Add the title card externally.
26. Validate the final film.
```

## Core Design Decision

The most important change is this:

> Story Maker V3 must distinguish between **user-authored story intent**, **production planning**, and **model-generated interpretation**.

For `KUTTY KARUPU`:

- The user script owns plot, scene order, reveal order, exclusions, and emotional intent.
- The planning agents own timing, generation boundaries, spatial contracts, panel selection, camera, and sound.
- GPT Image 2 owns the visual realization of each storyboard sheet.
- Minimax H3 owns motion and generated audio within the approved storyboard contract.
- Python owns deterministic execution, state, validation, rendering, and assembly.

That division will allow the skill to handle detailed screenplay inputs without flattening them into generic story plans or losing the constraints that make the script visually specific.