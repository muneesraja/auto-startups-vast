# Animation Cinematography Bible — Universal Visual Language for MiniMax H3

This reference bible provides the complete cinematography, camera grammar, facial reaction taxonomy, animation micro-beat mechanics, and composition rules for AI animation directing. Every agent authoring storyboards (`storyboard_sN.md`), sheet prompts (`storyboard_sheet_gK.txt`), or video prompts (`video_prompts/sN_gK.txt`) must select precise terms from this guide.

---

## Section A — Shot Sizes

Shot size controls emotional intimacy and spatial context. Vary shot sizes across shots within every generation.

| Shot Size | Abbreviation | Frame Coverage | Dramatic & Emotional Purpose |
|-----------|--------------|----------------|------------------------------|
| `extreme_wide` | EWS | Full environment, character occupies < 10% of frame | Establishes geography, loneliness, awe, epic scale, world-building |
| `wide` | WS | Full environment, characters fully visible with room around | Spatial relationships, staging multiple characters, action flow |
| `full` | FS | Head to toe, character fills 80-90% vertical frame | Posture, body language, physical locomotion, outfit reveal |
| `medium` | MS | Waist up | Conversational workhorse, two-character dialogue, hand gestures |
| `medium_closeup` | MCU | Chest up | Primary acting shot: balances facial emotion with physical posture |
| `closeup` | CU | Face fills frame (chin to forehead/hairline) | Intimacy, intense realization, emotional vulnerability, micro-acting |
| `extreme_closeup` | ECU | Single feature (eyes, mouth, trembling hands, prop) | Visceral intensity, high stakes, tactile detail, symbolic anchor |

### Combination & Framing Modifiers
- **Single**: One character isolated in frame, focusing audience empathy entirely on their internal reaction or state.
- **Two-Shot**: Two characters balanced in MS or MCU, establishing dynamic tension, camaraderie, or confrontation.
- **Three-Shot**: Three characters framed together, defining group dynamics, hierarchy, or triangulated tension.
- **Dirty Single**: Focuses on one primary subject while framing a subtle shoulder, back, or profile of another character in the foreground, grounding spatial proximity.
- **Clean Single**: Focuses entirely on one subject with zero foreground obstructions or foreign character elements.
- **Over-the-Shoulder (OTS)**: Camera looks past one character's shoulder/nape at another, anchoring spatial orientation (180° axis).
- **Insert Shot**: Quick cut to a prop, letter, clock, or mechanical trigger that drives the immediate scene logic.
- **Cutaway**: Brief cut to an external element or environmental reaction away from the primary characters.

---

## Section B — Camera Angles

Camera angle dictates power dynamics, psychological tension, and viewer empathy.

| Angle | Physical Setup | Emotional & Psychological Effect |
|-------|----------------|----------------------------------|
| `eye_level` | Lens at character's exact eye height | Neutral, intimate, democratic — places the viewer on equal footing with the character |
| `low_angle` | Lens placed below character looking upward | Power, dominance, heroism, towering presence, or ominous authority |
| `high_angle` | Lens placed above character looking downward | Vulnerability, helplessness, insignificance, isolation, diminutive scale |
| `birds_eye` | Directly overhead (90° vertical down) | God's-eye perspective, geometric layout, spatial map, detachment, fate |
| `worms_eye` | Ground level looking straight up | Extreme scale, towering awe, child-like wonder, dramatic ground impact |
| `dutch_angle` | Camera tilted off-axis on roll axis (10°–30°) | Psychological disquiet, madness, vertigo, physical instability, impending crisis |
| `over_the_shoulder` | Past one subject's shoulder toward another | Conversational grounding, perspective alignment, subjective confrontation |
| `pov` | Exactly where the character's eyes are | Total immersion, raw subjectivity, terror, firsthand discovery |
| `three_quarter_front` | 45° offset from straight front | The cinematic default: provides three-dimensional depth, facial curvature, and body volume |
| `three_quarter_back` | 45° offset from behind | Mystery, impending journey, contemplation, observation without engagement |
| `profile` | Strict 90° side view | Graphic silhouette, equal standoff, parallel motion tracking, emotional detachment |
| `top_down` | Overhead flat tabletop view | Ritual, sorting, tactile interaction, meal, map inspection, craft |

---

## Section C — Camera Positions (Spatial Ring)

Position defines where the camera body is placed relative to the subject on the horizontal plane:

| Position | Bearing | Recommended Use |
|----------|---------|-----------------|
| `front` | 0° direct head-on | Direct emotional address, formal confrontation, unblinking intimacy |
| `three_quarter_front_left` | 45° front-left | Workhorse framing: dimensional facial acting with left-leaning look room |
| `three_quarter_front_right` | 45° front-right | Workhorse framing: dimensional facial acting with right-leaning look room |
| `side_left` | 90° pure left profile | Tracking lateral movement, planar silhouette, standoff |
| `side_right` | 90° pure right profile | Tracking lateral movement, planar silhouette, standoff |
| `three_quarter_back_left` | 135° over left shoulder | Following character through space, looking forward together |
| `three_quarter_back_right` | 135° over right shoulder | Following character through space, looking forward together |
| `behind` | 180° direct rear | Departure, mystery, walking into the unknown, leading the audience |

---

## Section C-bis — Depth of Field & Focus

Focus directs audience attention and controls emotional detachment versus immersion.

| Focus Type | Description | Dramatic & Narrative Purpose |
|------------|-------------|------------------------------|
| `shallow_focus` | Subject sharp, foreground and background softly blurred | Isolation, intimacy, forcing attention onto performance |
| `deep_focus` | Everything from near foreground to deep background remains sharp | Environmental storytelling, staging multiple narrative planes |
| `rack_focus` | Focus visibly shifts from one plane/subject to another mid-shot | Redirecting audience attention, cause→effect revelation |
| `soft_focus` | Entire frame rendered with gentle diffused softness, low micro-contrast | Dream state, nostalgic memory, halo glamour, ethereal trance |

---

## Section D — Camera Movements (MiniMax H3 Native Vocabulary)

MiniMax H3 natively understands physical camera moves. Always use the **3D Camera Formula**:

```
[Motion Type] with [small|large] amplitude at [slow|fast] speed
```

### Primary Native Camera Movements

| Movement | Mechanical Action | Emotional & Narrative Function |
|----------|-------------------|--------------------------------|
| `Push In` | Camera moves physically toward subject | Intensifying focus, dawning realization, deepening intimacy |
| `Pull Out` | Camera moves physically backward from subject | Context reveal, growing isolation, departure, aftermath |
| `Zoom In` | Lens focal length narrows (perspective flattens) | Sudden alertness, dramatic accent (differs optically from push) |
| `Zoom Out` | Lens focal length widens (depth expands) | Scope expansion, disorienting shock, contextualizing |
| `Pan Left` / `Pan Right` | Camera pivots horizontally on fixed tripod | Scanning horizons, following head turns, redirecting focus |
| `Tilt Up` / `Tilt Down` | Camera pivots vertically on fixed tripod | Vertical reveal (shoes to face, towering trees to forest floor) |
| `Truck Left` / `Truck Right` | Camera physically slides horizontally | Lateral tracking, parallax foreground wipe, traversing corridors |
| `Pedestal Up` / `Pedestal Down` | Camera physically moves vertically up/down | Rising above obstacles, descending to eye level, floating elevation |
| `Arc Shot` | Camera circles around subject on curved track | 3D space reveal, emotional whirlwind, pivotal dramatic choice |
| `Tracking Shot` | Camera travels alongside moving subject | Journey, momentum, walking conversations, pursuit |
| `Static Shot` | Camera remains locked off, motionless | Contemplation, stillness, comedic timing, letting acting breathe |
| `Shake Slightly` | Subtle organic handheld float/breathing | Lived-in documentary realism, quiet tension, human presence |
| `Shake Strongly` | Violent mechanical camera tremor | Explosions, impacts, earthquakes, frantic pursuit, physical clash |
| `POV` | Camera moves organically as character's gaze | First-person experience, panic, scanning, creeping exploration |
| `Roll Clockwise` / `Roll Counterclockwise` | Camera spins on the optical barrel axis | Disorientation, gravity loss, transition to dream state, falling |

### Composite Camera Movements

Combine primary moves to express complex cinematographic intent:
- **Crane Up / Crane Down**: `Pedestal Up with Tilt Down` — swooping cinematic reveal of an epic environment.
- **Dolly Zoom (Vertigo Effect)**: `Push In with Zoom Out` (or reverse) — world warping while character stays static; sudden panic or revelation.
- **Orbit Follow**: `Arc Shot with Tracking Shot` — sweeping dynamically around a traveling character.
- **Whip Pan**: `Pan Left/Right at extreme fast speed` — kinetic energy transition between two focal points.
- **Steadicam Follow**: `Tracking Shot with smooth Push In` — floating seamlessly behind or ahead of walking characters.
- **Low-Angle Creep**: `Push In with small amplitude at slow speed at low angle` — approaching a mysterious or dangerous subject.

### Equipment Feel Cheatsheet

MiniMax H3 responds to physical motion descriptions rather than mechanical rig names. Translate cinematic equipment concepts to the native 3D camera formula:

| Equipment Feel | Native Motion Translation | Typical Cinematographic Use |
|----------------|---------------------------|-----------------------------|
| **Tripod / Sticks** | `Static Shot` | Controlled stillness, letting performance breathe |
| **Slider** | `Truck Left/Right with small amplitude at slow speed` | Subtle lateral parallax across foreground elements |
| **Handheld** | `Shake Slightly` or `Shake Strongly` | Organic breathing presence or chaotic visceral action |
| **Steadicam** | `Tracking Shot with smooth Push In at slow speed` | Floating, gliding elegance navigating complex terrain |
| **Gimbal** | `Tracking Shot with small amplitude` | Stabilized dynamic follow with responsive direction shifts |
| **Crane / Jib** | `Pedestal Up/Down with Tilt Down/Up` | Sweeping vertical elevations and dramatic environment reveals |
| **Drone / Cablecam** | `Crane Up with large amplitude at slow speed` + `Tracking Shot` | Expansive aerial geography and epic overhead traveling |

---

## Section E — Transitions & Cut Mechanics

Cuts must be purposeful. A cut must provide new visual or narrative information.

### Core Transition Grammar (MiniMax H3 Validated Phrases)

| Transition Code | Canonical Transition Phrase in Prompt | When to Use |
|-----------------|---------------------------------------|-------------|
| `hard_cut` | `Hard cinematic cut.` | Shift to new subject, space, angle, or temporal beat |
| `cut_on_action` | `Cut on the action.` | Mid-gesture, mid-jump, or door swing: kinetic momentum masks cut |
| `reaction_cut` | `Cut to the reaction.` | Cause → effect: character reacts to a sight, sound, or revelation |
| `match_cut` | `Match cut on <visual element>.` | Visual or geometric continuity linking two disparate scenes |
| `whip_pan` | `Whip pan transition.` | Camera swishes at high speed to bridge spaces with kinetic energy |
| `audio_led` | `Audio leads the cut.` | J-cut: next shot's sound/voice begins 0.5s prior to the visual cut |
| `continuous` | *(no cut phrase; omit or write "Continuous take.")* | Single uninterrupted shot without camera interruption |
| `camera_move` | *(describe camera repositioning within take)* | Reframing occurs purely via camera motion, no edit point |

### Extended Editorial Patterns
- **Smash Cut**: Abrupt jarring contrast from deafening action to absolute silence, or calm to frenzy.
- **Jump Cut**: Urgent temporal leap forward within the identical camera angle and subject.
- **Cross-Cutting**: Interweaving two parallel lines of action occurring simultaneously.
- **Match Sound**: L-cut where dialogue or audio lingers across the visual cut.

---

## Section F — Facial Reactions & Character Acting Taxonomy

Animation acting fails when described as generic states ("she looks sad"). Cinematic acting works because **the face reacts in an anatomical sequence**:

$$\text{Stimulus} \longrightarrow \text{Freeze} \longrightarrow \text{Eyes} \longrightarrow \text{Brows} \longrightarrow \text{Mouth} \longrightarrow \text{Head} \longrightarrow \text{Body} \longrightarrow \text{Secondary Motion}$$

### 1. Eye Reactions (18 Precise Actions)

| Reaction | Anatomical Motion | Emotional Register |
|----------|-------------------|--------------------|
| `eyes_widen` | Eyelids retract fully, whites visible around irises | Sudden shock, child-like wonder, sudden danger |
| `eyes_narrow` | Upper and lower lids squint inward | Suspicion, sharp concentration, hostility, skepticism |
| `eyes_dart` | Rapid lateral flickers between multiple points | Searching for escape, acute panic, guilty conscience |
| `eyes_downcast` | Irises sink toward floor, upper lids droop | Shame, sorrow, demure submission, hiding tears |
| `eyes_upward` | Gaze rolls toward sky or ceiling | Deep calculation, internal reflection, exasperation |
| `eyes_lock` | Unwavering laser focus on a single target | Uncompromising resolve, deep attraction, predator stance |
| `eyes_soften` | Tension leaves orbicularis oculi, warm gaze | Tenderness, maternal love, relief, forgiveness |
| `eyes_blink_rapid` | 3–4 rapid successive flutters | Disbelief, clearing vision, processing shocking information |
| `eyes_blink_slow` | Deliberate, prolonged eyelid closure | Heavy acceptance, weariness, emotional surrender |
| `eyes_squeeze_shut` | Lids clamp tight with crow's-feet wrinkling | Acute physical pain, terror, refusal to witness |
| `eyes_roll` | Upward and outward arc of irises | Impatience, sarcastic exasperation, dismissal |
| `eyes_sparkle` | Catchlights sharpen, eyes widen with subtle moisture | Childlike delight, sudden inspiration, mischievous scheming |
| `eyes_tear_up` | Liquid glassy glaze forms over cornea without spilling | Holding back immense grief, overwhelmed gratitude |
| `eyes_cry` | Distinct tears break over lower lash line onto cheeks | Uncontrollable grief, overwhelming emotional release |
| `eyes_glance_sideways` | Irises shift to extreme corner without head turn | Caution, secretive complicity, peripheral alertness |
| `eyes_defocus` | Pupils slight dilation, gaze fixes into empty mid-distance | Dissociation, traumatic flashback, lost in thought |
| `eyes_track` | Smooth pursuit movement across visual arc | Tracking floating dust, bird in flight, rolling object |
| `eyes_light_up` | Eyelids pop open, pupils dilate slightly | Eureka discovery, recognizing a loved face |

### 2. Brow Reactions (10 Actions)

| Reaction | Anatomical Motion | Emotional Register |
|----------|-------------------|--------------------|
| `brows_raise` | Frontalis contracts, forehead horizontal creases form | Pure surprise, questioning, greeting, openness |
| `brows_furrow` | Corrugator draws brows together and down | Focused struggle, anger, deep perplexity |
| `brow_single_raise` | One brow lifts high, the other stays neutral | "Is that so?", arched skepticism, playful challenge |
| `brows_pinch` | Inner corners pull upward creating center vertical folds | Empathy, acute worry, heartache, pleading |
| `brows_flash` | Micro-second lift and return | Quick greeting, instant recognition, conspiratorial nod |
| `brows_relax` | Forehead smooths, brows return to rest | Tension dissolving, clarity achieved, peaceful surrender |
| `brows_scrunch` | Tight knit pulling skin down over upper eyelids | Severe headache, blinding light, unbearable physical effort |
| `brows_knit` | Persistent tension between brows | Ongoing internal conflict, heavy decision-making |
| `brows_lift_slow` | Gradual upward expansion | Dawning understanding, rising astonishment |
| `brows_drop` | Heavy downward ledge over eye sockets | Ominous authority, intimidation, thunderous fury |

### 3. Mouth & Jaw Reactions (16 Actions)

| Reaction | Anatomical Motion | Emotional Register |
|----------|-------------------|--------------------|
| `mouth_open` | Jaw releases, lips part softly | Breathless awe, dumbfounded wonder |
| `mouth_close_tight` | Lips press into thin firm horizontal line | Resolute determination, stubborn refusal, enduring pain |
| `smile_slight` | Zygomaticus minor lifts lip corners subtly | Private amusement, gentle reassurance, quiet pride |
| `smile_wide` | Full teeth reveal, cheeks push high | Radiance, triumph, jubilant celebration |
| `smile_crooked` | One lip corner tugs upward | Charming arrogance, self-deprecating irony, cheeky dare |
| `grin` | Broad closed-mouth beam, lips stretched | Secret triumph, "I told you so", playful conspiracy |
| `frown` | Depressor muscles tug lip corners down | Heavy disappointment, disapproval, sullen sorrow |
| `pout` | Lower lip extends forward and upward | Childlike sulking, playful petulance, seeking comfort |
| `lip_bite` | Incisors catch inner lower lip | Nervous anticipation, intense hesitation, concentration |
| `lip_tremble` | Fine involuntary shudder of lower lip | Veracity of crying, freezing cold, suppressed terror |
| `lip_purse` | Orbicularis oris puckers lips forward | Critical appraisal, cautious doubt, kissing motion |
| `jaw_clench` | Masseter bulges visibly at jaw corner | Suppressed rage, extreme resolve under duress |
| `jaw_drop` | Dramatic dropped open mouth | Comedic or tragic absolute shock |
| `gasp` | Sharp inhalation, lips part into round O | Immediate discovery, sudden pain, jump-scare response |
| `snarl` | Levator labii pulls upper lip exposing canine | Primal disgust, animalistic defiance, fierce contempt |
| `tongue_out` | Tip of tongue rests on upper lip or pokes out | Intense manual dexterity focus, mischievous mockery |

### 4. Head Reactions (12 Actions)

| Reaction | Anatomical Motion | Emotional Register |
|----------|-------------------|--------------------|
| `head_tilt` | Ear tilts 15° toward shoulder | Curiosity, endearing attention, puppy-like query |
| `head_turn` | Smooth rotational pivot toward stimulus | Shift of attention, responding to a call |
| `head_snap` | Instant whip turn toward stimulus | Alarm, sudden threat detection, violent interruption |
| `head_drop` | Chin plunges to clavicle | Complete defeat, shame, crushing sorrow |
| `head_raise` | Chin points upward, throat exposed | Defiant pride, smelling the breeze, majestic posture |
| `nod` | Crisp single or double vertical bob | Agreement, silent approval, commanding assent |
| `head_shake` | Side-to-side rotation | Rejection, disbelief, "no way" |
| `head_cock` | Tilt accompanied by slight upward pivot | Bemused confusion, trying to comprehend |
| `head_bow` | Formal downward bend from neck | Humble gratitude, deep respect, solemn mourning |
| `head_recoil` | Sharp backward translation of neck and head | Visceral disgust, avoiding a physical blow, shock |
| `head_hang` | Limp cervical spine, chin resting on chest | Exhaustion after long battle, total loss of hope |
| `chin_tuck` | Chin retracts toward neck | Timid shyness, bracing against cold or gale |

### 5. Body Language & Posture (18 Actions)

| Reaction | Physical Execution | Emotional Register |
|----------|-------------------|--------------------|
| `lean_forward` | Torso tilts toward focal subject | Eager curiosity, investigative passion, intimidation |
| `lean_back` | Torso pulls back into seat or stance | Healthy skepticism, defensive reserve, casual ease |
| `shoulders_hunch` | Trapezius contracts, neck disappears | Freezing cold, acute fear, feeling small and targeted |
| `shoulders_drop` | Shoulders sink with long exhalation | Massive relief, burden lifted, surrender |
| `shoulders_square` | Shoulders draw back, chest expands | Taking charge, courage rallying, military discipline |
| `arms_cross` | Forearms fold over sternum | Emotional armor, stubborn resistance, waiting guard |
| `hands_clasp` | Fingers interlock tightly before chest | Pervasive anxiety, earnest prayer, fervent hope |
| `hands_on_hips` | Palms on iliac crests, elbows flared | Playful exasperation, bossy authority, readiness |
| `fists_clench` | White knuckles, fingernails pressing into palms | Simmering fury, summoning will to fight |
| `hand_cover_mouth` | Palm flies up to mask open lips | Suppressing a gasp, muffling laughter, sheer shock |
| `hand_reach` | Arm extends forward, fingers splayed | Longing, offering rescue, desperate yearning |
| `gesture_pointing` | Forefinger extends rigidly | Directing gaze, accusing, leading the way |
| `gesture_wave` | Palm opens and sweeps rhythmically | Cheerful greeting, wistful goodbye, frantic hailing |
| `fidget` | Twisting hem of shirt, tapping fingers | High nervous energy, restless impatience, deception |
| `startle` | Involuntary whole-body electric jolt | Jump-scare, physical shock, rude awakening |
| `freeze` | All locomotion ceases in mid-stride | Stalking prey, hiding from predator, pure realization |
| `slump` | Spine curves into C-shape, head droops | Crushing disappointment, defeat, drained battery |
| `bounce` | Weight shifts rapidly onto balls of feet | Uncontainable joy, athletic readiness, giddy thrill |

---

## Section G — Animation Micro-Beats & Physics

Never write abstract instructions like "the boy reacts with surprise." Professional animators choreograph micro-beats with clear cause-and-effect timing:

### The Canonical Micro-Beat Sequence
1. **Stimulus**: The trigger occurs (sound, object lands, voice calls).
2. **Freeze (Anticipation)**: Primary character stops for 2–4 frames (0.1s).
3. **Eyes lead**: Eyes snap or dart to the source first.
4. **Brows & Mouth follow**: Facial planes shift (eyes widen + brows lift + jaw drops).
5. **Head follows eyes**: Cranium turns toward the stimulus with secondary tilt.
6. **Body rebalances**: Torso, shoulders, and hips adjust to the new center of gravity.
7. **Secondary motion settles**: Clothes, hair, tassels, ears, and props overshoot and settle with a natural delay.

### Worked Examples of Micro-Beat Choreography

- **Childlike Discovery**:
  > *"Freezes mid-step. Her amber eyes widen into huge glass marbles, catching the morning sun. Her brows lift into soft arches, and her mouth parts in a silent, delighted gasp. She tilts her head sideways like an inquisitive bird, then slowly extends her small trembling hand forward. Her honey-colored braids swing forward over her shoulder with the movement and gently settle against her pinafore."*

- **Suppressed Panic**:
  > *"At the metallic clatter, his eyes dart violently to the left without his head moving. He freezes rigid. His brows pinch upward into deep worry lines, his lower lip quivers once, and his hands snap into tight fists at his sides. Only after a beat does his head snap around, the oversized collar of his woolen sweater rubbing against his chin as he braces."*

- **Explosion of Joy**:
  > *"Her eyes light up with sparkling highlights as both brows flash upward. A wide, toothy grin spreads across her cheeks, dimples creasing. She throws her head back with a bright laugh, bouncing up and down on the balls of her sneakers. Her curly auburn hair bounces with buoyant spring, settling a fraction of a second after her feet touch ground."*

### Principles of Secondary Motion & Weight
- **Overlapping Action**: Different parts of the body move at different rates (e.g., hip rotates, then chest follows, then shoulders, then wrist).
- **Follow-Through**: Fabric, capes, ribbons, long hair, animal tails, and floppy ears never stop when the character stops — they travel past the resting point and sway back into rest.
- **Squash and Stretch**: When landing from a leap or expressing extreme shock, facial features and body masses compress (squash) on impact and elongate (stretch) during acceleration.

---

## Section H — Composition Rules (12 Essential Techniques)

| Rule | Description | Narrative Purpose |
|------|-------------|-------------------|
| `rule_of_thirds` | Subject placed at intersections of 3×3 grid | Natural balance, pleasing aesthetic movement across frame |
| `center` | Subject placed squarely in the exact geometric center | Symmetry, supreme importance, spiritual confrontation |
| `symmetry` | Left and right halves mirror each other | Formal grandeur, fairy-tale mythic atmosphere, ritual |
| `leading_lines` | Architecture, paths, beams of light pointing to subject | Directs the viewer's eye relentlessly to the focal narrative beat |
| `negative_space` | Vast unoccupied canvas surrounding a tiny subject | Profound loneliness, vulnerability, peaceful contemplation |
| `depth` | Staging with distinct Foreground, Midground, and Background | Layered 3D parallax, rich world density, tactile immersion |
| `silhouette` | Subject backlit in black profile against vibrant light | Graphic elegance, mystery, iconic hero posture |
| `frame_within_frame` | Archways, doorframes, foliage branches framing subject | Voyeurism, feeling trapped, crossing a threshold |
| `visual_hierarchy` | Lighting and contrast ensure one dominant focal point | Instant visual clarity in fast 5–15s animated sequences |
| `headroom` | Calculated vertical breathing room above character's head | Proper framing; too little feels cramped, too much feels dwarfed |
| `look_room` | Negative space ahead of character's gaze direction | Visual balance allowing character to "look into their future/goal" |
| `screen_direction` | Respecting the 180° axis across editorial cuts | Ensures spatial coherence so characters face each other correctly |

---

## Section I — Director's Brief Prompt Construction

When compiling the final video prompt for MiniMax H3, synthesize these elements into the clean, scannable **Director's Brief** structure:

```
subject_definitions:Reference

Use the provided storyboard as the exact visual guide for composition,
framing, character appearance, environment, and sequence progression.

Maintain the exact appearance of [Character 1]: [Full descriptive paragraph].

Maintain the exact appearance of [Character 2]: [Full descriptive paragraph].

[Environment context and ambient atmosphere.]

[Behavioral constraints & anti-artifact guardrails.]

Generate a cinematic [duration]-second [pacing] sequence matching the
[grid]-panel storyboard.

[Style declaration line 1 - craft, medium, texture]
[Style declaration line 2 - color palette, lighting]
[Style declaration line 3 - rendering aesthetic]
[Quality declarations - natural physics, expressive micro-acting, temporal coherence]

[If g2+: This is a seamless continuation from the previous generation.
SHOT 1 begins from the exact ending pose, camera angle, and lighting of the previous clip.]

Timeline

SHOT 1 — 0.0–X.Xs (Continuous Shot)

[Visual Description: Shot size, camera angle, character positioning, and micro-beat acting sequence.]

[Camera instruction: 3D Camera Formula with motion type, amplitude, and speed.]

Audio: [Detailed soundscape: Foley, environment acoustics, vocalizations or <d>[English] dialogue</d>.]

[Transition phrase from Section E, or finish.]

SHOT 2 — X.X–Y.Ys (Continuous Shot)
...
```
