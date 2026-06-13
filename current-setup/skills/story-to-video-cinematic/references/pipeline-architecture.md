# Cinematic Pipeline V2 — Pipeline Architecture

The cinematic animation pipeline uses a 3-stage model chain orchestrated via the **batch-wave execution model**. This ensures maximum visual quality, character consistency, and minimizes model swaps on the GPU.

## Model Stack

1. **Stage 1: Ideogram 4 (T2I)**: Generates high-quality base compositions and character reference sheets.
2. **Stage 2: Flux Klein 9B (I2I Edit)**: Consistency editor that aligns characters with their reference sheets and derives last frames (LF) from first frames (FF).
3. **Stage 3: LTX 2.3 FFLF (Video)**: Motion engine that interpolates between FF and LF.

---

## Batch-Wave Execution Model (GPU Swap Timeline)

By batching calls to the same model together, the orchestrator performs a fixed set of GPU loads (max 7 loads) regardless of the number of scenes/shots in the story.

```
Wave 0 (GPU: Ideogram) 
   └─ Generate all character reference sheets.
Wave 1 (GPU: Ideogram) 
   └─ Generate all raw First Frames (FFs) for visual chain starts.
Wave 2 (GPU: Flux Klein)
   ├─ Apply character sheets to raw FFs (FF edit pass).
   └─ Derive all Last Frames (LFs) from edited FFs.
Wave 3 (GPU: LTX-Video)
   ├─ Render all visual chain start videos.
   └─ Extract tail frames from finished videos.
Wave 4 (GPU: Flux Klein - Continuation Wave 1)
   └─ Derive LFs for depth-1 continuation shots using tail frames as FF inputs.
Wave 5 (GPU: LTX-Video - Continuation Wave 1)
   ├─ Render all depth-1 continuation videos.
   └─ Extract tail frames from finished videos.
Wave 6 & 7 (Depth 2 Continuation)
   └─ Repeat Wave 4 & 5 logic for depth-2 continuation shots.
```

---

## Technical Details

### Visual Depth & Wave Scheduling
Every shot is recursively assigned a visual depth:
* `depth = 0` if the shot starts a chain (`continuity: "start"`, `##cut`, or `ff_source: "ideogram"`).
* `depth = d + 1` if it continues from a shot at depth `d`.

This visual depth determines the continuation wave in which the shot is processed, allowing the pipeline to scale dynamically to support any chain length.

### Stitching
At the end of the pipeline, the orchestrator outputs `stitch_list.json` containing the sorted list of successful video clip paths.
