# Full Story Dry-Run — Step-by-Step Walkthrough

This document traces the complete end-to-end execution of a story using the cinematic V2 pipeline.

## 1. Input Story & Director Decisions

### Story:
> "Pippin the panda walks through a bamboo forest. He spots a glowing butterfly
> and reaches for it. Suddenly, a waterfall appears through the bamboo — and 
> there stands Miko the monkey, grinning."

The director parses this into 1 Scene and 3 Shots, generating the V3 prompt JSON: `examples/06-full-story-dryrun-prompt.json`.

---

## 2. Wave Execution Roadmap

The orchestrator executes the pipeline in 7 distinct waves:

```
[Wave 0] Generate Pippin & Miko character sheets (Ideogram)
   │
[Wave 1] Generate Shot 1 FF & Shot 3 FF (Ideogram)
   │
[Wave 2] Edit FFs + Derive LFs:
         - Edit Shot 1 FF with Pippin sheet
         - Derive Shot 1 LF from edited Shot 1 FF
         - Edit Shot 3 FF with Pippin & Miko sheets
         - Derive Shot 3 LF from edited Shot 3 FF
   │
[Wave 3] LTX Video Generation (Batch 1):
         - Render Shot 1 Video (FF=Shot 1 FF, LF=Shot 1 LF)
         - Render Shot 3 Video (FF=Shot 3 FF, LF=Shot 3 LF)
         - Extract Tail Frame of Shot 1 Video → Shot 2 FF
   │
[Wave 4] Derive Shot 2 LF from extracted Shot 2 FF (Klein)
   │
[Wave 5] LTX Video Generation (Batch 2):
         - Render Shot 2 Video (FF=Shot 2 FF, LF=Shot 2 LF)
   │
[Done]   Stitch and export final videos!
```

---

## 3. Detailed Assets Walkthrough

### Wave 0: Character Sheets
* **Input**: Character prompts from `characters[].character_sheet_prompt`.
* **Output**:
  - `characters/pippin_sheet.png`: Front, side, and 3/4 views of the panda with a red scarf.
  - `characters/miko_sheet.png`: Front, side, and 3/4 views of the monkey with a leaf hat.

### Wave 1: First Frames (T2I)
* **Input**: Scene prompts from `shots[0].ff_prompt` and `shots[2].ff_prompt`.
* **Output**:
  - `scenes/s01_sh01_ff_raw.png`: Baby panda walking on path in bamboo forest (generic panda).
  - `scenes/s01_sh03_ff_raw.png`: Panda and monkey standing near waterfall (generic placeholders).

### Wave 2: Klein Consistency & LF Derivations
* **Actions**:
  1. **Edit Shot 1 FF**: Replace generic panda with Pippin from sheet 1.  
     → `scenes/s01_sh01_ff.png`
  2. **Derive Shot 1 LF**: Perform edit pass on `s01_sh01_ff.png` to move camera forward and turn head.  
     → `scenes/s01_sh01_lf.png`
  3. **Edit Shot 3 FF**: Replace generic characters on rock with Pippin (sheet 1) and Miko (sheet 2).  
     → `scenes/s01_sh03_ff.png`
  4. **Derive Shot 3 LF**: Edit `s01_sh03_ff.png` to make monkey wave and panda react.  
     → `scenes/s01_sh03_lf.png`

### Wave 3: Video Batch 1 & Tail Extraction
* **Actions**:
  1. Run FFLF on `s01_sh01_ff.png` (FF) and `s01_sh01_lf.png` (LF).  
     → `videos/s01_sh01.mp4`
  2. Run FFLF on `s01_sh03_ff.png` (FF) and `s01_sh03_lf.png` (LF).  
     → `videos/s01_sh03.mp4`
  3. Extract tail frame of `videos/s01_sh01.mp4`.  
     → `scenes/s01_sh02_ff.png` (Used as Shot 2 FF to ensure seamless continuity!)

### Wave 4: Klein Continuation Edit
* **Action**:
  1. Edit Shot 2 FF (`s01_sh02_ff.png`) with Pippin reference to make him reach for the glowing butterfly.  
     → `scenes/s01_sh02_lf.png`

### Wave 5: Video Batch 2
* **Action**:
  1. Run FFLF on `s01_sh02_ff.png` (FF) and `s01_sh02_lf.png` (LF).  
     → `videos/s01_sh02.mp4`

### Done: Stitching
* The orchestrator stitches `s01_sh01.mp4`, `s01_sh02.mp4`, and `s01_sh03.mp4` together. Note how Shot 2 transitions perfectly from Shot 1 because its start frame was literally extracted from Shot 1's tail!
