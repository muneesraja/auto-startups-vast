# Phase 2: Smart Frame Generation

> [!IMPORTANT]
> **In the new recursive orchestrator flow, Phase 2 (image gen) and Phase 3 (video gen) are interleaved per-chain.** The old approach of running all image gen first, then all video gen, is replaced by `filmmaking_orchestrator.py` which processes each shot in sequence within a chain. This document describes the image generation logic only.

---

## 1. The Smart Frame Generation Matrix

The pipeline adapts to shot relationships to optimize GPU usage and storytelling continuity:

| Shot Type | First Frame (FF) | Last Frame (LF) | LF Structural Anchor |
|---|---|---|---|
| **`chain_start`** | ✅ Generated | ✅ Generated | FF image (just generated) |
| **`continuation`** | ❌ Tail frame extracted from preceding video | ✅ Generated | Tail frame from preceding video |
| **`independent`** | ✅ Generated | ✅ Generated | FF image (just generated) |
| **`bridge`** | ❌ Tail frame extracted from preceding video | ✅ Generated | Tail frame from preceding video |

### Why the structural anchor matters

The LF is **always generated with the FF or tail frame prepended as reference[0]** in the Flux ReferenceLatent chain. This means:
- The Flux model sees the opening frame before generating the closing frame
- Environment, lighting, and character appearance from the FF are carried into the LF
- `lf_references` in the shot dict only needs to contain references for **new characters** entering the LF for the first time

---

## 2. The New Recursive Execution Flow

Instead of a separate Phase 2 script, the main entry point is `filmmaking_orchestrator.py`:

```bash
# Full pipeline (recommended)
python3 filmmaking_orchestrator.py --prompts filmmaking_prompt.json

# Dry-run to inspect the execution plan
python3 filmmaking_orchestrator.py --prompts filmmaking_prompt.json --dry-run

# Fast mode (skip seed hunt)
python3 filmmaking_orchestrator.py --prompts filmmaking_prompt.json --fast

# Interactive seed selection
python3 filmmaking_orchestrator.py --prompts filmmaking_prompt.json --interactive

# Rerun a single failed shot
python3 filmmaking_orchestrator.py --prompts filmmaking_prompt.json --shot film_001_shot002
```

The orchestrator processes each chain as:
```
For each chain:
  Shot 1 (chain_start):
    Phase 2: Generate FF → Generate LF (anchor=FF)
    Phase 3: FFLF video gen (seed hunt → upscale → render)
    Phase 4: Extract tail frame from video
  Shot 2 (continuation):
    Phase 2: Generate LF (anchor=tail frame from Shot 1)
    Phase 3: FFLF video gen
    Phase 4: Extract tail frame
  Shot 3 (continuation): ...
```

### Standalone Phase 2 (standalone image gen only)

For debugging or regenerating specific stills without triggering video gen:

```bash
# Generate keyframe stills for all shots in filmmaking_prompt.json
python3 generate_frames.py --prompts filmmaking_prompt.json

# Generate for a specific shot
python3 generate_frames.py --prompts filmmaking_prompt.json --shot film_001_shot001

# With a specific structural anchor (for continuation shots run standalone)
python3 generate_frames.py --prompts filmmaking_prompt.json --shot film_001_shot002 --anchor scenes/film_001_shot001_tail_frame.png

# Dry-run
python3 generate_frames.py --prompts filmmaking_prompt.json --dry-run

# With evaluation and coherence checks
python3 generate_frames.py --prompts filmmaking_prompt.json --evaluate
```

---

## 3. Reference Chain Logic

### FF generation
- Uses `references` from the shot dict (character sheets for characters in the FF)
- Plain Flux I2I via `flux-2-dev-turbo` template

### LF generation
- The **structural anchor** (FF image or tail frame) is always prepended as reference[0]
- `lf_references` from the shot dict is appended after (new characters only)
- The `build_lf_reference_chain()` function in `generate_frames.py` handles this

```
LF references passed to Flux:
  [structural_anchor_image, ...lf_references]
     ^                          ^
     Always present             Only new characters
     (FF or tail frame)         not visible in anchor
```

---

## 4. Visual Coherence Checks (FF ↔ LF)

When `--evaluate` is passed, each generated shot is evaluated for visual coherence between the FF and LF using Gemini Vision:

1. **Spatial Continuity** (0-10): Is the environment/setting consistent?
2. **Character Continuity** (0-10): Are characters identical and recognizable in both frames?
3. **Logical Trajectory** (0-10): Can the motion prompt realistically connect frame A to frame B?
4. **Interpolation Difficulty**: `easy`, `medium`, `hard`, or `impossible`

For continuation shots where the FF is the tail frame (not locally generated as a still), the coherence check compares the tail frame against the generated LF.

### Refinement Loop
- **Threshold**: Overall ≥ 7 AND difficulty ≠ `"impossible"`
- The anchor strategy treats the FF/tail as fixed; if coherence fails, retry with adjusted `last_frame_prompt` (up to 3 retries, incrementing seed)

---

## 5. File Structure

```
story-to-video-filmmaking/{story-slug}/
├── characters/                # Character reference sheets
├── scenes/                    # Keyframe still images
│   ├── film_001_shot001_ff.png      # FF (chain_start)
│   ├── film_001_shot001_lf.png      # LF (chain_start)
│   ├── film_001_shot001_tail_frame.png  # Extracted from Shot 1 video
│   ├── film_001_shot002_lf.png      # LF (continuation — FF=tail frame)
│   ├── film_001_shot002_tail_frame.png  # Extracted from Shot 2 video
│   └── ...
├── videos/                    # Final rendered video segments
├── motion_eval/               # Stage 1 preview clips and motion scores
└── feedback/                  # Frame quality and coherence eval JSONs
```
