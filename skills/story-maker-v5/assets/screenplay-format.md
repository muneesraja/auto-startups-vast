# Animation Screenplay Format Guide

A reference for authoring production-grade animation screenplays inside
`story-maker-v5`. Every `developed_story.md` must be written in this format.

The standard is drawn from professional feature animation screenwriting
(Pixar, DreamWorks, Skydance Animation) and optimized for AI video generation
pipelines where downstream agents parse the screenplay for dialogue, sound
cues, timing, and staging.

---

## 1. Scene Headings (Sluglines)

### Master Sluglines

Every new location or time-of-day shift opens with a **master slugline** in
ALL-CAPS:

```text
INT. KITCHEN - NIGHT
EXT. SUNLIT POND - DAY
EXT. CANYON CHASM - CONTINUOUS
INT. UNDERWATER VALLEY - CONTINUOUS
```

Format: `INT./EXT. LOCATION NAME - TIME`

| Time Tag | Meaning |
|---|---|
| `DAY` | Daylight |
| `NIGHT` | Nighttime |
| `DAWN` / `DUSK` | Transitional light |
| `CONTINUOUS` | Unbroken action from the previous slugline |
| `MOMENTS LATER` | Brief implied time skip |
| `SAME` | Same time, different angle or location |

### Secondary / Camera Sluglines

Within a scene, use **secondary sluglines** (also ALL-CAPS) to signal POV
shifts, reveals, or sub-locations without starting a new scene:

```text
OLLIE'S POV - THROUGH THE CYLINDER

BACK TO SHORE

PULL BACK TO REVEAL

OLLIE'S POV - THE CANYON FLOOR

BACK ON THE LOG
```

These act as in-scene camera redirections. They tell Agent 3 (Storyboard
Planner) exactly where to cut to a POV shot or execute a dramatic reveal.

---

## 2. Action Paragraphs (The 1–3 Line Rule)

### Present Tense, Active Voice, Always

Screenplays are written in the **eternal present**. Never past tense.

```text
✗  Ollie walked to the edge and looked down nervously.
✓  Ollie creeps to the edge. Peers over.
```

### Keep It Lean

**Maximum 3 lines per action paragraph.** White space controls reading tempo:

- Short paragraphs = fast cuts, kinetic energy.
- One-line paragraphs = punchy impact beats.
- Longer blocks (3 lines) = sustained action or environmental establishment.

```text
A sudden BUZZ. A glowing GREEN DRAGONFLY darts past his ears.

Ollie turns abruptly to follow it. His hind foot SLIPS.

The basket tips. Ollie lurches forward, but it's too late—

SPLASH! The basket hits the water, dumping the shell and flowers into
the shallows.
```

**Never write prose walls** (5+ lines of unbroken description). If you need
more detail, break it into multiple short paragraphs separated by blank lines.

### Physicalize Subtext

Follow the Unbound Storytelling Standard: show emotion through involuntary
physical reactions, not abstract labels.

```text
✗  Ollie felt terrified looking at the abyss.
✓  Ollie's beak falls open. Terror drains the color from his avian face.
```

---

## 3. ALL-CAPS Conventions (Load-Bearing)

### Sound Effects & Audio Cues

Capitalize significant sound events. These are direct signals to Agent 5's
`foley_and_sfx` audio stem:

```text
A sudden BUZZ.
SPLASH! The basket hits the water.
SNAP! Ollie saws off the flower head.
GLUG-GLUG-GLUG!
WHUMP. WHUMP. He beats the air with raw, desperate power.
A sinister CREAK of wood shatters the silence.
The fish's jaws SLAM shut with concussive force!
```

**Rule**: If the audience should *hear* it, CAPITALIZE it.

### Character Introductions

First appearance of a named character uses ALL-CAPS with age/species/visual
shorthand:

```text
YOUNG OLLIE (5), an impossibly cute, fuzzy Pookoo with wild spiky fur
and massive green eyes, sits on a mossy boulder.

CALOO, Ollie's massive, terrified father, erupts from the water.

This is OLLIE (trapped in the bird's body) and IVY (trapped in the Pookoo).
```

After introduction, use normal case: `Ollie`, `Ivy`, `Caloo`.

### Key Props & Transformations

Capitalize hero props on first introduction or significant state change:

```text
He twists a fat, sticky dollop of AMBER RESIN.
A buoyant surface float. A FLOATING SNORKEL ASSEMBLY.
ROOT SNAKES. A dozen of them slither out, coiling across the log.
```

---

## 4. Montage Formatting

Rapid engineering, preparation, or travel sequences use montage format:

```text
EXT. FOREST SHORELINE - MONTAGE

-- Ollie stands before a weeping pine tree. With a twig, he twists a
fat, sticky dollop of AMBER RESIN.

-- Using a sharp flake of flint, Ollie scrapes the rim of the wooden
cylinder smooth.

-- He slathers the sticky amber sap into the groove, pressing a disc
of translucent quartz into place. A waterproof lens.

-- He cinches a broad leaf strap around a wooden peg.

-- Ollie proudly pulls the helmet on. He squints tight, then opens his
eyes through the clear glass, beaming.
```

**Rules:**
- Each dash-beat (`--`) is one storyboard panel / shot.
- Keep each beat to 1–3 lines.
- The montage slugline tells Agent 3 to use rapid cuts (1.0–2.5s per shot).

---

## 5. Dialogue & Performance Directives

### Character Cue (Header)

Character name in ALL-CAPS, centered or left-aligned, on its own line:

```text
OLLIE
I told you, I don't fly!
```

### Parentheticals (Actor Direction)

Delivery tone, physical micro-acting, and comedic timing in parentheses
directly below the character cue:

```text
OLLIE
(squeaky, sheepish)
Hey, Dad...
(beat)
Uh... thirsty?
```

```text
IVY
(suddenly nervous)
Ollie?
```

```text
OLLIE
(Doppler-dropping wail)
We're gonna diiiieeee!
```

```text
OLLIE
(false bravado)
Alright, I think we could take him.
I'll go for the eyes.
```

**Common parenthetical vocabulary:**
- Delivery: `whispered`, `shouted over wind`, `muffled inside helmet`, `squeaky`, `deadpan`
- Emotion: `pure panic`, `false bravado`, `stunned awe`, `tender`
- Physical: `while clinging to his back`, `through gritted teeth`, `panting`
- Timing: `(beat)` — a deliberate pause for comedic or dramatic effect
- Continuation: `(CONT'D)` — same character speaks after an action line break

### Dialogue Rhythm

Real dialogue is messy, clipped, and alive:

```text
✗  "Please return that to me. It is my turn to play with it."
✓  "Give it back! It's my turn!"

✗  "I am feeling quite frightened right now, Ivy."
✓  "I'm scared, Ivy!"
```

---

## 6. Timing & Pacing Markers

### Explicit Time Jumps

Use brief time cues between action blocks to signal editorial pacing:

```text
ONE SECOND LATER—

Ollie violently yanks his head back, COUGHING and HACKING.
```

```text
TWO SECONDS LATER—

Ollie breaches like a launched torpedo, WHEEZING and GASPING for air!
```

### Scene Transitions

End scenes with transition directives when needed:

```text
FADE OUT.
CUT TO:
SMASH CUT TO:
```

---

## 7. Integrating with `developed_story.md`

The screenplay forms the **body** of `developed_story.md`. After the screenplay
text, the file must end with the required machine-readable metadata sections:

```markdown
# Screenplay

\`\`\`text
EXT. SUNLIT POND - DAY

YOUNG OLLIE (5), an impossibly cute, fuzzy Pookoo...
...
FADE OUT.
\`\`\`

## Characters
- id: char_01
  name: Young Ollie
  species: Pookoo
  age: 5
  appearance: Compact, otter-like woodland rodent with fluffy chocolate-brown
  fur, spiky russet head tuft, oversized black button nose, cream muzzle,
  massive emerald-green eyes.

## Locations
- id: loc_01
  name: Sunlit Pond
  description: A pristine, glassy pond edge framed by wild clover and
  giant orange gerbera daisies.
  establishing_prompt: ...

## Objects
- id: obj_01
  name: Diving Helmet
  description: Hollowed wood/gourd cylinder with translucent polished
  resin faceplate, sealed with amber sap, bound with woven leaf strap.
  appearance: ...

## Constraints
- id: H1
  type: co_presence_exclusion
  severity: BLOCKER
  ...
```

---

## 8. Anti-Patterns (Common Screenplay Failures)

| Anti-Pattern | Why It Fails | Fix |
|---|---|---|
| Prose walls (5+ line paragraphs) | Unreadable; no pacing signal; Agent 3 cannot parse beats | Break into 1–3 line paragraphs |
| Past tense narration | Not a screenplay; reads like a novel | Present tense always |
| Emotion labels ("felt angry") | Not filmable; Agent 4 can't draw "felt" | Physicalize: jaw clench, fist tightens |
| Missing sound cues | Agent 5 has no foley to extract | ALL-CAPS every audible event |
| No parentheticals on dialogue | Dialogue has no performance direction | Add tone + physical micro-acting |
| No sluglines | Agent 2 can't locate scene boundaries | `INT./EXT. LOCATION - TIME` |
| Generic/flat dialogue | Reads like translated subtitles | Clipped, colloquial, rhythmic |
