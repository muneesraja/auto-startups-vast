# V13 — Story to Video Deterministic Skill Planning

**Date:** 2026-06-17  
**Status:** Planning / Discussion  

---

## 1. Schema Design — `prompts.json` & `director_visual_blueprint.json`

### 1.1 `director_visual_blueprint.json` — Master Schema

This is the single source of truth. All downstream agents/scripts read from and write back to this file.

```json
{
  "meta": {
    "story_title": "The Panda and the Butterfly",
    "style": "children's book watercolor illustration",
    "aesthetic": "warm, gentle, narrative",
    "total_duration_seconds": 42,
    "total_scenes": 3,
    "total_shots": 8,
    "created_at": "2026-06-17T10:00:00Z",
    "last_updated_at": "2026-06-17T12:00:00Z",
    "version": 1
  },

  "characters": [
    {
      "id": "char_01",
      "name": "Pippin the Panda",
      "appearance": "Chubby baby panda with round ears, black and white fur, bright curious eyes, small red scarf",
      "character_sheet_prompt": null,
      "character_sheet_path": null,
      "character_sheet_status": "pending"
    },
    {
      "id": "char_02",
      "name": "Momo the Monkey",
      "appearance": "Slender golden-brown monkey with a curly tail, expressive amber eyes, wears a tiny green vest",
      "character_sheet_prompt": null,
      "character_sheet_path": null,
      "character_sheet_status": "pending"
    }
  ],

  "scenes": [
    {
      "scene_id": "scene_01",
      "scene_title": "The Forest Path",
      "scene_duration_seconds": 14,
      "environment": "Dense bamboo forest with dappled golden sunlight filtering through canopy, misty atmosphere, moss-covered rocks along a winding path",
      "time_of_day": "late morning",
      "lighting": "warm dappled sunlight, soft shadows",

      "shots": [
        {
          "shot_id": "scene_01_shot_01",
          "shot_index": 0,
          "duration_seconds": 4,
          "continuation_from_previous": false,
          "wave": 1,

          "characters_present": ["char_01"],

          "director_notes": "Opening establishing shot. Panda walks along a forest path toward camera. Medium-wide framing.",

          "ff": {
            "description": "Medium-wide shot of Pippin the Panda standing at the far end of a bamboo forest path, facing the camera, one paw lifted mid-step. Dappled golden sunlight. Misty atmosphere.",
            "camera_framing": "medium-wide, eye-level",
            "character_expressions": {
              "char_01": "curious, mouth slightly open"
            },

            "ideogram_prompt": null,
            "ideogram_prompt_status": "pending",

            "consistency_prompt": null,
            "consistency_prompt_status": "pending",
            "consistency_references": ["char_01"],

            "generated_image_path": null,
            "consistent_image_path": null,
            "generation_status": "pending"
          },

          "lf": {
            "description": "Same path, Panda has walked closer to camera. Now mid-frame. Head tilted slightly upward noticing something. Sunlight shifted slightly.",
            "camera_framing": "medium, eye-level",
            "character_expressions": {
              "char_01": "surprised, eyes wide, head tilted up"
            },

            "delta_from_ff": {
              "camera_change": "static camera, subject moves toward camera",
              "subject_changes": "Panda is now closer and larger in frame, head tilted upward, expression shifts from curious to surprised",
              "environment_changes": "Slight wind moves bamboo leaves, sunlight dapple pattern shifts, a butterfly becomes faintly visible in upper-right",
              "particle_effects": "Dust motes in sunlight beams, slight leaf drift"
            },

            "flux_edit_prompt": null,
            "flux_edit_prompt_status": "pending",
            "flux_references": ["ff_image", "char_01"],

            "generated_image_path": null,
            "generation_status": "pending"
          },

          "motion": {
            "prompt": null,
            "prompt_status": "pending",
            "video_path": null,
            "extracted_last_frame_path": null,
            "generation_status": "pending"
          }
        },
        {
          "shot_id": "scene_01_shot_02",
          "shot_index": 1,
          "duration_seconds": 3,
          "continuation_from_previous": true,
          "wave": 2,

          "characters_present": ["char_01"],

          "director_notes": "Continuation from shot 1. Panda now reacts to butterfly. Camera stays. Cut NOT needed — smooth visual continuation.",

          "ff": {
            "description": "INHERITED from scene_01_shot_01 last frame extraction",
            "camera_framing": "medium, eye-level",
            "character_expressions": {
              "char_01": "delighted, reaching one paw upward"
            },
            "source": "extracted_from_previous_video",

            "ideogram_prompt": null,
            "ideogram_prompt_status": "skipped",

            "consistency_prompt": null,
            "consistency_prompt_status": "skipped",
            "consistency_references": [],

            "generated_image_path": null,
            "consistent_image_path": null,
            "generation_status": "pending_wave_1"
          },

          "lf": {
            "description": "Panda gently cups the butterfly in both paws, smiling warmly. Butterfly glowing faintly.",
            "camera_framing": "medium close-up, slight zoom in",
            "character_expressions": {
              "char_01": "warm smile, eyes soft"
            },

            "delta_from_ff": {
              "camera_change": "subtle zoom in toward panda's face and paws",
              "subject_changes": "Arms raised to cup butterfly, facial expression shifts from reaching to gentle holding",
              "environment_changes": "Background slightly more out-of-focus from zoom, no drastic change",
              "particle_effects": "Butterfly wing shimmer, golden dust motes"
            },

            "flux_edit_prompt": null,
            "flux_edit_prompt_status": "pending",
            "flux_references": ["ff_image", "char_01"],

            "generated_image_path": null,
            "generation_status": "pending"
          },

          "motion": {
            "prompt": null,
            "prompt_status": "pending",
            "video_path": null,
            "extracted_last_frame_path": null,
            "generation_status": "pending"
          }
        }
      ]
    }
  ]
}
```

### 1.2 `prompts.json` — Namespaced Prompt Store

Each agent step writes to its own namespace. No collision. Clear ownership.

```json
{
  "meta": {
    "blueprint_version": 1,
    "last_updated_by": "step_6_lf_prompter",
    "last_updated_at": "2026-06-17T12:00:00Z"
  },

  "character_sheets": {
    "char_01": {
      "prompt_type": "ideogram_json",
      "prompt": { "...ideogram JSON..." },
      "output_path": null,
      "status": "pending",
      "generated_by": "step_3_character_prompter"
    },
    "char_02": {
      "prompt_type": "ideogram_json",
      "prompt": { "...ideogram JSON..." },
      "output_path": null,
      "status": "pending",
      "generated_by": "step_3_character_prompter"
    }
  },

  "ff_shots": {
    "scene_01_shot_01": {
      "prompt_type": "ideogram_json",
      "prompt": { "...ideogram JSON..." },
      "reference_images": [],
      "output_path": null,
      "status": "pending",
      "generated_by": "step_4_ff_prompter"
    },
    "scene_01_shot_02": {
      "prompt_type": "extracted_frame",
      "prompt": null,
      "reference_images": [],
      "output_path": null,
      "status": "pending_wave_1",
      "generated_by": "system"
    }
  },

  "consistency_patches": {
    "scene_01_shot_01": {
      "prompt_type": "flux_edit",
      "prompt": "Apply the character appearance from image 1 (Pippin the Panda character sheet) to the panda in the scene. Maintain the pose, lighting, and composition. The panda should have the exact fur pattern, red scarf, and round ears from the character reference.",
      "reference_images": ["{{character_sheets.char_01.output_path}}", "{{ff_shots.scene_01_shot_01.output_path}}"],
      "output_path": null,
      "status": "pending",
      "generated_by": "step_5_consistency_prompter"
    }
  },

  "lf_shots": {
    "scene_01_shot_01": {
      "prompt_type": "flux_edit",
      "prompt": "The panda has walked closer to the camera and is now mid-frame. Its head is tilted slightly upward with a surprised expression, eyes wide. Bamboo leaves sway gently in the wind. A faint butterfly is becoming visible in the upper-right of the frame. Dust motes float in the sunlight beams. The sunlight dapple pattern has shifted slightly.",
      "reference_images": [
        "{{consistency_patches.scene_01_shot_01.output_path}}",
        "{{character_sheets.char_01.output_path}}"
      ],
      "output_path": null,
      "status": "pending",
      "generated_by": "step_6_lf_prompter"
    }
  },

  "motion_prompts": {
    "scene_01_shot_01": {
      "prompt": "A panda walking forward along a forest path toward the camera, tilting its head up as it notices something above. Bamboo leaves sway, dust motes drift in sunbeams. Slow deliberate walk.",
      "duration_seconds": 4,
      "ff_image": "{{consistency_patches.scene_01_shot_01.output_path}}",
      "lf_image": "{{lf_shots.scene_01_shot_01.output_path}}",
      "output_path": null,
      "status": "pending",
      "generated_by": "step_7_motion_prompter"
    }
  }
}
```

### 1.3 Key Schema Decisions

| Decision | Rationale |
|---|---|
| **Namespaced sections** in `prompts.json` | Each agent step writes to its own namespace (`character_sheets`, `ff_shots`, `consistency_patches`, `lf_shots`, `motion_prompts`). Zero collision even if parallelized later. |
| **Template references** with `{{...}}` | Paths are resolved at generation time by the wave organizer script. This decouples prompt generation from image generation. |
| **Status tracking per-item** | Every prompt and every generation has a `status` field (`pending`, `generated`, `failed`, `skipped`, `pending_wave_1`). This enables resume-from-failure. |
| **`delta_from_ff`** in blueprint | The director explicitly describes what changes between FF and LF at the structural level, not the prompt level. This gives the LF prompter agent concrete constraints. |
| **`wave` field on shots** | The organizer script can filter by wave without re-analyzing continuation chains. |
| **`continuation_from_previous`** | Single boolean. If `true`, FF source is `extracted_from_previous_video`. If `false`, FF goes through Ideogram → Flux consistency pipeline. |

---

## 2. Agent SDK — Google ADK vs OpenRouter Agent SDK

### Recommendation: Google ADK (Agent Development Kit)

| Factor | Google ADK | OpenRouter SDK |
|---|---|---|
| **Structured Output** | First-class JSON schema enforcement via Gemini models | Depends on upstream model provider; inconsistent |
| **Multi-step Orchestration** | Built-in agent orchestration, tool use, and sequential/parallel agent chaining | Manual orchestration, no agent graph primitives |
| **Model Flexibility** | Supports Gemini natively + can call external models | Full model marketplace access |
| **Tool Definition** | Native function calling with typed schemas | Pass-through to model's function calling |
| **State Management** | Session-based state management built-in | Manual state management |
| **Cost** | Gemini Flash/Pro are competitive; Flash 2.5 is very cheap | Pay per token per model, more flexibility on model choice |
| **Local/Self-hosted** | Can run locally | API-only |

### Why ADK wins here:

1. **Structured JSON enforcement is critical for this pipeline.** Steps 2-7 all produce structured JSON. ADK with Gemini models gives you `response_schema` enforcement — the model MUST return valid JSON matching your schema. OpenRouter's structured output support varies by model.

2. **Agent chaining is native.** Your pipeline is a linear chain of 9 steps. ADK's `SequentialAgent` or custom `AgentGraph` can model this directly with shared state.

3. **Tool definitions for ComfyUI API calls.** Each generation step (Ideogram API, Flux API, LTX generation) can be defined as an ADK tool. The agent decides when to call it based on the blueprint.

4. **Cost efficiency.** Gemini 2.5 Flash is extremely cheap for the mechanical prompt generation steps (3-7). Use Gemini 2.5 Pro for the director phase (steps 1-2).

### Hybrid Approach (Best of Both):

Use **ADK for orchestration and structured output**, but call **OpenRouter for specific model choices** when needed:

```
Step 1-2 (Director): ADK → Gemini 2.5 Pro (strong reasoning, structured output)
Step 3-7 (Prompt Generation): ADK → Gemini 2.5 Flash (cheap, fast, schema-enforced)
  OR
Step 1-2 (Director): ADK → OpenRouter → Claude Sonnet 4 (if testing shows better results)
Step 3-7 (Prompt Generation): ADK → Gemini 2.5 Flash
```

ADK can call OpenRouter as a custom tool, giving you the model marketplace while keeping orchestration clean.

---

## 3. Model Selection Strategy

### Per-Step Model Recommendations

| Step | Task | Reasoning Complexity | Recommended Model | Fallback |
|---|---|---|---|---|
| **Step 1** — Director Script | Story → Cinematographic screenplay | **High** — needs film theory, pacing, visual storytelling | Gemini 2.5 Pro / Claude Sonnet 4 | GPT-4o |
| **Step 2** — Visual Blueprint JSON | Script → Structured JSON with durations, FF/LF descriptions, character mappings | **High** — complex structured output with cross-referencing | Gemini 2.5 Pro (with schema enforcement) | Claude Sonnet 4 |
| **Step 3** — Character Sheet Prompts | Blueprint → Ideogram JSON for character sheets | **Medium** — formulaic, follows template | Gemini 2.5 Flash | GPT-4o mini |
| **Step 4** — FF Shot Prompts | Blueprint → Ideogram JSON for scene images | **Medium** — needs scene composition understanding | Gemini 2.5 Flash | GPT-4o mini |
| **Step 5** — Consistency Prompts | Blueprint + FF → Flux edit prompts | **Medium** — edit-style prompting, reference image assignment | Gemini 2.5 Flash | GPT-4o mini |
| **Step 6** — LF Shot Prompts | Blueprint + FF → Flux edit prompts for LF | **High** — subtle delta reasoning (see section 6) | Gemini 2.5 Pro / Claude Sonnet 4 | Gemini 2.5 Flash |
| **Step 7** — Motion Prompts | Blueprint → LTX FFLF motion prompts | **Medium** — follows FFLF rules, brief prompts | Gemini 2.5 Flash | GPT-4o mini |
| **Step 8** — Wave Organizer | JSON processing, no LLM needed | **None** — pure script | Node.js/Python script | — |

### Testing Strategy

Run the same scene through 3 model combinations and compare output quality:

1. **All Gemini**: Pro for 1-2, Flash for 3-7
2. **Hybrid**: Claude Sonnet 4 for 1-2 + 6, Flash for rest
3. **All OpenRouter**: Claude for 1-2 + 6, GPT-4o mini for rest

Evaluate on: JSON validity, prompt quality, visual output consistency, cost per story.

---

## 4. Duration Guardrails (2s-5s)

Agreed on 2s-5s. Hardcode these rules into the Director's system prompt:

```
DURATION RULES (MANDATORY):
- Minimum shot duration: 2 seconds
- Maximum shot duration: 5 seconds  
- Default for action shots (walking, running, turning): 3 seconds
- Default for reaction shots (noticing, surprised, smiling): 2 seconds
- Default for establishing/wide shots (landscape, environment): 4-5 seconds
- Default for emotional close-ups: 2-3 seconds
- Head turns, quick glances, small gestures: 2 seconds ALWAYS
- NEVER exceed 5 seconds — LTX FFLF quality degrades beyond this
- If a shot needs more time, SPLIT it into two continuation shots
```

---

## 5. LF Edit Delta Strategy — Few-Shot Approach

This is the hardest part of the pipeline. Here's my detailed suggestion:

### The Core Problem

The LF prompter needs to describe *what's different* from the FF image in Flux Klein 9B's edit language. Too much change → the video will jump-cut. Too little change → the video will freeze/stutter. The sweet spot is **3-5 discrete, observable differences**.

### Strategy: Structured Delta Categories + Few-Shot Examples

Build the LF prompter's system prompt around a **delta taxonomy** with concrete examples for each category.

#### Delta Taxonomy

Every LF prompt must specify changes from exactly these categories:

| Category | What it controls | Safe range for 2-5s FFLF |
|---|---|---|
| **Camera** | Pan, tilt, zoom, dolly | ≤15° rotation, ≤20% zoom |
| **Subject Position** | Where the character is in frame | Move ≤30% of frame width |
| **Subject Action** | What the character is doing | One action change (walking→standing, looking left→looking up) |
| **Subject Expression** | Facial/body expression | One expression shift |
| **Environment Motion** | Background elements that move | Wind, water, clouds — subtle |
| **Particles** | Small floating elements | Dust, leaves, snow, fireflies |

#### Few-Shot Examples for the LF Prompter System Prompt

```
=== FEW-SHOT EXAMPLE 1: Walk Forward ===
SHOT CONTEXT: A panda walking along a forest path, 3 seconds
FF: Medium-wide shot, panda at far end of path, facing camera, one paw lifted
LF DELTA:
- Camera: static, no change
- Subject Position: panda moved from background to mid-frame (closer to camera)
- Subject Action: still walking, opposite paw now lifted
- Subject Expression: curious → slightly surprised, head tilted up
- Environment: bamboo leaves shifted by wind, sunlight dapple pattern moved right
- Particles: 3-4 dust motes visible in light beams

LF PROMPT (for Flux Klein 9B):
"The panda has walked closer to the camera and is now in the middle of the frame. Its head is tilted slightly upward with eyes wide in a surprised expression. The bamboo leaves have shifted in a gentle breeze. Dust motes float in the sunlight beams."

=== FEW-SHOT EXAMPLE 2: Head Turn (2 second micro-shot) ===  
SHOT CONTEXT: Close-up of a fox, turning to look at camera, 2 seconds
FF: Fox looking left in profile, forest background blurred
LF DELTA:
- Camera: static
- Subject Position: no change (close-up)
- Subject Action: head rotated from left profile to three-quarter view facing camera
- Subject Expression: neutral → alert, ears perked forward
- Environment: no change (blurred background)
- Particles: none

LF PROMPT:
"The fox has turned its head from looking left to facing slightly toward the camera in a three-quarter view. Its ears are now perked forward with an alert expression. Everything else remains unchanged."

=== FEW-SHOT EXAMPLE 3: Camera Zoom with Environment (4 second establishing) ===
SHOT CONTEXT: Wide shot of a waterfall scene, camera slowly zooms in, 4 seconds
FF: Ultra-wide shot of waterfall with forest, tiny figure visible at base
LF DELTA:
- Camera: slow zoom in, framing tightens from ultra-wide to wide
- Subject Position: figure is now larger in frame due to zoom
- Subject Action: figure's arm is raised, pointing at waterfall
- Subject Expression: not visible at this distance
- Environment: water flow pattern changed, mist at base shifted, clouds moved slightly left
- Particles: water spray mist denser due to closer framing

LF PROMPT:
"The camera has zoomed in slightly, tightening the frame from ultra-wide to wide. The figure at the base of the waterfall is now larger and has raised an arm pointing upward. The waterfall's water flow pattern has shifted, mist at the base has moved, and clouds have drifted slightly left. Water spray is more visible."

=== FEW-SHOT EXAMPLE 4: Two characters interacting (3 seconds) ===
SHOT CONTEXT: Panda and Monkey meeting on a path, 3 seconds
FF: Panda on left, Monkey approaching from right, 6 feet apart
LF DELTA:
- Camera: static
- Subject Position: both moved toward center, now 2 feet apart
- Subject Action: Panda extended a paw, Monkey reaching out to shake
- Subject Expression: Panda warm smile, Monkey excited grin
- Environment: tree branches swayed slightly
- Particles: a few falling leaves between them

LF PROMPT:
"The panda and monkey have moved closer together and are now nearly touching. The panda extends its right paw forward while the monkey reaches out with its hand to meet. The panda has a warm smile and the monkey shows an excited grin. Tree branches have swayed slightly and a few leaves are falling between them."
```

#### Key Rules for the LF Prompter's System Prompt

```
LF PROMPT ENGINEERING RULES:

1. DESCRIBE THE END STATE, NOT THE TRANSITION
   Bad: "The camera slowly pans right and the panda turns its head"
   Good: "The panda's head is now turned to the right, facing the camera"

2. KEEP CHANGES TO 3-5 OBSERVABLE DIFFERENCES
   The LTX FFLF model interpolates between FF and LF. If LF looks radically 
   different, the video will jump. If LF looks identical, the video will freeze.

3. PRESERVE 80% OF THE FRAME
   Most of the image should remain recognizable. Only 20% of the visual 
   information should change between FF and LF.

4. USE CONCRETE SPATIAL LANGUAGE
   Bad: "moved a bit"
   Good: "moved from the left third to the center of the frame"

5. ENVIRONMENT CHANGES MUST BE PHYSICALLY PLAUSIBLE
   Wind moves leaves. Water flows downstream. Clouds drift. 
   Don't teleport background elements.

6. FOR 2-SECOND SHOTS: ONLY 1-2 CHANGES
   A head turn. An expression shift. That's it.

7. FOR 5-SECOND SHOTS: UP TO 5 CHANGES
   Camera, position, action, expression, and one environment change.

8. ALWAYS REFERENCE THE FF IMAGE
   Start the prompt assuming image 1 is the FF. Describe what changed.
```

### Implementation Tip

Store these few-shot examples in a file like `system-prompts/lf-prompter-examples.md` and inject them into the system prompt. As you test and discover failure modes, add new examples for those specific cases. This is a living document that gets better with each story you produce.

---

## Summary of Answers

| Your Question | My Answer |
|---|---|
| **1. Plan the schema** | See section 1 — namespaced `prompts.json` with 5 sections + full `director_visual_blueprint.json` schema with per-shot FF/LF/motion structure |
| **2. Google ADK or OpenRouter SDK?** | **Google ADK** for orchestration + structured output enforcement. Use OpenRouter as a tool within ADK for model flexibility (hybrid approach) |
| **3. Model selection** | Gemini 2.5 Pro for Steps 1-2 (director), Gemini 2.5 Flash for Steps 3-5 + 7 (mechanical), Gemini Pro or Claude Sonnet 4 for Step 6 (LF deltas). Test 3 combinations. |
| **4. Duration** | 2-5s with hard rules per shot type in the director system prompt |
| **5. LF edit delta strategy** | Structured delta taxonomy (6 categories) + few-shot examples in system prompt + key rules about change budget (3-5 observable differences, preserve 80% of frame) |
