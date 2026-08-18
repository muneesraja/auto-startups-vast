# Directing Questions Bank (story-maker-v3)

210+ questions for the critique agent (Agent 6) to evaluate the full director plan
(beat_board.md + scenes.md + all storyboard_sN.md). Organized by the 7 sections of
[`directors-guide.md`](directors-guide.md). Each question has a stable ID, the
question text, what to check, and pass/fail criteria.

The critique agent reads this file and evaluates every question against the
artifacts, producing `critique_report.md` with PASS/FAIL per question.

---

## Section 1: Story & Visual Storytelling (30 questions)

### Q1.1 — Does every scene have a visible goal?
- **Check:** scenes.md — each scene's `beat:` field names a visible character goal.
- **Pass:** every scene states what the character wants in visible action terms.
- **Fail:** any scene where the character has no visible goal (just "walks" or "exists").

### Q1.2 — Does every scene have a conflict?
- **Check:** scenes.md — each scene has something standing in the way of the goal.
- **Pass:** every scene names an obstacle, antagonist, or environmental resistance.
- **Fail:** any scene where the character achieves the goal with no resistance.

### Q1.3 — Does every scene have stakes?
- **Check:** scenes.md — each scene implies what happens if the character fails.
- **Pass:** failure consequences are visible or strongly implied.
- **Fail:** any scene where failure has no consequence (no stakes = no tension).

### Q1.4 — Is there a clear setup → escalation → climax → resolution spine?
- **Check:** beat_board.md — the beats trace this arc across the full story.
- **Pass:** early beats establish, middle beats escalate, one beat is the climax, last beat resolves.
- **Fail:** beats are flat (no escalation) or the climax is missing or unclear.

### Q1.5 — Does the beat board trace a complete emotional arc?
- **Check:** beat_board.md — emotions vary across beats and form an arc.
- **Pass:** emotions shift through the story (e.g., joy → fear → tension → triumph).
- **Fail:** emotions are monotonous (all "tension" or all "joy").

### Q1.6 — Are any beats padding (no change in situation or emotion)?
- **Check:** beat_board.md — each beat changes the character's situation or emotion.
- **Pass:** every beat is a meaningful change.
- **Fail:** any beat that repeats the previous beat's situation and emotion.

### Q1.7 — Are consecutive beats different in emotional register?
- **Check:** beat_board.md — no 3+ consecutive beats share the same emotion.
- **Pass:** emotional variety across consecutive beats.
- **Fail:** 3+ consecutive beats with the same emotion (story is stalling).

### Q1.8 — Is the story told visually (show vs tell)?
- **Check:** developed_story.md + scenes.md — no inner thoughts, only visible action.
- **Pass:** all descriptions are camera-visible (expressions, actions, movements).
- **Fail:** any "she felt afraid" or "he remembered" — inner thoughts the camera can't see.

### Q1.9 — Does every scene have one visible objective?
- **Check:** scenes.md — each scene's `beat:` is one sentence of visible action.
- **Pass:** every scene's beat is a single visible objective.
- **Fail:** any scene with multiple objectives or a non-visible objective.

### Q1.10 — Are character goals visible, not internal?
- **Check:** scenes.md — goals are physical/visible, not emotional/internal.
- **Pass:** "Kemi wants to protect Timi" shown as "Kemi shields Timi behind her."
- **Fail:** goals stated as internal states ("Kemi wants to feel safe").

### Q1.11 — Does the story have a clear protagonist?
- **Check:** developed_story.md — one character is the clear focus.
- **Pass:** a single protagonist drives the story; other characters support.
- **Fail:** no clear protagonist or multiple equal protagonists (diffuse focus).

### Q1.12 — Does the protagonist change across the story?
- **Check:** beat_board.md — the protagonist's situation or emotion at the end differs from the start.
- **Pass:** the protagonist is in a different state at the resolution vs the setup.
- **Fail:** the protagonist is unchanged (no character arc).

### Q1.13 — Is the antagonist/obstacle strong enough?
- **Check:** scenes.md — the conflict is proportional to the protagonist's ability.
- **Pass:** the antagonist or obstacle genuinely threatens the protagonist's goal.
- **Fail:** the obstacle is trivially overcome (no real tension).

### Q1.14 — Does the climax feel earned?
- **Check:** beat_board.md — the climax follows sufficient escalation.
- **Pass:** enough beats escalate before the climax that it feels inevitable.
- **Fail:** the climax arrives too early or without buildup.

### Q1.15 — Does the resolution pay off the setup?
- **Check:** beat_board.md — the resolution connects to the setup.
- **Pass:** the ending resolves the conflict established in the setup.
- **Fail:** the ending is unrelated to the setup (no payoff).

### Q1.16 — Is the story sized to the target?
- **Check:** scenes.md — sum of target_seconds is within 15% of TARGET.
- **Pass:** timing sums correctly (this is also structurally validated).
- **Fail:** timing is off (should already be caught by the structural validator).

### Q1.17 — Are scene boundaries at location changes?
- **Check:** scenes.md — each scene is in one location; location changes = new scene.
- **Pass:** no scene jumps between locations.
- **Fail:** any scene with multiple locations (should be split into two scenes).

### Q1.18 — Are adjacent scenes different in location, focus, or tone?
- **Check:** scenes.md — consecutive scenes differ in at least one dimension.
- **Pass:** adjacent scenes vary in location, lead character, or emotional register.
- **Fail:** adjacent scenes are too similar (anti-sameness violation).

### Q1.19 — Does every beat in the beat board belong to a scene?
- **Check:** beat_board.md + scenes.md — every beat number is in some scene's `beats:` list.
- **Pass:** all beats are covered (structurally validated when beat board exists).
- **Fail:** any beat not covered by a scene (dropped story content).

### Q1.20 — Is the cast list stable across the pipeline?
- **Check:** developed_story.md + scenes.md + storyboard_sN.md — same char_NN ids throughout.
- **Pass:** character ids are consistent from story through storyboard.
- **Fail:** any invented or renamed character id.

### Q1.21 — Are character appearances rich enough for visual consistency?
- **Check:** developed_story.md `## Characters` — each has detailed appearance.
- **Pass:** appearance fields include features, wardrobe, accessories, build.
- **Fail:** any character with a thin appearance description (< 2 sentences).

### Q1.22 — Are locations described with establishing detail?
- **Check:** developed_story.md `## Locations` — each has description + establishing_prompt.
- **Pass:** locations have enough visual detail to generate a sheet.
- **Fail:** any location with a vague description ("a forest").

### Q1.23 — Is there a memorable final image (button)?
- **Check:** beat_board.md last beat + scenes.md last scene — the ending is visually iconic.
- **Pass:** the last beat/scene has a strong, memorable visual.
- **Fail:** the ending is visually forgettable (just "she walks away").

### Q1.24 — Does the story avoid deus ex machina?
- **Check:** beat_board.md — resolutions come from character action, not external rescue.
- **Pass:** the protagonist solves the problem through their own action.
- **Fail:** an external force resolves the conflict without character agency.

### Q1.25 — Is the pacing appropriate for the target duration?
- **Check:** beat_board.md estimated_seconds + scenes.md target_seconds.
- **Pass:** fast-paced for short ads, breathing room for longer stories.
- **Fail:** pacing mismatches the format (too slow for 30s, too rushed for 5min).

### Q1.26 — Are objects/props introduced before they're critical?
- **Check:** developed_story.md `## Objects` + scenes.md `objects:` field.
- **Pass:** hero props are established before they drive a beat.
- **Fail:** a critical object appears with no prior introduction.

### Q1.27 — Does every scene advance the story?
- **Check:** scenes.md — each scene moves the plot forward.
- **Pass:** removing any scene would break the story's progression.
- **Fail:** any scene that could be removed without story impact (padding).

### Q1.28 — Is the tone consistent within each scene?
- **Check:** scenes.md + storyboard_sN.md — each scene has a coherent tone.
- **Pass:** shots within a scene share a consistent emotional register.
- **Fail:** jarring tone shifts within a single scene (should be two scenes).

### Q1.29 — Are character motivations clear?
- **Check:** developed_story.md — characters act for understandable reasons.
- **Pass:** the audience can infer why each character acts.
- **Fail:** any character acts without clear motivation (random behavior).

### Q1.30 — Does the story have a theme or message?
- **Check:** developed_story.md — there's an underlying idea beyond the plot.
- **Pass:** the story explores a theme (courage, family, greed, etc.).
- **Fail:** the story is pure action with no thematic underpinning (acceptable for ads, fail for narrative).

---

## Section 2: Shot Design (30 questions)

### Q2.1 — Does every shot's shot_size serve the beat's emotion?
- **Check:** storyboard_sN.md — each shot's `shot_size:` matches the beat's emotional intent.
- **Pass:** closeup for emotion, extreme_wide for isolation/scale, medium for interaction.
- **Fail:** shot_size is random or contradicts the emotion (closeup for geography, wide for intimacy).

### Q2.2 — Are shot sizes varied across each generation?
- **Check:** storyboard_sN.md — shot_size values differ across shots in a generation.
- **Pass:** at least 3 distinct shot sizes in a generation with 5+ shots.
- **Fail:** all shots in a generation share the same shot_size (flat visual).

### Q2.3 — Is the establishing shot extreme_wide or wide?
- **Check:** storyboard_sN.md — the first shot of the first generation establishes geography.
- **Pass:** scene opens with extreme_wide or wide to establish space.
- **Fail:** scene opens with closeup or medium (audience has no spatial context).

### Q2.4 — Are close-ups reserved for emotion/revelation?
- **Check:** storyboard_sN.md — closeup and extreme_closeup are used at emotional peaks.
- **Pass:** close-ups appear at moments of high emotion or key revelation.
- **Fail:** close-ups used for default framing (devalued through overuse).

### Q2.5 — Does the shot size progression build tension?
- **Check:** storyboard_sN.md — shot sizes tighten as tension rises within a generation.
- **Pass:** progression from wide → medium → closeup as tension builds.
- **Fail:** no progression (random sizes) or reverse progression (closeup → wide during tension).

### Q2.6 — Are there 5-8 micro-shots per 15s generation for fast-paced content?
- **Check:** storyboard_sN.md — generation shot count matches pacing intent.
- **Pass:** 5-8 shots for action/fast-paced generations; fewer for tender beats.
- **Fail:** too few shots (slow) or too many (chaotic) for the intended pacing.

### Q2.7 — Are tender/dialogue beats allowed longer shots (6-15s)?
- **Check:** storyboard_sN.md — emotional/dialogue shots aren't cut too fast.
- **Pass:** tender beats have shots longer than 4s with camera breathing.
- **Fail:** tender beats cut every 1.5s (undermines the emotion).

### Q2.8 — Is each shot's duration appropriate for its content?
- **Check:** storyboard_sN.md — shot duration matches the complexity of the action.
- **Pass:** simple actions get 1.5-3s; complex actions get 3-5s; emotional holds get 5+.
- **Fail:** shots too short to read or too long without content to fill them.

### Q2.9 — Does every shot have a clear subject?
- **Check:** storyboard_sN.md — the audience knows where to look in each shot.
- **Pass:** each shot's action: names a clear subject (character, object, or space).
- **Fail:** any shot where the subject is ambiguous.

### Q2.10 — Are establishing shots used after location changes?
- **Check:** storyboard_sN.md — new locations get an establishing shot.
- **Pass:** the first shot in a new scene/location is wide or extreme_wide.
- **Fail:** new scene starts in closeup without establishing the new space.

### Q2.11 — Are reaction shots used effectively?
- **Check:** storyboard_sN.md — important events get a reaction shot.
- **Pass:** key moments (reveal, impact, decision) are followed by a reaction shot.
- **Fail:** events happen without showing the character's reaction.

### Q2.12 — Is the 180° rule maintained (screen direction)?
- **Check:** storyboard_sN.md — characters face the same direction across cuts.
- **Pass:** screen direction is consistent; composition: includes screen_direction where relevant.
- **Fail:** characters flip facing direction across cuts (disorienting).

### Q2.13 — Are POV shots used for immersion at key moments?
- **Check:** storyboard_sN.md — POV shots appear when the audience should see what the character sees.
- **Pass:** POV used for discovery, fear, or revelation moments.
- **Fail:** POV never used (missed immersion) or overused (disorienting).

### Q2.14 — Are over-the-shoulder shots used for conversations?
- **Check:** storyboard_sN.md — dialogue scenes use OTS framing.
- **Pass:** two-character dialogue uses medium or OTS shots.
- **Fail:** dialogue shot in closeup only (no spatial relationship).

### Q2.15 — Is shot variety maintained across the full scene?
- **Check:** storyboard_sN.md — all generations in a scene don't repeat the same size pattern.
- **Pass:** different generations use different shot size distributions.
- **Fail:** every generation uses the same size sequence (monotonous).

### Q2.16 — Are inserts and detail shots used for key objects?
- **Check:** storyboard_sN.md — hero props get insert shots.
- **Pass:** important objects (from scenes.md `objects:`) get at least one detail shot.
- **Fail:** hero props never get a close-up insert (audience misses them).

### Q2.17 — Does the shot count match the panel grid?
- **Check:** storyboard_sN.md — panels are distributed across shots logically.
- **Pass:** each shot claims 1-4 panels and all panels are used.
- **Fail:** panels unused or a shot claims more panels than it needs.

### Q2.18 — Are two-shots used for relationship moments?
- **Check:** storyboard_sN.md — key relationship beats use two-shots.
- **Pass:** medium or wide two-shots when two characters interact meaningfully.
- **Fail:** two-character interaction always in singles (no relationship framing).

### Q2.19 — Is the camera angle (high/low/dutch) used intentionally?
- **Check:** storyboard_sN.md — angle choices serve the story.
- **Pass:** low angle for power, high angle for vulnerability, dutch for unease.
- **Fail:** angle choices are random or contradict the emotional intent.

### Q2.20 — Are extreme close-ups reserved for peak moments?
- **Check:** storyboard_sN.md — extreme_closeup is rare and impactful.
- **Pass:** extreme_closeup used at most 1-2 times per scene, at peak emotion.
- **Fail:** extreme_closeup overused (loses impact).

### Q2.21 — Does each generation have a visual rhythm?
- **Check:** storyboard_sN.md — shot durations create a rhythm within each generation.
- **Pass:** shot durations vary to create rhythm (fast-slow-fast or building).
- **Fail:** all shots the same duration (mechanical, no rhythm).

### Q2.22 — Are wide shots used to show spatial relationships?
- **Check:** storyboard_sN.md — wide shots establish where characters are relative to each other.
- **Pass:** wide shots appear before close-ups of the same space.
- **Fail:** close-ups without any wide context for spatial relationships.

### Q2.23 — Is the 3/4 front angle used as the workhorse?
- **Check:** storyboard_sN.md — most character shots use 3/4 front, not flat front or profile.
- **Pass:** 3/4 front is the default; flat front and profile are intentional variations.
- **Fail:** all shots are flat front (no depth) or all profile (no face).

### Q2.24 — Are character entrances given proper shots?
- **Check:** storyboard_sN.md — when a character enters, they get a recognizable shot.
- **Pass:** new characters get a clear medium or full shot on first appearance.
- **Fail:** new characters appear in closeup (audience can't identify them).

### Q2.25 — Are exits given proper shots?
- **Check:** storyboard_sN.md — when a character exits, the shot holds on the empty space or follows them out.
- **Pass:** exits are shown, not implied.
- **Fail:** characters disappear between shots (no exit shown).

### Q2.26 — Is the shot design consistent with the genre?
- **Check:** storyboard_sN.md — shot choices match the story's genre and tone.
- **Pass:** action stories have fast cuts; drama has longer holds; comedy has reaction beats.
- **Fail:** shot design contradicts genre (slow cuts in an action scene).

### Q2.27 — Are group shots handled correctly?
- **Check:** storyboard_sN.md — scenes with 3+ characters use appropriate group framing.
- **Pass:** wide or medium shots establish the group before singles.
- **Fail:** group scenes only in close-ups (audience can't track who's where).

### Q2.28 — Does the first shot of each generation continue from the last?
- **Check:** storyboard_sN.md — generation boundaries use `continuous` or motivated `hard_cut`.
- **Pass:** first shot of gK+1 continues from gK or cuts for a reason.
- **Fail:** generation boundary is an arbitrary cut with no motivation.

### Q2.29 — Are objects given screen time proportional to their importance?
- **Check:** storyboard_sN.md — hero props get more panel time than background dressing.
- **Pass:** key objects get inserts or featured panels; background gets less.
- **Fail:** important objects barely visible while background dominates.

### Q2.30 — Is the final shot of the scene memorable?
- **Check:** storyboard_sN.md — the last shot before the handoff is visually strong.
- **Pass:** the scene ends on a striking image or emotional beat.
- **Fail:** the scene ends on a forgettable shot.

---

## Section 3: Camera Movement (30 questions)

### Q3.1 — Does every camera move have a story motivation?
- **Check:** storyboard_sN.md — each shot's `camera:` field has a reason rooted in the story.
- **Pass:** push in for realization, tracking for pursuit, arc for revelation.
- **Fail:** camera moves without motivation ("cool" movement).

### Q3.2 — Are there static shots where the action carries the frame?
- **Check:** storyboard_sN.md — not every shot has camera movement.
- **Pass:** some shots use Static Shot to let the action carry the frame.
- **Fail:** every shot has camera movement (exhausting, no stillness).

### Q3.3 — Is the camera vocabulary from the Minimax H3 motion set?
- **Check:** storyboard_sN.md — camera: fields use Minimax terms (Push In, Tracking Shot, etc.).
- **Pass:** camera descriptions use recognized Minimax motion vocabulary.
- **Fail:** camera uses terms Minimax doesn't understand (structurally warned).

### Q3.4 — Are push-ins reserved for realization/growing emotion?
- **Check:** storyboard_sN.md — Push In appears at moments of realization or emotional intensity.
- **Pass:** push in used when the character learns something or feels deeply.
- **Fail:** push in used for default movement (devalued).

### Q3.5 — Are tracking shots used for pursuit/following?
- **Check:** storyboard_sN.md — Tracking Shot appears when following action.
- **Pass:** tracking used for chase, following, or building tension.
- **Fail:** tracking used in static dialogue (wrong tool).

### Q3.6 — Is whip pan reserved for energy/urgency/transition?
- **Check:** storyboard_sN.md — Whip Pan appears at high-energy moments or bridge transitions.
- **Pass:** whip pan used for urgency, surprise, or bridge masking.
- **Fail:** whip pan used casually (loses energy impact).

### Q3.7 — Are arc shots used for revelation?
- **Check:** storyboard_sN.md — Arc Shot appears when revealing something new.
- **Pass:** arc used to circle and reveal a subject or space.
- **Fail:** arc used without a reveal purpose.

### Q3.8 — Are crane/pedestal moves used for scale change?
- **Check:** storyboard_sN.md — Crane or Pedestal appears for grandeur or scale shifts.
- **Pass:** crane up for liberation/scale; pedestal down for descent/intimacy.
- **Fail:** crane/pedestal used without scale or emotional purpose.

### Q3.9 — Is handheld used for chaos/immediacy?
- **Check:** storyboard_sN.md — Shake/handheld appears at chaotic or urgent moments.
- **Pass:** handheld/shake used for danger, chaos, documentary feel.
- **Fail:** handheld used in calm scenes (wrong energy).

### Q3.10 — Are multi-move shots coherent?
- **Check:** storyboard_sN.md — shots with multiple camera moves flow logically.
- **Pass:** multi-move shots sequence naturally (track then arc, push then static).
- **Fail:** multi-move shots with contradictory movements (pan left then pan right for no reason).

### Q3.11 — Does the camera speed match the action speed?
- **Check:** storyboard_sN.md — camera speed (slow/fast) matches the action's energy.
- **Pass:** fast camera for fast action; slow camera for tender moments.
- **Fail:** fast camera in a tender scene or slow camera in a chase.

### Q3.12 — Is camera movement varied across the generation?
- **Check:** storyboard_sN.md — not all shots in a generation use the same camera move.
- **Pass:** at least 3 distinct camera moves in a generation with 5+ shots.
- **Fail:** all shots use the same move (e.g., all Push In).

### Q3.13 — Are zoom shots used intentionally?
- **Check:** storyboard_sN.md — Zoom In/Out is used for stylistic effect, not as default.
- **Pass:** zoom used for deliberate stylistic emphasis or snap-zoom energy.
- **Fail:** zoom used as a lazy substitute for push in (less cinematic).

### Q3.14 — Does the camera lead or follow the subject?
- **Check:** storyboard_sN.md — tracking shots lead or follow intentionally.
- **Pass:** camera leads for anticipation; follows for pursuit.
- **Fail:** camera position relative to subject is unclear or inconsistent.

### Q3.15 — Are tilt shots used for vertical reveals?
- **Check:** storyboard_sN.md — Tilt Up/Down reveals something above or below.
- **Pass:** tilt used to reveal height, scale, or vertical motion.
- **Fail:** tilt used where a pan or push would be better.

### Q3.16 — Is the camera movement motivated by the character's gaze?
- **Check:** storyboard_sN.md — camera follows what the character looks at.
- **Pass:** camera moves to discover what the character sees.
- **Fail:** camera moves independently of character attention.

### Q3.17 — Does the camera breathe during tender moments?
- **Check:** storyboard_sN.md — tender shots have subtle, slow camera movement.
- **Pass:** tender beats use slow push in or static with subtle shake.
- **Fail:** tender beats have aggressive camera movement (undermines tenderness).

### Q3.18 — Are POV shots marked as POV in the camera field?
- **Check:** storyboard_sN.md — POV shots use the POV camera term.
- **Pass:** POV shots explicitly say "POV" in the camera: field.
- **Fail:** POV shots described without the POV term (ambiguous).

### Q3.19 — Does the camera establish depth in the frame?
- **Check:** storyboard_sN.md — camera positions create foreground/midground/background depth.
- **Pass:** tracking, arc, or angled shots create parallax and depth.
- **Fail:** all shots are flat front-on (no depth, no dimensionality).

### Q3.20 — Is the camera movement consistent within a shot?
- **Check:** storyboard_sN.md — each shot's camera move is coherent, not contradictory.
- **Pass:** camera does one thing or transitions smoothly between moves.
- **Fail:** camera description lists contradictory moves (pan left AND pan right).

### Q3.21 — Are roll shots used for disorientation?
- **Check:** storyboard_sN.md — Roll Clockwise/Counterclockwise is rare and intentional.
- **Pass:** roll used for dizziness, disorientation, or stylistic impact.
- **Fail:** roll used casually (disorienting without purpose).

### Q3.22 — Does the camera respect the 180° line?
- **Check:** storyboard_sN.md — camera doesn't cross the action axis between shots.
- **Pass:** camera stays on one side of the action line across cuts.
- **Fail:** camera crosses the line (characters flip direction — disorienting).

### Q3.23 — Are truck shots used for lateral movement?
- **Check:** storyboard_sN.md — Truck Left/Right is used for lateral following or parallel action.
- **Pass:** truck used for side-by-side movement or lateral reveal.
- **Fail:** truck used where tracking or pan would be better.

### Q3.24 — Does the camera movement escalate with the story?
- **Check:** storyboard_sN.md — camera energy increases as tension builds.
- **Pass:** calm camera early; more dynamic camera as tension rises.
- **Fail:** camera energy is flat across the scene (doesn't build).

### Q3.25 — Is the final camera move of the scene memorable?
- **Check:** storyboard_sN.md — the last shot's camera move is striking.
- **Pass:** the scene ends on a strong camera move (push in to face, crane up to sky).
- **Fail:** the scene ends on a static or forgettable camera move.

### Q3.26 — Does each generation after g1 open as a continuation?
- **Check:** storyboard_sN.md — g(K+1) shot 1 action describes continuing
  from the previous generation's ending state.
- **Pass:** each generation after g1 opens as a natural continuation.
- **Fail:** generation openings ignore the previous generation's ending.

### Q3.27 — Does the camera avoid unmotivated zooms during dialogue?
- **Check:** storyboard_sN.md — dialogue scenes don't use zoom.
- **Pass:** dialogue uses push in (motivated) or static, not zoom.
- **Fail:** zoom during dialogue (feels cheap, not cinematic).

### Q3.28 — Is camera shake amplitude appropriate?
- **Check:** storyboard_sN.md — Shake Slightly vs Shake Strongly matches the moment.
- **Pass:** slight shake for tension; strong shake for chaos/impact.
- **Fail:** strong shake in a calm scene or slight shake in chaos.

### Q3.29 — Are camera moves described with amplitude and speed?
- **Check:** storyboard_sN.md — camera moves include "with small/large amplitude" and "at slow/fast speed" where relevant.
- **Pass:** key moves specify amplitude and speed for Minimax precision.
- **Fail:** camera moves lack amplitude/speed qualifiers (vague for the model).

### Q3.30 — Does the camera rest at the end of a move?
- **Check:** storyboard_sN.md — multi-move shots end on a held frame.
- **Pass:** camera moves then settles (e.g., "track then hold on face").
- **Fail:** camera is always moving, never settles (no rest points).

---

## Section 4: Composition (30 questions)

### Q4.1 — Does every shot have one clear subject?
- **Check:** storyboard_sN.md — each shot's composition: and action: name one clear subject.
- **Pass:** the audience knows where to look in every shot.
- **Fail:** any shot with competing subjects or no clear subject.

### Q4.2 — Is screen direction maintained across cuts (180° rule)?
- **Check:** storyboard_sN.md — characters face the same direction across cuts.
- **Pass:** screen_direction is consistent; no axis jumps.
- **Fail:** characters flip facing direction across cuts.

### Q4.3 — Are leading lines used to guide the eye?
- **Check:** storyboard_sN.md — composition: includes leading_lines where architecture or environment guides the eye.
- **Pass:** leading lines used in shots with roads, corridors, shadows.
- **Fail:** leading lines available but never used.

### Q4.4 — Is negative space used for isolation/scale?
- **Check:** storyboard_sN.md — composition: includes negative_space for lonely or small moments.
- **Pass:** negative space used when the character is isolated or overwhelmed.
- **Fail:** frames are always busy (no breathing room for isolation beats).

### Q4.5 — Is composition varied across the generation?
- **Check:** storyboard_sN.md — not all shots share the same composition values.
- **Pass:** at least 3 distinct composition values in a generation with 5+ shots.
- **Fail:** all shots use the same composition (e.g., all rule_of_thirds).

### Q4.6 — Is visual_hierarchy used to make subjects unmissable?
- **Check:** storyboard_sN.md — composition: includes visual_hierarchy for key subject shots.
- **Pass:** visual_hierarchy used when the subject needs to be unmissable.
- **Fail:** key subjects compete with background (no hierarchy).

### Q4.7 — Is rule_of_thirds used as the default?
- **Check:** storyboard_sN.md — rule_of_thirds is the most common composition.
- **Pass:** rule_of_thirds used for most shots; other compositions are intentional deviations.
- **Fail:** rule_of_thirds never used or used for everything (no variety).

### Q4.8 — Is center composition used for focus/formality?
- **Check:** storyboard_sN.md — center composition used for iconic or formal moments.
- **Pass:** center used for hero shots, symmetry, or product reveals.
- **Fail:** center never used (missed iconic framing) or overused (static).

### Q4.9 — Is symmetry used for order/ritual/fairy-tale?
- **Check:** storyboard_sN.md — symmetry composition used at appropriate moments.
- **Pass:** symmetry used for formal, ritual, or otherworldly moments.
- **Fail:** symmetry used randomly or never (missed opportunity).

### Q4.10 — Is depth used for immersion?
- **Check:** storyboard_sN.md — composition: includes depth for immersive shots.
- **Pass:** depth used in shots with foreground/midground/background layers.
- **Fail:** all shots are flat (no depth, no parallax).

### Q4.11 — Is silhouette used for mystery/drama?
- **Check:** storyboard_sN.md — silhouette composition used for dramatic backlight moments.
- **Pass:** silhouette used at dramatic or mysterious moments.
- **Fail:** silhouette never used (missed dramatic tool).

### Q4.12 — Is frame_within_frame used for voyeurism/confinement?
- **Check:** storyboard_sN.md — frame_within_frame used for doorways, windows, arches.
- **Pass:** frame_within_frame used when characters are framed by architecture.
- **Fail:** frame_within_frame never used (missed compositional tool).

### Q4.13 — Is headroom balanced?
- **Check:** storyboard_sN.md — composition: includes headroom where relevant.
- **Pass:** headroom noted when character framing is tight.
- **Fail:** headroom never considered (characters float or are cramped).

### Q4.14 — Is look_room provided in the direction the character looks?
- **Check:** storyboard_sN.md — composition: includes look_room where relevant.
- **Pass:** look_room noted when characters look off-screen.
- **Fail:** characters look into the edge of the frame (no look_room).

### Q4.15 — Does the composition serve the emotion?
- **Check:** storyboard_sN.md — composition choices match the shot's emotional intent.
- **Pass:** negative_space for loneliness, center for power, depth for immersion.
- **Fail:** composition contradicts emotion (busy frame for isolation).

### Q4.16 — Are composition values from the 12-value taxonomy?
- **Check:** storyboard_sN.md — all composition: values are from the declared set.
- **Pass:** all values are valid (structurally validated).
- **Fail:** invalid values (should already be caught by the structural validator).

### Q4.17 — Is the composition intentional, not accidental?
- **Check:** storyboard_sN.md — composition: field is present and considered.
- **Pass:** every shot has a composition: field with intentional choices.
- **Fail:** composition: missing or generic (no thought).

### Q4.18 — Does the composition guide the eye to the story element?
- **Check:** storyboard_sN.md — composition draws attention to the key element in the shot.
- **Pass:** leading lines, visual hierarchy, or lighting draw the eye to the subject.
- **Fail:** composition doesn't guide the eye (audience doesn't know where to look).

### Q4.19 — Is the composition consistent within a shot?
- **Check:** storyboard_sN.md — a shot's composition values are compatible.
- **Pass:** composition values work together (rule_of_thirds + leading_lines).
- **Fail:** contradictory composition values (center + rule_of_thirds).

### Q4.20 — Are key reveals composed for maximum impact?
- **Check:** storyboard_sN.md — reveal shots use composition that maximizes the reveal.
- **Pass:** reveals use center, visual_hierarchy, or negative_space for impact.
- **Fail:** reveals use generic composition (underwhelming).

### Q4.21 — Is the composition varied across the scene?
- **Check:** storyboard_sN.md — composition differs across generations.
- **Pass:** different generations use different composition patterns.
- **Fail:** every generation uses the same composition (monotonous).

### Q4.22 — Does the composition support the shot_size?
- **Check:** storyboard_sN.md — composition and shot_size work together.
- **Pass:** wide + leading_lines, closeup + center, medium + rule_of_thirds.
- **Fail:** composition fights the shot_size (wide + center, closeup + negative_space).

### Q4.23 — Is the horizon line level (no accidental tilts)?
- **Check:** storyboard_sN.md — no dutch angle unless intentionally composed.
- **Pass:** dutch angle only used for unease/tension; otherwise level.
- **Fail:** accidental tilts or dutch angle overused.

### Q4.24 — Are group shots composed with clear hierarchy?
- **Check:** storyboard_sN.md — group shots use visual_hierarchy to rank characters.
- **Pass:** the most important character is visually dominant in group shots.
- **Fail:** group shots with no hierarchy (all characters equal weight).

### Q4.25 — Does the composition create visual tension where needed?
- **Check:** storyboard_sN.md — tense moments use composition that creates unease.
- **Pass:** tension uses dutch angle, negative_space, or off-center framing.
- **Fail:** tense moments use calm composition (undermines tension).

### Q4.26 — Is the composition clean (no distracting elements)?
- **Check:** storyboard_sN.md — action: and composition: don't describe cluttered frames.
- **Pass:** frames are clean with one clear subject and minimal distraction.
- **Fail:** frames described with too many competing elements.

### Q4.27 — Does the composition use foreground elements for depth?
- **Check:** storyboard_sN.md — depth composition includes foreground elements.
- **Pass:** foreground objects (leaves, doorways, props) create depth.
- **Fail:** no foreground elements (flat composition).

### Q4.28 — Is the composition appropriate for the Minimax H3 backend?
- **Check:** storyboard_sN.md — composition is achievable in a single 4K sheet panel.
- **Pass:** composition is simple enough to render clearly in a panel.
- **Fail:** composition too complex for a single panel (split-focus, too many elements).

### Q4.29 — Does the composition evolve across the scene?
- **Check:** storyboard_sN.md — composition shifts as the story progresses.
- **Pass:** early shots use one pattern; later shots shift as emotion changes.
- **Fail:** composition is static across the entire scene.

### Q4.30 — Is the final shot composed for memorability?
- **Check:** storyboard_sN.md — the last shot uses a strong composition.
- **Pass:** final shot uses center, symmetry, or visual_hierarchy for an iconic image.
- **Fail:** final shot uses generic composition (forgettable ending).

---

## Section 5: Editing & Cuts (24 questions)

### Q5.1 — Does every cut answer a question or reveal new information?
- **Check:** storyboard_sN.md — each cut is motivated (new subject, space, state, viewpoint, or time).
- **Pass:** every cut adds new information.
- **Fail:** any cut that only changes framing (should be camera_move).

### Q5.2 — Are transitions varied (not all hard_cut)?
- **Check:** storyboard_sN.md — transition types are mixed within generations.
- **Pass:** at least 3 distinct transitions in a generation with 5+ shots.
- **Fail:** all transitions are hard_cut (structurally warned).

### Q5.3 — Are cut_on_action and reaction_cut used for same-character boundaries?
- **Check:** storyboard_sN.md — same-character cuts use cut_on_action or reaction_cut, not hard_cut.
- **Pass:** same-character boundaries use motivated transitions.
- **Fail:** same-character boundaries use hard_cut (structurally errored when shot_size matches).

### Q5.4 — Is match_cut used with named elements?
- **Check:** storyboard_sN.md — match_cut shots name the matched element in action:.
- **Pass:** match cut references a specific element ("Match cut on the falling tin").
- **Fail:** match_cut without naming the element (structurally errored).

### Q5.5 — Is audio_led used with non-empty audio?
- **Check:** storyboard_sN.md — audio_led shots have audio: content.
- **Pass:** audio_led shots have sound that leads the cut.
- **Fail:** audio_led without audio content (structurally errored).

### Q5.6 — Is the first shot of each generation continuous or motivated?
- **Check:** storyboard_sN.md — generation boundaries use continuous or a motivated cut.
- **Pass:** first shot of gK+1 continues from gK or cuts for a clear reason.
- **Fail:** generation boundary is an arbitrary hard_cut.

### Q5.7 — Does the editing rhythm match the story pacing?
- **Check:** storyboard_sN.md — shot durations create a rhythm that matches the beat's emotion.
- **Pass:** fast cuts for action, slow cuts for tenderness, held shots for tension.
- **Fail:** editing rhythm contradicts the story pacing.

### Q5.8 — Are reaction shots cut at the right moment?
- **Check:** storyboard_sN.md — reaction cuts come after the stimulus, not before.
- **Pass:** reaction_cut appears after the action that causes the reaction.
- **Fail:** reaction shots before the stimulus (confusing timeline).

### Q5.9 — Is cross-cutting used for parallel action?
- **Check:** storyboard_sN.md — parallel storylines are intercut across generations.
- **Pass:** cross-cutting used when two storylines need to be shown simultaneously.
- **Fail:** parallel action shown sequentially (loses tension).

### Q5.10 — Are cutaways used for context?
- **Check:** storyboard_sN.md — cutaway shots provide context outside the main action.
- **Pass:** cutaways used to show environment, other characters, or consequences.
- **Fail:** no cutaways (missed context opportunities).

### Q5.11 — Are insert shots used for key details?
- **Check:** storyboard_sN.md — insert shots show important objects or details.
- **Pass:** inserts used for hero props, key expressions, or critical details.
- **Fail:** important details never get insert shots.

### Q5.12 — Does the editing build tension through acceleration?
- **Check:** storyboard_sN.md — shot durations shorten as tension builds.
- **Pass:** shots get progressively shorter toward a climax.
- **Fail:** shot durations are flat during a tension build.

### Q5.13 — Does the editing release tension through deceleration?
- **Check:** storyboard_sN.md — after a climax, shots lengthen.
- **Pass:** post-climax shots are longer (breathing room).
- **Fail:** fast cutting continues after the climax (no release).

### Q5.14 — Are smash cuts used for extreme contrast?
- **Check:** storyboard_sN.md — smash cuts (quiet to loud, calm to chaos) are used intentionally.
- **Pass:** smash cuts used at key tonal shifts.
- **Fail:** no smash cuts at obvious contrast moments (missed impact).

### Q5.15 — Is the scene-end handoff present?
- **Check:** storyboard_sN.md — every scene has a `## Scene-end handoff` block.
- **Pass:** handoff block is present with on_screen, mood, transition.
- **Fail:** handoff missing (structurally errored).

### Q5.16 — Does the handoff transition match the scene boundary?
- **Check:** storyboard_sN.md — handoff transition (hard_cut, match_cut) fits the scene change.
- **Pass:** handoff transition is appropriate for the scene boundary.
- **Fail:** handoff transition contradicts the scene change style.

### Q5.17 — Are L-cuts and J-cuts used at scene boundaries?
- **Check:** storyboard_sN.md — audio_led transitions used for sound bridges.
- **Pass:** audio_led used to bridge audio across scene/generation boundaries.
- **Fail:** no audio bridges at boundaries (harder transitions).

### Q5.18 — Is the editing clean (no unnecessary cuts)?
- **Check:** storyboard_sN.md — every cut is motivated; no wasted cuts.
- **Pass:** removing any cut would lose information.
- **Fail:** cuts that don't add information (should be camera_move).

### Q5.19 — Does the editing respect the 15s generation limit?
- **Check:** storyboard_sN.md — no shot straddles a generation boundary.
- **Pass:** shots that don't fit move to the next generation (structurally validated).
- **Fail:** shots straddling boundaries (structurally errored).

### Q5.20 — Are panels assigned in reading order?
- **Check:** storyboard_sN.md — panels are numbered 1..N in reading order across shots.
- **Pass:** panels follow reading order (structurally validated).
- **Fail:** panels out of order (structurally errored).

### Q5.21 — Is the panel grid appropriate for the shot count?
- **Check:** storyboard_sN.md — panel_grid gives enough panels for the shots.
- **Pass:** grid size matches the number of key poses needed.
- **Fail:** grid too small (not enough panels) or too large (wasted panels).

### Q5.22 — Are key poses shown in the panels?
- **Check:** storyboard_sN.md — each shot's panels show its key poses.
- **Pass:** panels capture the start, middle, and end of the shot's action.
- **Fail:** panels don't show the key moments (missing poses).

### Q5.23 — Does the editing create a clear visual flow?
- **Check:** storyboard_sN.md — shots flow logically from one to the next.
- **Pass:** each shot follows naturally from the previous (spatial, temporal, emotional).
- **Fail:** shots feel disconnected (no visual flow).

### Q5.24 — Is the final cut of the scene impactful?
- **Check:** storyboard_sN.md — the last cut before the handoff is strong.
- **Pass:** the scene ends on a decisive cut or continuous hold.
- **Fail:** the scene ends on a weak or arbitrary cut.

---

## Section 6: Animation Direction (25 questions)

### Q6.1 — Is action: written as micro-beats, not single verbs?
- **Check:** storyboard_sN.md — each shot's action: is a sequence of micro-beats.
- **Pass:** "freezes, eyes dart, head turns, body follows, mouth drops open."
- **Fail:** "The baby turns around." (single verb, no micro-beats).

### Q6.2 — Does each shot have anticipation, action, and follow-through?
- **Check:** storyboard_sN.md — action: describes wind-up, the action, and the aftermath.
- **Pass:** anticipation (crouch) → action (jump) → follow-through (land, hair swings).
- **Fail:** only the action is described, no anticipation or follow-through.

### Q6.3 — Are character reactions timed (stimulus → pause → response)?
- **Check:** storyboard_sN.md — reactions have a beat between stimulus and response.
- **Pass:** "hears sound → freezes → eyes move → head turns."
- **Fail:** instant reaction with no processing beat (feels mechanical).

### Q6.4 — Do eyes lead, then brows, then mouth in reaction shots?
- **Check:** storyboard_sN.md — facial reactions are sequenced.
- **Pass:** "eyes widen, brows rise, mouth drops open."
- **Fail:** "face reacts" (no sequence, no detail).

### Q6.5 — Is secondary motion described (cloth, hair, ears)?
- **Check:** storyboard_sN.md — action: includes secondary motion for key movements.
- **Pass:** "hair swings after the head turn; cloth billows on the landing."
- **Fail:** no secondary motion described (animation feels stiff).

### Q6.6 — Is weight conveyed through movement description?
- **Check:** storyboard_sN.md — heavy things move slowly, light things fast.
- **Pass:** "the heavy tin thuds down; the light feather floats."
- **Fail:** all objects move at the same implied speed (no weight).

### Q6.7 — Is exaggeration used for emotional clarity?
- **Check:** storyboard_sN.md — poses and expressions are pushed beyond realism.
- **Pass:** "eyes widen impossibly large; jaw drops to chest."
- **Fail:** realistic, understated animation (less expressive in animation).

### Q6.8 — Is squash & stretch described for impacts?
- **Check:** storyboard_sN.md — impact moments include deformation.
- **Pass:** "the tin squashes on impact, then bounces back."
- **Fail:** impacts described without deformation (less dynamic).

### Q6.9 — Is timing (ease in/ease out) implied in the action?
- **Check:** storyboard_sN.md — action: implies acceleration/deceleration.
- **Pass:** "starts slow, accelerates, slams to a stop."
- **Fail:** linear motion descriptions ("moves from A to B").

### Q6.10 — Are character entrances animated with personality?
- **Check:** storyboard_sN.md — new characters enter with a distinctive movement.
- **Pass:** "the hyena slinks in low, shoulders rolling, ears flat."
- **Fail:** characters enter with no personality ("the hyena walks in").

### Q6.11 — Are character exits animated with purpose?
- **Check:** storyboard_sN.md — exits show how the character leaves.
- **Pass:** "Kemi sprints out of frame, dust kicking up behind her."
- **Fail:** characters just disappear ("Kemi leaves").

### Q6.12 — Is the protagonist's body language consistent?
- **Check:** storyboard_sN.md — the protagonist moves consistently across shots.
- **Pass:** Kemi's movement style (agile, martial, protective) is consistent.
- **Fail:** the protagonist's movement style changes between shots.

### Q6.13 — Are group animations choreographed?
- **Check:** storyboard_sN.md — group scenes have coordinated movement.
- **Pass:** "the animals scatter in different directions, vines swinging."
- **Fail:** group scenes described as "animals move" (no choreography).

### Q6.14 — Is the animation matched to the shot duration?
- **Check:** storyboard_sN.md — the action described fits the shot's time range.
- **Pass:** a 1.5s shot has a simple action; a 6s shot has a complex sequence.
- **Fail:** too much action for a short shot or too little for a long one.

### Q6.15 — Are emotional transitions animated?
- **Check:** storyboard_sN.md — emotion changes are shown through animation.
- **Pass:** "smile fades, eyes narrow, jaw sets."
- **Fail:** emotion changes stated but not animated ("she becomes angry").

### Q6.16 — Is the animation physical (grounded in physics)?
- **Check:** storyboard_sN.md — movements respect gravity, momentum, and mass.
- **Pass:** jumps have arcs, landings have impact, falls accelerate.
- **Fail:** physics-defying movement without explanation (floating, instant stops).

### Q6.17 — Are key actions given enough screen time?
- **Check:** storyboard_sN.md — important actions get enough seconds to read.
- **Pass:** key actions have 2+ seconds to be visible.
- **Fail:** important actions in 0.5s shots (too fast to read).

### Q6.18 — Is the animation varied across shots?
- **Check:** storyboard_sN.md — not every shot uses the same movement vocabulary.
- **Pass:** shots have distinct movements (one runs, one jumps, one ducks).
- **Fail:** repetitive movement across shots (all running, all standing).

### Q6.19 — Are environmental animations described?
- **Check:** storyboard_sN.md — the environment reacts to the action.
- **Pass:** "leaves scatter, dust kicks up, water splashes."
- **Fail:** environment is static (no reaction to character action).

### Q6.20 — Are object animations described?
- **Check:** storyboard_sN.md — hero props have their own animation.
- **Pass:** "the tin spins, catches light, wobbles, settles."
- **Fail:** objects are static props with no animation.

### Q6.21 — Is the climax animation the most dynamic?
- **Check:** storyboard_sN.md — the climax shot has the most dynamic animation.
- **Pass:** climax has the biggest, most exaggerated, most detailed animation.
- **Fail:** climax animation is no more dynamic than other shots.

### Q6.22 — Are quiet moments animated with subtlety?
- **Check:** storyboard_sN.md — tender/quiet moments have subtle animation.
- **Pass:** "chest rises and falls slowly; eyes blink; fingers relax."
- **Fail:** quiet moments have no animation description (feels dead).

### Q6.23 — Is the animation appropriate for the character's personality?
- **Check:** storyboard_sN.md — each character moves in their own way.
- **Pass:** the hyena moves differently from Kemi; the baby differently from both.
- **Fail:** all characters move the same way (no personality in movement).

### Q6.24 — Are transitions between actions smooth?
- **Check:** storyboard_sN.md — action: sequences flow from one beat to the next.
- **Pass:** "ducks, rolls, comes up swinging" (connected sequence).
- **Fail:** disconnected actions ("ducks. Then swings." — no flow).

### Q6.25 — Is the final animation beat of the scene memorable?
- **Check:** storyboard_sN.md — the last shot's action is iconic.
- **Pass:** "Kemi slides to a hero stop, tin raised high, dust settling."
- **Fail:** the last shot's action is forgettable.

---

## Section 7: Sound & Editing (25 questions)

### Q7.1 — Does every shot have audio direction?
- **Check:** storyboard_sN.md — each shot has a non-empty `audio:` field.
- **Pass:** every shot has foley, ambient, or impact sound described.
- **Fail:** any shot with empty audio: (Minimax will invent random sound).

### Q7.2 — Are silence and impact sounds used intentionally?
- **Check:** storyboard_sN.md — silence appears before reveals; impacts at action peaks.
- **Pass:** "dead silence" before a reveal; "sharp crack" at impact.
- **Fail:** no silence used (missed tension tool) or no impacts (action feels soft).

### Q7.3 — Does music synchronization land on emotional peaks?
- **Check:** storyboard_sN.md — music hits align with the shot's emotional peak.
- **Pass:** "warm strings swell on the reveal" or "percussion hits on the impact."
- **Fail:** music described without timing to the emotional peak.

### Q7.4 — Are foley, ambient, and impact layers all present?
- **Check:** storyboard_sN.md — across the scene, all three sound layers appear.
- **Pass:** footsteps (foley), wind/room tone (ambient), crashes (impact) all present.
- **Fail:** only one layer used (e.g., all ambient, no foley or impact).

### Q7.5 — Are sound bridges used at scene transitions?
- **Check:** storyboard_sN.md — audio_led transitions bridge audio across boundaries.
- **Pass:** audio from the next scene starts before the visual cut.
- **Fail:** no sound bridges (harder scene transitions).

### Q7.6 — Is dialogue quoted inline where it happens?
- **Check:** storyboard_sN.md — dialogue: field has `cid: "line"` format.
- **Pass:** dialogue is in the dialogue: field at the right shot.
- **Fail:** dialogue described in action: instead of dialogue: (structurally wrong).

### Q7.7 — Is dialogue kept short for lip-sync?
- **Check:** storyboard_sN.md — dialogue lines are short enough for Minimax to lip-sync.
- **Pass:** lines are 1-8 words; long speeches are split across shots.
- **Fail:** long monologues in a single shot (lip-sync will fail).

### Q7.8 — Are speaker IDs stable in dialogue?
- **Check:** storyboard_sN.md — dialogue uses consistent cid: prefixes.
- **Pass:** "char_01: "Hello"" — stable character ids.
- **Fail:** inconsistent speaker ids or missing speaker labels.

### Q7.9 — Is ambient sound matched to the location?
- **Check:** storyboard_sN.md — ambient sound matches the location_id.
- **Pass:** jungle location has birds, insects, wind; city has traffic, crowd.
- **Fail:** ambient sound doesn't match the location (jungle with car traffic).

### Q7.10 — Does the soundscape evolve across the scene?
- **Check:** storyboard_sN.md — ambient sound changes as the scene progresses.
- **Pass:** "birds singing" → "silence" → "snarling" as threat appears.
- **Fail:** ambient sound is constant across the entire scene.

### Q7.11 — Are footsteps described for walking/running shots?
- **Check:** storyboard_sN.md — movement shots include footstep foley.
- **Pass:** "soft padding footsteps" or "heavy boots on gravel."
- **Fail:** movement shots with no footstep sound (feels detached).

### Q7.12 — Are fabric/cloth sounds described for action?
- **Check:** storyboard_sN.md — action shots include fabric foley.
- **Pass:** "fabric rustles, wrap flutters" during movement.
- **Fail:** action shots with no fabric sound (less tactile).

### Q7.13 — Are impact sounds specific, not generic?
- **Check:** storyboard_sN.md — impacts are described specifically.
- **Pass:** "metallic BONK on the hyena's head" not just "a sound."
- **Fail:** generic impact sounds ("bang", "crash" without detail).

### Q7.14 — Is non-diegetic music described in video prompts?
- **Check:** video_prompts/ — non_diegetic_music section is filled.
- **Pass:** score described with instrumentation, tempo, dynamics.
- **Fail:** non_diegetic_music is "N/A" when the scene clearly needs score.

### Q7.15 — Is the overall soundscape described in video prompts?
- **Check:** video_prompts/ — overall_soundscape section is filled.
- **Pass:** soundscape describes the full generation's audio environment.
- **Fail:** overall_soundscape is empty or generic.

### Q7.16 — Does the audio match the emotional beat?
- **Check:** storyboard_sN.md — audio: content matches the beat's emotion.
- **Pass:** joy → upbeat music; fear → dissonant drone; tension → silence + heartbeat.
- **Fail:** audio contradicts emotion (cheerful music during a fear beat).

### Q7.17 — Are environmental sounds layered?
- **Check:** storyboard_sN.md — audio: includes multiple sound sources.
- **Pass:** "wind through trees, distant bird call, rustling leaves."
- **Fail:** only one sound source per shot (thin soundscape).

### Q7.18 — Is the audio direction actionable for Minimax?
- **Check:** storyboard_sN.md — audio: describes sounds Minimax can generate.
- **Pass:** concrete, describable sounds (footsteps, wind, thunder, dialogue).
- **Fail:** abstract audio ("the sound of despair") that Minimax can't render.

### Q7.19 — Are quiet moments given quiet audio?
- **Check:** storyboard_sN.md — tender/silent beats have soft or no audio.
- **Pass:** "soft breathing, distant wind" for a tender moment.
- **Fail:** loud audio during a tender moment (undermines intimacy).

### Q7.20 — Are loud moments given loud audio?
- **Check:** storyboard_sN.md — action/impact beats have loud audio.
- **Pass:** "thunderous crash, roaring wind, screaming" for chaos.
- **Fail:** quiet audio during a loud moment (underwhelming).

### Q7.21 — Does the audio bridge across generation boundaries?
- **Check:** storyboard_sN.md — the last shot's audio can lead into the next generation.
- **Pass:** audio fades or carries (audio_led) across boundaries.
- **Fail:** hard audio cuts at every generation boundary (jarring).

### Q7.22 — Is music used sparingly (not constant)?
- **Check:** storyboard_sN.md — not every shot has music; music is a tool.
- **Pass:** music appears at key moments; silence/foley fills the rest.
- **Fail:** music described in every shot (wall-to-wall score is exhausting).

### Q7.23 — Are vocal reactions described (gasps, shouts)?
- **Check:** storyboard_sN.md — character vocal sounds are in audio: or dialogue:.
- **Pass:** "toddler gasps" or "Kemi shouts a battle cry."
- **Fail:** characters are silent during action (no vocal reactions).

### Q7.24 — Does the final shot's audio leave a lasting impression?
- **Check:** storyboard_sN.md — the last shot's audio is memorable.
- **Pass:** "triumphant motto resonates" or "music swells to a crescendo."
- **Fail:** the last shot's audio is forgettable.

### Q7.25 — Is the audio consistent with the visual action?
- **Check:** storyboard_sN.md — what we hear matches what we see.
- **Pass:** footsteps when walking, crash when impacting, wind when outside.
- **Fail:** audio doesn't match the visual (footsteps when standing still).

## Section 8: Spatial Continuity (10 questions)

### Q8.1 — Does every scene with a spatial plan define a primary anchor landmark?
- **Check:** spatial_plan_sN.md — `primary_anchor` is set and matches a declared landmark.
- **Pass:** primary anchor is declared and has a `## Landmark` block with `panorama_xy`.
- **Fail:** no primary anchor, or the anchor has no panorama_xy.

### Q8.2 — Are zones non-overlapping in X?
- **Check:** spatial_plan_sN.md — zone `x_range` values do not overlap.
- **Pass:** each zone owns a distinct horizontal slice.
- **Fail:** two zones share X range (ambiguous geography).

### Q8.3 — Does g1 attach the location panorama?
- **Check:** spatial_plan_sN.md — g1 has `location_reference: attach`.
- **Pass:** g1 attaches the location.
- **Fail:** g1 omits the location (no establishing geography).

### Q8.4 — Do later generations omit the location unless re-establishing?
- **Check:** spatial_plan_sN.md — gK (K>1) has `location_reference: omit` unless
  it explicitly re-establishes geography.
- **Pass:** later generations omit, or attach with clear re-establishing reason.
- **Fail:** later generations always attach (defeats the anchor-based continuity).

### Q8.5 — Does every normal generation have a generation_geography?
- **Check:** spatial_plan_sN.md — every `## Generation gK` sets
  `generation_geography:` (or legacy `anchor_view:`) with a non-empty
  staging description.
- **Pass:** all normal generations have a geography description.
- **Fail:** any normal generation missing the geography description.

### Q8.6 — Do character positions fall within their declared zones?
- **Check:** spatial_plan_sN.md — `start_positions` / `end_positions` coordinates
  fall within the zone's x_range / y_range / z_range.
- **Pass:** all positions are inside their zones.
- **Fail:** any position outside its zone (geography violation).

### Q8.7 — Are movement constraints consistent with start/end positions?
- **Check:** spatial_plan_sN.md — `approach(anchor)` → Z decreases;
  `retreat` → Z increases; `fixed_at` → no change.
- **Pass:** constraints match position deltas.
- **Fail:** constraint contradicts the position change.

### Q8.8 — Does every shot have on_screen_positions for all characters_present?
- **Check:** spatial_plan_sN.md — each `### Shot N` has `on_screen_positions`
  covering every `characters_present` from the storyboard.
- **Pass:** all on-screen characters are positioned.
- **Fail:** any character missing a position (spatial ambiguity).

### Q8.9 — Are visible_landmarks honoured per shot?
- **Check:** spatial_plan_sN.md — `visible_landmarks: []` shots should not show
  the landmark; non-empty lists should show the listed landmarks.
- **Pass:** landmark visibility is explicitly declared per shot.
- **Fail:** visibility not declared, or a forbidden landmark appears.

### Q8.10 — Is camera geography consistent across continuous shots?
- **Check:** spatial_plan_sN.md — `camera_zone` and `camera_facing` are declared
  per shot and don't teleport between continuous shots.
- **Pass:** camera geography is consistent or changes only on hard cuts.
- **Fail:** camera jumps zones between continuous shots (jarring geography change).

### Q8.11 — Does every shot declare a camera_zoom level?
- **Check:** spatial_plan_sN.md — each `### Shot N` has a `camera_zoom:` field
  from the 7-value taxonomy (extreme_wide through extreme_closeup).
- **Pass:** every shot has a camera_zoom value.
- **Fail:** any shot missing camera_zoom (spatial framing ambiguity).

### Q8.12 — Is camera_zoom consistent with the storyboard's shot_size?
- **Check:** spatial_plan_sN.md `camera_zoom` vs storyboard_sN.md `shot_size`
  for each shot — they should match or be adjacent on the zoom ladder.
- **Pass:** camera_zoom and shot_size agree or differ by at most 1 step.
- **Fail:** camera_zoom contradicts shot_size (e.g. extreme_wide vs closeup).

### Q8.13 — Does camera_zoom change smoothly within continuous shots?
- **Check:** spatial_plan_sN.md — between continuous shots, camera_zoom does
  not jump more than 2 steps on the ladder.
- **Pass:** zoom changes are gradual within continuous shots.
- **Fail:** zoom jumps abruptly (e.g. extreme_wide → extreme_closeup) within
  a continuous shot sequence (use a cut instead).

### Q8.14 — Does every shot declare character_facing for on-screen characters?
- **Check:** spatial_plan_sN.md — each `### Shot N` has `character_facing:`
  entries for all characters in `on_screen_positions`.
- **Pass:** every on-screen character has a facing direction.
- **Fail:** any on-screen character missing a facing direction (body language
  ambiguity).

### Q8.15 — Are character_facing directions from the valid vocabulary?
- **Check:** spatial_plan_sN.md — `character_facing` values use
  toward_<landmark>, away_from_<landmark>, toward_camera, away_from_camera,
  profile_left, or profile_right.
- **Pass:** all facing values are from the vocabulary.
- **Fail:** any facing value is not recognised (ambiguous direction).

### Q8.16 — Do character_facing directions reference declared landmarks?
- **Check:** spatial_plan_sN.md — `toward_<X>` / `away_from_<X>` references
  match declared landmark IDs.
- **Pass:** all landmark references in facing directions are declared.
- **Fail:** a facing direction references an unknown landmark.

### Q8.17 — Is the 180° rule respected across continuous shots?
- **Check:** spatial_plan_sN.md — between continuous shots, no character
  reverses facing direction (profile_left → profile_right, or
  toward_X → away_from_X).
- **Pass:** facing direction is maintained or changes only on cuts.
- **Fail:** a character reverses facing between continuous shots (180° rule
  violation — disorienting screen direction flip).

### Q8.18 — Does character facing match the dramatic intent?
- **Check:** spatial_plan_sN.md — characters face toward what they're
  reacting to, away from threats they're avoiding, toward camera for
  emotional intimacy.
- **Pass:** facing directions serve the dramatic beat (e.g. character faces
  the approaching threat, faces away when scared).
- **Fail:** facing contradicts the dramatic intent (e.g. character faces
  away from the thing they're supposed to be looking at).

### Q8.19 — Are facing directions consistent with movement constraints?
- **Check:** spatial_plan_sN.md — a character with `approach(lamp_01)` should
  face `toward_lamp_01`; a character retreating should face `away_from_lamp_01`
  or `toward_camera` (if backing away).
- **Pass:** facing aligns with movement direction.
- **Fail:** facing contradicts movement (e.g. approaching a landmark while
  facing away from it).

### Q8.20 — Does the materialized spatial block match the first shot?
- **Check:** storyboard_sheet_gK.txt — the `SPATIAL CONTINUITY LOCK` block's
  first-shot section should match `character_facing` and `camera_zone`
  declared for shot 1 in spatial_plan_sN.md.
- **Pass:** materialized block and first shot spatial state agree.
- **Fail:** materialized block contradicts shot 1's declared spatial state.
