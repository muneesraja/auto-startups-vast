Yes. The prompts are thoughtfully structured, but there are several architecture-level contradictions that will create invalid artifacts, unnecessary revision loops, or misleading quality gates.

## Highest-risk Issues

### 1. Scene duration rules conflict with short-form targets

`scene_writer.md` requires:

> `N = ceil(target_seconds / 70)`  
> each scene is approximately `60-80s`

But the system also supports 30-second ads and very short stories.

For a 30-second target:

```text
ceil(30 / 70) = 1 scene
scene target must be ~60-80s
```

That makes it impossible to satisfy the 30-second target and the scene-duration rule simultaneously.

Change to a duration-aware policy:

```text
target <= 45s:
  one scene, exact target duration

target <= 90s:
  one or two scenes, each 30-70s

target > 90s:
  ceil(target / 70) scenes
```

More generally, let the planner optimize scene count subject to:

```text
minimum_scene_seconds <= scene_duration <= maximum_scene_seconds
```

rather than hard-coding 70 seconds.

---

### 2. The “one location per scene” rule conflicts with visual storytelling

Both `scene_writer.md` and `directing-questions.md` strongly enforce:

> one location per scene

That is reasonable for spatial continuity, but it prevents:
- cross-cutting
- parallel action
- cutaways to another location
- establishing a new location before the next scene
- visual contrast sequences

The directing guide explicitly mentions cross-cutting:

> “plan as alternating generations”

But generations are also described as continuous renders within one scene and one location.

You need to choose one of these models:

```text
Option A: one location per scene, no cross-location cross-cutting
Option B: one location per sequence, scenes may contain location sub-blocks
Option C: allow `location_id` per generation rather than per scene
```

For this architecture, Option A is the safest. Then remove or downgrade questions such as:
- Q5.9 cross-cutting
- Q5.10 cutaways outside the main action
- Q5.14 smash cuts where they imply a location change
- Q5.17 scene-boundary audio bridges as a requirement

They should be genre-dependent advisories, not universal expectations.

---

### 3. The critique gate is currently self-certifying

`critique_agent.md` says:

> “Be decisive — if the artifact plausibly satisfies the question, mark PASS.”

Then GATE 0 requires zero FAILs.

This creates a strong incentive to mark borderline cases as PASS. The agent can technically satisfy the validator without improving the artifacts.

More importantly, the prompt says:

> “The director agent fixes the flagged artifacts”

but no explicit ownership or revision policy exists for each artifact type.

Improve this with:

```text
Status: BLOCKER | MAJOR | MINOR | ADVISORY
Disposition: ACCEPTED | FIX_REQUIRED | WAIVED
Owner: Agent 1 | Agent 2 | Agent 3 | Agent 3a | User
Evidence:
```

Then distinguish:

```text
structural_pass
creative_review
human_approval
```

Do not let “zero FAILs in an LLM-generated critique report” alone represent creative approval.

A stronger gate would be:

```text
GATE 0:
- all structural validators pass
- no unresolved BLOCKER or MAJOR findings
- every MAJOR finding has evidence and a fix disposition
- critique report is generated from immutable artifact hashes
```

---

### 4. The question bank contains many universal rules that are actually style preferences

Several questions fail work that may be intentionally valid.

Examples:

- Q2.13: POV must be used
- Q2.23: 3/4 front should be the workhorse
- Q3.25: the last shot must have a striking camera move
- Q4.3: leading lines should be used
- Q4.9: symmetry should be used
- Q5.17: audio bridges should be used
- Q7.14: music should be present when a scene “clearly needs” it
- Q1.30: every narrative must have a theme

These should not be pass/fail requirements for every story. Convert them into applicability-aware checks:

```markdown
Applicability: REQUIRED | OPTIONAL | NOT_APPLICABLE
Status: PASS | FAIL | ADVISORY
Reason:
```

For example:

```text
Q2.13 POV usage:
- REQUIRED for subjective discovery or fear sequences
- OPTIONAL otherwise
- NOT_APPLICABLE for product montage or ensemble staging
```

This will reduce false failures and make the critique more defensible.

---

### 5. The question bank says 210+ questions, but the current inventory is 220

The sections contain:

```text
30 + 30 + 30 + 30 + 24 + 25 + 25 + 20 = 214
```

Actually, the displayed spatial section runs through `Q8.20`, so the total is:

```text
30 + 30 + 30 + 30 + 24 + 25 + 25 + 20 = 214
```

The prompt examples also use different numbers:
- `210+`
- `200+`
- `215`
- `200 questions`

This should be generated dynamically from the question bank. Never hard-code the expected count in prompts or examples.

Use:

```text
Questions evaluated: <validator-derived count>
```

The validator should extract all IDs and calculate totals itself.

---

### 6. Transition semantics are inconsistent across files

`storyboard_planner.md` defines eight transitions, including:

```text
continuous
hard_cut
cut_on_action
reaction_cut
match_cut
whip_pan
audio_led
camera_move
```

But its field notes later say:

> transition is `continuous` or `hard_cut`

That contradicts the eight-value grammar.

Also:

- `continuous` is described as a transition
- `camera_move` is described as not a cut
- generation boundaries are said to always be cuts
- the first shot of a generation may be `continuous`

You need separate concepts:

```text
shot_boundary:
  continuous
  cut

cut_type:
  hard_cut
  cut_on_action
  reaction_cut
  match_cut
  whip_pan
  audio_led

camera_change:
  none
  camera_move
```

A cleaner storyboard representation would be:

```text
boundary:
  kind: cut | continuous
  type: cut_on_action
```

Or, if preserving the Markdown format, explicitly state:

```text
The parenthesized transition value is one of the eight values.
`continuous` and `camera_move` do not create editorial cuts.
```

---

### 7. `audio_led` is being used ambiguously

The prompts describe `audio_led` as:

> next shot's sound starts before the visual

But in `storyboard_planner.md`, the shot's own `audio:` field is required to be non-empty. It is unclear whether the audio belongs to:
- the outgoing shot
- the incoming shot
- both
- the next shot beginning early

Define this explicitly:

```text
audio_led on Shot N means Shot N+1 audio begins during Shot N.
Shot N+1 must declare `incoming_audio:` or an equivalent field.
```

Otherwise the video prompter cannot reliably translate the transition into H3 instructions.

Also, Q5.17 and Q7.5 make audio bridges sound mandatory at boundaries. That is too strict. Audio bridges should be optional and motivated.

---

### 8. Shot 1 audio/dialogue handling is underspecified

`video_prompter.md` requires:

```text
[Shot 1] <action, camera, audio. NO timestamp on Shot 1.>
```

But it does not clearly require dialogue from the storyboard to appear in the video prompt, except indirectly through the dialogue rules.

Add a deterministic mapping contract:

```text
Every non-empty storyboard `dialogue:` field must appear exactly once
in the corresponding video prompt shot, unless explicitly marked:
- omitted_by_design
- off_screen
- continued_across_cut
```

Also validate:
- dialogue speaker exists in `characters_present`
- dialogue is not assigned to a character outside the scene cast
- dialogue timing fits inside the shot
- no dialogue is silently dropped during prompt generation

---

### 9. Character identity data has no authoritative source

The prompts alternate between:

```text
developed_story.md
assets/CHARACTERS.md
asset_registry.json
```

Examples:

- `story_developer.md` says Agent 1 creates character definitions.
- `image_prompter.md` says read `assets/CHARACTERS.md`.
- `storyboard_planner.md` says read `assets/CHARACTERS.md`.
- The architecture says `asset_registry.json` is authoritative.
- The actual file map does not list `assets/CHARACTERS.md`.

This is a major source-of-truth problem.

Define the ownership clearly:

```text
story bible:
  canonical semantic identity and narrative facts

asset registry:
  generated media, hashes, provider metadata, file paths

character manifest:
  canonical visual identity lock
```

Then specify which agent reads which one.

Recommended:

```text
developed_story.md:
  narrative character definition

characters.json:
  canonical normalized visual identity

asset_registry.json:
  generated asset metadata only
```

Do not require agents to read a file that may not exist.

---

### 10. Asset reuse by file existence is unsafe

The image prompt says:

> skip if `assets/characters/<cid>.png` exists

But the architecture uses `.webp` in multiple places. This is already inconsistent:

```text
assets/characters/*.webp
assets/characters/<cid>.png
```

More importantly, file existence does not prove that the asset matches the current character definition.

Reuse should be based on an identity fingerprint:

```text
character_id
visual_identity_hash
prompt_hash
model_hash
asset_path
status
```

Only reuse when:

```text
existing.visual_identity_hash == current.visual_identity_hash
```

Otherwise mark the asset as stale or create a versioned asset.

---

### 11. “No text” requirements conflict with useful visual identification

The prompts repeatedly require:

```text
no text, no labels, no captions
```

That is correct for storyboard sheets sent to video generation. It is less appropriate for character, object, and location reference sheets, where tiny labels can be useful for human review.

Separate the policies:

```text
video_reference_sheet:
  absolutely no text

human_review_asset_sheet:
  optional small labels, never embedded into the visual reference crop
```

If the same image is used both for human review and as a Minimax reference, keep it text-free and generate a separate metadata overlay externally.

---

### 12. The character-sheet layout is physically impossible or overconstrained

`character_sheet_template.md` asks for:

- six full-body turnaround views in one row
- twelve large expressions
- accessory close-ups
- scale reference
- little empty space
- maximum character pixels
- all on one 16:9 sheet

This will produce very small figures and unreadable expressions. The requirements directly conflict.

Use separate assets:

```text
character_identity_sheet:
  6 turnaround views + accessories

character_expression_sheet:
  6-12 expressions

character_scale_sheet:
  optional

character_render_reference:
  one or two hero views for image/video generation
```

For downstream generation, the six-view identity sheet may be less useful than one clean, large 3/4 hero view plus a secondary full-body view.

---

### 13. The location prompt asks for impossible 360-degree coverage

Both the location prompt and directors guide require:

> a wide-angle 360-degree view of the entire space, all walls and corners visible in one frame

A single 16:9 image cannot reliably show all walls and corners without severe distortion. The spatial planner correctly says it is not a true 3D system, but the prompt still presents the location image as if it were panoramic geometry.

Change the wording to:

```text
Create a wide establishing environment plate with readable left-to-right
geography, visible anchor landmarks, and enough surrounding context to imply
the space. Do not claim literal 360-degree geometric coverage.
```

If true environmental continuity is needed, generate:
- a left-facing plate
- a right-facing plate
- an overhead/layout diagram
- or a multi-view location reference set

---

### 14. Spatial zones are too restrictive for camera zones

The spatial planner says:

> zone X ranges must NOT overlap

Then it uses zones for:
- character placement
- camera placement
- landmarks
- depth

A camera often needs to be located in the same broad spatial region as a character or cross a zone boundary during a continuous tracking shot. Non-overlapping horizontal slices make this difficult.

Separate these concepts:

```text
subject_zone
camera_zone
landmark_region
forbidden_region
```

Also, X/Y pixel coordinates in a generated panorama are not stable enough to validate exact subject placement from an image model. Treat them as coarse bins:

```text
left_third
center
right_third
foreground
midground
background
```

Use numeric coordinates for planning metadata, but avoid implying pixel-level enforcement.

---

### 15. Spatial continuity validation cannot prove visual correctness

The spatial validators can prove that:
- declared coordinates are in ranges
- IDs match
- movement constraints are mathematically consistent

They cannot prove that the generated sheet obeys those coordinates. Agent 7 is the only component that checks the image.

However, Agent 7 is explicitly non-blocking:

> WARN entries do not block

That makes the spatial contract advisory in practice.

Consider severity levels:

```text
PASS
WARN
BLOCKER
```

Use `BLOCKER` for:
- missing protagonist
- duplicated protagonist
- wrong location
- forbidden landmark present during a critical reveal
- severe left/right reversal
- missing required prop

Use `WARN` for:
- approximate depth mismatch
- weak landmark visibility
- minor placement drift

---

### 16. Agent 5 is instructed to describe what was drawn, but structural fidelity remains mandatory

`video_prompter.md` correctly says:

> describe what was actually drawn, not what you wished for

But it also requires the prompt to match the storyboard exactly:
- same shot count
- same timestamps
- same identities
- same actions
- same spatial contract

This creates a conflict when the sheet differs from the storyboard.

The system needs an explicit discrepancy policy:

```text
If the sheet matches the storyboard:
  author the normal video prompt.

If the sheet differs but remains usable:
  author a visual-discrepancy report and revise the prompt to match the sheet.

If the sheet is unusable:
  block Agent 5 and regenerate the sheet.

Never silently describe a visual action absent from the sheet.
Never silently accept a sheet that contradicts a critical storyboard beat.
```

Agent 5 should not be responsible for correcting image-generation errors through text.

---

### 17. The image prompt validator appears too weak

The prompt says the validator checks:

> every character prompt file exists + non-empty, location prompt exists, one sheet prompt per generation

But the architecture claims action fidelity and cross-artifact checks. The validator should also verify:

- every storyboard generation has exactly one sheet prompt
- every shot's claimed panels are represented in panel directions
- every key action token appears in the relevant panel description
- all required cast IDs have identity coverage
- all props in critical shots appear in `PROP CONTINUITY`
- no invented character IDs
- no forbidden internal IDs in natural-language sections
- no-text clause exists exactly once at the end
- prompt order is correct
- generated spatial block is present exactly once

Otherwise many of the important prompt rules remain procedural advice rather than enforcement.

---

### 18. “Action fidelity” based on keyword presence is brittle

The architecture says the validator checks that key action words appear in panel descriptions. This can create false positives:

```text
Storyboard: "runs frantically"
Panel prompt: "the character watches the runner who runs frantically"
```

The keyword exists, but the panel may not depict the correct subject.

It can also create false negatives:

```text
Storyboard: "sprints"
Panel prompt: "dashes at full speed"
```

Semantically correct, lexically different.

Prefer structured action tokens in the storyboard:

```yaml
action_tokens:
  - subject: char_01
    verb: sprint
    intensity: frantic
    direction: toward_landmark
```

Then validate semantic fields deterministically where possible, and use the LLM only for equivalence review.

---

### 19. The prompts over-specify camera and action for an image-only storyboard sheet

The storyboard sheet is a static image, but many panel directions include:
- camera movement
- temporal progression
- complex multi-stage action
- exact start/end positions
- animation micro-beats

A still image cannot reliably represent all of that. The image prompt should distinguish:

```text
visible pose:
  what must be frozen in the panel

temporal implication:
  what the panel suggests happened before/after

video-only direction:
  what belongs exclusively in video_prompts
```

For example:

```text
Panel:
  visible pose: Kemi crouched with one foot planted and fist raised
  temporal implication: she has just landed after the leap
Video:
  action: crouches, launches, rotates, lands, dust settles
```

This will reduce overloaded image prompts and improve panel readability.

---

### 20. The storyboard example contains internal inconsistencies

The example in `storyboard_planner.md` has several issues that could teach agents the wrong behavior:

- `g1` ends at `15.0s`; `g2` starts at `15.0s`, which is correct, but the generation durations are not aligned with the stated “at most 15 seconds” examples consistently.
- Shot 5 uses `hard_cut` with the same character absent from Shot 6, but the object continuity is not explicitly explained.
- Shot 7 uses `reaction_cut` while introducing a new character and dialogue, which may be acceptable but should explain the new information.
- The example uses `Low Angle Tracking Shot`, while the documented vocabulary says `Tracking Shot`, `Tilt`, etc. The validator may reject “Low Angle Tracking Shot” unless aliases are supported.
- The example says `character_facing` and spatial positioning are mandatory, but the storyboard example itself does not show those fields because they live in the spatial plan. This should be stated clearly.
- “Continue directly from the previous scene” is used for generation continuity, but no exact handoff state is shown.

Examples should be validator-clean test fixtures, not illustrative pseudo-files.

---

## Prompt-Specific Recommendations

### `story_developer.md`

Add a structured story contract before the free-form narrative:

```markdown
story_id:
title:
format:
target_seconds:
genre:
tone:
protagonist_id:
theme:
logline:

## Story Objectives
visible_goal:
central_conflict:
stakes:
climax:
resolution:
```

The current prompt asks the developer to produce a rich story, but downstream agents must infer critical fields from prose.

Also, “every scene needs goals, conflict, and stakes” is difficult for Agent 1 to guarantee because scenes do not exist yet. The developer should define story-level and candidate-sequence objectives; Agent 2 should own scene-level validation.

---

### `beat_board.md`

The beat board needs stronger fields:

```text
beat_type: setup | escalation | reversal | climax | resolution
protagonist_state_before:
protagonist_state_after:
visible_goal:
obstacle:
stakes:
required_props: []
required_characters: []
location_hint:
```

The current `emotion` field is useful but insufficient to drive reliable downstream planning.

Also, the timing warning of “within 50%” is too permissive. A beat board totaling 50% or 150% of target is not a useful timing guide. Use:

```text
warning: outside 20%
error: outside 40%
```

Or calculate beat timing from scene targets after scene planning.

---

### `scene_writer.md`

Add explicit ownership of scene duration and beat mapping:

```text
Every beat must be assigned exactly once.
A beat may not be split across scenes.
If a beat requires multiple locations, mark it as a scene-boundary candidate
and split the beat during beat-board revision.
```

The current “do not split a beat” rule may be too rigid for long beats. A better model is to allow:

```text
beat segment:
  beat_id: 4
  segment: a
  function: setup
```

Forcing every dramatic beat into one scene can produce awkward scene durations.

---

### `spatial_planner.md`

The spatial plan is ambitious, but it is doing too much in one format. Split it into:

```text
static_spatial_plan:
  landmarks
  zones
  world axis
  lighting
  forbidden regions

dynamic_shot_plan:
  character positions
  camera position
  facing
  visible landmarks
  movement
```

This makes it easier to reuse the static location geography across all scenes and episodes.

Also clarify whether `location_ref_id` is:
- the location asset ID
- the location prompt ID
- the scene's location ID from `developed_story.md`

It should be one canonical identifier.

---

### `spatial_qa_agent.md`

Spatial QA should have an escalation policy. Current behavior makes every issue a warning, including potentially fatal errors.

Recommended:

```text
PASS:
  minor approximation only

WARN:
  usable but continuity is weak

BLOCKER:
  wrong character count, wrong location, major landmark contradiction,
  impossible geography, missing required prop
```

Also require an image-reference record:

```text
image_path:
image_sha256:
spatial_plan_sha256:
reviewed_at:
```

This prevents a QA report from becoming stale after sheet regeneration.

---

### `storyboard_sheet_template.md`

The prompt repeats much of the same material as `image_prompter.md`. This creates two sources of truth for:
- grid layout
- panel numbering
- hard exclusions
- reference ordering
- spatial block behavior
- style restrictions

Keep the template as the source of truth and make `image_prompter.md` a shorter execution prompt that references it.

The current duplication will eventually drift.

Also, do not place a literal text diagram called `PANEL MAP` in a prompt whose requirement is “no text.” The model may render the panel map or interpret it as page content. Put the map in a machine-readable metadata header or use plain prose:

```text
Read panels column-major: top-left, middle-left, bottom-left,
top-right, middle-right, bottom-right.
```

---

### `video_prompter.md`

The prompt should explicitly define how to handle visual discrepancies:

```text
The rendered sheet is the visual authority for appearance and composition.
The storyboard is the temporal and editorial authority.
If they conflict, stop and report the conflict unless it is a non-critical
visual approximation.
```

Also add a hard check that each prompt uses the correct reference-picture count. The current prompt says one `<Picture 1>`, but the reference system may attach:
- previous sheet
- location lock
- character sheets
- extras

The H3 prompt should clarify whether these are all represented as `<Picture N>` labels or whether only the storyboard sheet is `<Picture 1>` and other images remain unmentioned. The current documentation is ambiguous.

---

## Recommended Pipeline Changes

A stronger pipeline would be:

```text
1. Agent 1 writes story.md and normalized story.json
2. Agent 1b writes beat_board.md and beat_board.json
3. Structural validation
4. Agent 2 writes scenes.md and scenes.json
5. Structural validation
6. Agent 3a writes spatial_plan.json/md
7. Agent 3 writes storyboard.md and storyboard.json
8. Cross-artifact validation
9. Agent 6 generates critique findings
10. Director/user resolves findings
11. Immutable approval snapshot
12. Python generates assets and sheets
13. Agent 7 performs visual QA
14. User approves or rejects sheets
15. Agent 5 writes video prompts from approved sheets
16. Video prompt validation
17. User approves render manifest
18. Render jobs execute from manifest
19. Automated media QA
20. Concat and final delivery validation
```

The most important change is inserting an explicit **approved render manifest** before paid video generation.

```json
{
  "scene_id": "s1",
  "generation_id": "g2",
  "sheet": "storyboard_sheet_s1_g2.webp",
  "sheet_sha256": "...",
  "video_prompt": "video_prompts/s1_g2.txt",
  "video_prompt_sha256": "...",
  "previous_tail": "tails/s1_g1_tail.mp4",
  "status": "approved",
  "approved_by": "user",
  "approved_at": "..."
}
```

## Priority Order

I would address these first:

1. Resolve the duration contradiction for short-form stories.
2. Establish one canonical source of truth for character and location identity.
3. Separate structural validation, creative critique, and human approval.
4. Fix transition and audio-led semantics.
5. Add artifact hashes and stale-artifact detection.
6. Make the question bank applicability-aware instead of universally prescriptive.
7. Replace file-existence asset reuse with identity fingerprints.
8. Clarify the sheet-versus-storyboard discrepancy policy.
9. Split overloaded character/location sheets into purpose-specific references.
10. Strengthen visual QA from non-blocking warnings to severity-based outcomes.

The core design is viable. The largest risk is not the brain/hands split; it is that the prompts currently contain several competing authorities and many aesthetic preferences expressed as hard validation rules. Those two issues will cause the most operational friction as the number of scenes, episodes, and regenerated assets increases.