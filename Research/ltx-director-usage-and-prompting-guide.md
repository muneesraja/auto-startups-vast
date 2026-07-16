# LTX Director — Usage & Prompting Guide (Research)

**Date:** 2026-07-16  
**Companion doc:** [ltx-director-api-automation.md](./ltx-director-api-automation.md) (headless `/prompt` schema)  
**Repo workflow:** `workflows/comfyui/LTX_Director_2_Workflow_Hotfix.json`  
**story-maker bible:** `skills/story-maker/assets/ltx-2.3-director-bible.md`

This document synthesizes **official LTX prompting rules**, **WhatDreamsCost / community Director tutorials**, **Prompt Relay** research, and **story-maker** conventions into one practical guide for using LTX Director well.

---

## 1. What LTX Director is

LTX Director is a **ComfyUI custom node** (WhatDreamsCost-ComfyUI v2.x) that turns LTX 2.3 generation into a **non-linear editor**:

- Visual **timeline** with draggable blocks (images, text prompts, audio, motion video)
- Built-in **Prompt Relay** — each time segment gets its own local prompt; cross-attention is routed so events land in the right window
- **Guide keyframes** — any still can anchor the **first, middle, or last** frame (not only classic I2V-at-frame-0)
- **Custom audio** import + **audio inpainting** (blend imported audio with generated gaps)
- **IC-LoRA motion track** (reference video / Ingredients sheet conditioning)
- **Retake mode** (beta) — regenerate a sub-range inside an existing clip
- **Timeline save/load** — JSON export of full editor state

It replaces older WhatDreamsCost nodes (LTX Sequencer, Multi Image Loader, Keyframer) for most workflows. The author recommends **LTX Sequencer over Keyframer** if you still use the legacy nodes.

**Hard dependencies:** updated [ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo) and [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes). Install via ComfyUI Manager (`WhatDreamsCost-ComfyUI`) or `workflows/setup/ltx-23-director-hotfix.sh`.

### Primary references

| Source | URL |
|--------|-----|
| GitHub / README | https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI |
| Prompt Relay (paper + demos) | https://gordonchen19.github.io/Prompt-Relay/ |
| Official LTX prompting | https://docs.ltx.video/api-documentation/implementation-guides/prompting-guide |
| Official I2V API docs | https://docs.ltx.video/api-documentation/api-reference/video-generation/image-to-video |
| WhatDreamsCost tutorial (v1) | https://www.youtube.com/watch?v=vM60pJJqqEI |
| Director 2.0 audio / extend | https://www.youtube.com/watch?v=l2o24m4LLx4 |
| Community timeline write-up | https://awheatsandbox.com/public/guides/ltx-director-comfyui-ltx23-timeline-guide-2026-05-22.html |
| IC-LoRA Ingredients | https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Ingredients |
| FLF strength discussion | https://huggingface.co/RuneXX/LTX-2.3-Workflows/discussions/111 |

---

## 2. Mental model: three control layers

Director combines three independent knobs. Strong results usually use **at least two** of them deliberately.

```mermaid
flowchart LR
  subgraph global [Global layer]
    G[global_prompt]
    G --> style[Style / lighting / cast context]
  end
  subgraph time [Time layer - Prompt Relay]
    T1[Segment 1 prompt]
    T2[Segment 2 prompt]
    Tn[Segment N prompt]
  end
  subgraph space [Spatial layer - Guide keyframes]
    K1[Start image]
    K2[Mid / end image]
    KS[guideStrength]
  end
  global --> LTX[LTX 2.3 diffusion]
  time --> LTX
  space --> LTX
```

| Layer | Control | Answers |
|-------|---------|---------|
| **Global** | `global_prompt` | What is the world, look, and persistent context? |
| **Timed text** | Text segments + Prompt Relay | What happens **when**? |
| **Guide images** | Image segments + `guideStrength` + `isEndFrame` | What should the pixels **look like** at specific frames? |

**Prompt Relay** (NTU S-Lab, integrated via Kijai → Director): inference-time routing so prompt *A* mainly affects interval *[t₀, t₁)* and prompt *B* affects *[t₁, t₂)*, reducing cross-attention bleed between events. See the [video gallery](https://gordonchen19.github.io/Prompt-Relay/) for multi-beat examples (eagle → eye → city → TV pullback).

---

## 3. Timeline tracks (how to use the node)

### Main track (keyframes + text)

- **Image blocks** — guide keyframes (I2V start, mid-shot reveal, end frame)
- **Text blocks** — segment prompts for Prompt Relay (add via timeline UI; type `text`)
- **Video blocks** (v2) — trim/split/extend generated or imported video on the same track

Right-click an image → **Convert to End Frame** sets `isEndFrame: true` so the guide inserts at the **last frame of the block**, not the start. This is the Director-native FLF pattern.

### Audio track

- Import audio, trim on timeline, toggle **use custom audio**
- **Inpaint audio** — generate speech/SFX in gaps while keeping imported segments
- Pair segment prompts with lip-sync / performance beats (WhatDreamsCost recommends putting **action + sound** in segment prompts, not only global)

### Motion / IC-LoRA track

- Drop **reference video** for IC-LoRA structural control (pose, depth, camera, etc.)
- v2.0.4+ adds **Ingredients IC-LoRA** support on this track; author prefers it over MSR/BFS for stability
- Connect IC-LoRA in `LTXDirectorGuide` (`ic_lora_name`, `ic_lora_strength`)
- **Override audio** — use audio from IC-LoRA video instead of audio track

### Generation range

- `start_frame` / `end_frame` / `duration_frames` define what gets rendered (in/out points)
- Internal storage is always **pixel-space frames**; UI can display seconds via `frame_rate` + `display_mode`
- LTX temporal rule: output length snaps to **`8n+1`** frames

### Resize / output size

On `LTXDirector`:

- `custom_width` / `custom_height` — target for guide images (0 = use source)
- `resize_method` — `maintain aspect ratio`, `crop`, `pad`, `stretch to fit`, `pad green`
- `divisible_by` — snap to 32 for LTX latent grid (story-maker uses **1920×1088**)

Uploads land in `input/whatdreamscost/` when using the UI upload path.

---

## 4. Prompting: global vs segment

### WhatDreamsCost / tutorial consensus

From the [v1 tutorial](https://www.youtube.com/watch?v=vM60pJJqqEI) and [audio workflow video](https://www.youtube.com/watch?v=l2o24m4LLx4):

| | Global prompt | Segment (local) prompt |
|---|---------------|------------------------|
| **Put here** | Environment, lighting, overall style, stable scene context | Actions, gestures, dialogue performance, sound cues, camera moves **for that time span** |
| **Avoid** | Long action scripts, beat-by-beat story | Re-stating global style every segment |
| **Why** | Anchors consistency across the clip | Prompt Relay binds semantics to time |

**Example (singing clip):**

- **Global:** `Warm stage lighting, intimate concert venue, cinematic shallow depth of field, the singer at a vintage microphone.`
- **Segment 0–5s:** `The man slowly raises his hand to take a breath, then lowers it. Thin cigarette smoke twists and drifts gently sideways.`
- **Segment 5–10s:** `He leans into the microphone and sings the opening line with visible jaw and lip articulation.`

### Official LTX 2.3 rules (still apply inside Director)

From [LTX docs](https://docs.ltx.video/) and story-maker bible:

- **I2V / guided clips:** the still already defines appearance — prompt **motion, camera, audio**, not a second character description
- **Present tense**, physical verbs, filmmaking camera terms (`dolly in`, `static locked-off`, `tracking`)
- **One primary motion arc** per clip; split clips instead of stacking unrelated major actions
- **Dialogue** → prefer **static camera**; animate face, hands, micro-expression
- Include **audio in prose**: quoted dialogue, ambience, SFX, music
- Use **role + position** referents (`the figure on the left`), not character names LTX cannot see

### Common failure modes (WhatDreamsCost)

1. **Prompting “wrong for LTX”** — vague mood, no physical beats → model drifts or freezes  
2. **Too much action for segment length** — e.g. “robot picks up car and throws it at building” in **2 seconds** → prompt ignored  
3. **Single giant prompt** instead of timed segments when you need precise beats  

**Fix:** follow [official LTX 2.3 prompt guide](https://docs.ltx.video/api-documentation/implementation-guides/prompting-guide); match **action complexity to segment duration** (see §5).

---

## 5. Segment timing & Prompt Relay

### Minimum granularity

- Treat **~0.5s** as practical floor (shorter blocks are unreliable)
- **≥2 seconds per distinct physical action** or camera move (community rule of thumb)
- Align segment boundaries with **beats you can see** — pan ends, gesture starts, line begins

### How the UI builds relay strings

On each edit, `commitChanges()` in `ltx_director.js`:

1. Sorts segments in generation range
2. Merges **gaps** into adjacent segment lengths (pixel frames)
3. Writes `local_prompts` as `"prompt A | prompt B | …"`
4. Writes `segment_lengths` as `"48,72,…"` (same count as prompts)

**Headless automation must mirror this** — see API automation doc.

### Example 5s clip @ 24fps (121 frames)

| Time | Type | Content |
|------|------|---------|
| 0.0–2.5s | text | `Camera holds static. The woman turns her head slowly toward the window.` |
| 2.5–5.0s | text | `She exhales, shoulders drop, and she speaks softly: "I didn't expect rain today."` |

Optional: start image at frame 0 with `guideStrength` 0.8 for likeness lock.

---

## 6. Guide keyframes & strength

### Key insight (WhatDreamsCost + community)

**Every image is a guide**, not only a start frame. Place the still **where the moment should land**, then prompt the **approach** in earlier segments.

**Example:** explosion hero shot should peak at 4s → place image at 4s, prompt pre-explosion buildup in 0–4s segments.

### Layout patterns

| Pattern | Timeline | Use case |
|---------|----------|----------|
| **Standard I2V** | Image at 0, `isEndFrame: false` | Animate from storyboard still |
| **FLF / transition** | Image A @ 0, Image B @ end with `isEndFrame: true` | Panel A → panel B |
| **Mid-shot anchor** | Image @ midpoint | Reveal, punchline, landing beat |
| **T2V** | No images (or strength 0 dummy) | Pure text; set `custom_width` × `custom_height` |

### `guideStrength` tuning

| Strength | Behavior | When |
|----------|----------|------|
| **1.0** | Rigid lock to guide pixels | Start frame identity; must match still exactly |
| **0.85** | Strong end-frame landing | FLF last frame (community default for “ends on still”) |
| **0.70–0.80** | Balanced motion + structure | Talking, walking; story-maker `i2v_strength` band |
| **0.55–0.65** | Looser motion | Fast action, horse riding, large reveal pans |
| **≤0.5** | Thematic hint only | Rare; easy to drift off reference |

[RuneXX FLF note](https://huggingface.co/RuneXX/LTX-2.3-Workflows/discussions/111): **0.7** often lands the last frame close to the input still; **middle** keyframes often need **lower** strength so motion stays natural. Very high strength can cause exposure/color glitch when the guide came from another model.

### story-maker AD mapping (when we wire Director v2)

| AD `motion_class` | `guideStrength` (start) | Notes |
|-------------------|-------------------------|-------|
| talking | 0.80 | Face lock |
| walking / forest_exploration / general | 0.70 | |
| horse_riding | 0.65 | |
| large_reveal | 0.60 | |
| fast_action | 0.55 | |

FLF end frame: `max(0.85, i2v_strength + 0.05)` — same as `ltx_render_params.py` today.

### End-frame vs start-frame (technical)

- `isEndFrame: false` → insert at `segment.start`
- `isEndFrame: true` → insert at `segment.start + length - 1`

Always set the flag for last-panel guides; merely placing an image near the end is **not** equivalent.

---

## 7. Workflow patterns (recipes)

### A. Simple I2V (one storyboard panel)

1. Set `duration_frames` (e.g. 121 for ~5s @ 24fps)
2. Drop start still at frame 0 (`guideStrength` 0.7–0.8)
3. One text segment spanning full duration with **motion + audio** prompt
4. Global: style + environment only
5. Run Hotfix 2-stage workflow

### B. FLF (panel A → panel B)

1. First image @ 0 (`isEndFrame: false`, strength ~0.7)
2. Text segment(s) for middle motion
3. Last image near end (`isEndFrame: true`, strength ~0.85+)
4. Verify `guide_strength` widget order matches image sort order

### C. Timed multi-beat (dialogue + gesture)

1. Global: scene geography + lighting + cast roles (no beat script)
2. Segment 1: entrance / look
3. Segment 2: line delivery + lip articulation
4. Segment 3: reaction / hold
5. Static camera on dialogue segments

### D. Extend video (+5s)

From [Director 2.0 audio tutorial](https://www.youtube.com/watch?v=l2o24m4LLx4):

1. Load existing clip on timeline
2. Add new text segment **after** the clip end (e.g. 21–26s on a 20s base)
3. Write prompt **only** for the extension span
4. Optionally add end keyframe for landing composition

### E. IC-LoRA + Ingredients sheet

1. Author reference sheet (character turnarounds + location panel)
2. Loop sheet as static video on motion track OR use Ingredients LoRA path in v2.0.4+
3. Prompt structure from HuggingFace README:

```
Reference sheet: <describe each panel>

Generated video: <action / camera / audio for the shot>
```

4. Start IC-LoRA strength ~1.0, tune up (~1.4 in HF validation recipe — dev model; distilled hotfix may differ)
5. WhatDreamsCost chose Ingredients IC-LoRA for **stability** over other reference methods

### F. Retake mode (experimental)

- Select sub-range on timeline; set `retakePrompt` / `retakeStrength`
- Requires base video uploaded (`retakeVideo.imageFile`)
- README warns retake is **not potent enough** yet — expect iteration

---

## 8. Hotfix pipeline (quality vs speed)

Our Hotfix workflow (`LTX_Director_2_Workflow_Hotfix.json`) is **2-stage**:

1. **Stage 1** — base latent generation (distilled transformer, few steps)
2. **Stage 2** — spatial upscaler + refine pass

Practical knobs (from deprecated in-repo template notes + researcher doc):

| Knob | Typical | Notes |
|------|---------|-------|
| Stage 1 steps | 8 | Raise for chaotic motion |
| Stage 2 steps | 4 | Raise for fine detail (fabric, faces) |
| Stage 2 denoise | ~0.42 | Lower if upscale artifacts; raise if soft |
| CFG | 1.0–1.5 | story-maker `guidance` enum maps here |

Director v2.0.4 **skips Prompt Relay overhead** when relay is unused — pure single-prompt I2V runs closer to plain workflow speed. Multi-segment timelines pay the relay cost.

---

## 9. story-maker integration checklist

When AD clips move to Director v2, keep these bible rules (`ltx-2.3-director-bible.md`):

- [ ] Motion prompt = physics + camera + audio; **no** appearance re-description  
- [ ] **6 / 8 / 10s** primary durations; snap to `8n+1` frames at 24fps  
- [ ] One primary arc per clip; split on cast change or major beat change  
- [ ] Dialogue → static camera + dense micro-actions  
- [ ] Global prompt carries scene style; segment prompts carry beats  
- [ ] `guideStrength` from `motion_class`; end frame from `last_frame_strength`  
- [ ] Panels uploaded to Comfy `input/whatdreamscost/`  
- [ ] Do **not** mix Hotfix checkpoint path with legacy I2V/FLF templates in one run  

---

## 10. Quick troubleshooting

| Symptom | Likely cause | Try |
|---------|--------------|-----|
| Black / wrong first frame | Bad `imageB64` or missing `imageFile` | Upload file; use `imageFile` only in API |
| End doesn’t match last panel | `isEndFrame` false or strength too low | End frame flag + strength 0.85+ |
| Action at wrong time | One global prompt only | Add text segments; check `segment_lengths` |
| Prompt ignored | Too much action, too short segment | Lengthen segment or simplify verb |
| Frozen / Ken-Burns | Vague segment prompt | Timed physical micro-beats (bible §Anti-freeze) |
| Rigid / no motion | `guideStrength` too high | Lower to 0.6–0.7 |
| Drift off character | Strength too low on start frame | Raise start guide to 0.8 |
| Validation error on queue | Missing custom nodes / models | Run `ltx-23-director-hotfix.sh` |
| Color mismatch on end frame | Guide from different model than video | Lower end strength or re-grade still |

---

## 11. Related repo files

| Path | Purpose |
|------|---------|
| `Research/ltx-director-api-automation.md` | Headless timeline JSON + `/prompt` |
| `skills/story-maker/assets/ltx-2.3-director-bible.md` | AD + I2V motion prompt rules |
| `skills/story-maker/tools/ltx_render_params.py` | motion_class → strength / CFG |
| `workflows/setup/ltx-23-director-hotfix.sh` | Server install |
| `Research/WhatDreamsCost-ComfyUI/` | Upstream source (gitignored vendor clone) |

---

## 12. Summary

**Use Director like an editor, not a single prompt box:**

1. **Global** = world + look  
2. **Segments** = timed actions (Prompt Relay)  
3. **Guides** = where pixels must match stills (strength + end-frame flag)  
4. **Match action budget to segment length**  
5. **Keep LTX I2V prompting discipline** even with a timeline  

For automation, the UI is just a serializer — see the companion API doc for exact JSON/widget contracts.
