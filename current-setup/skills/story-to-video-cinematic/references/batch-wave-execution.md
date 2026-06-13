# Batch-Wave Execution & GPU Swapping

The batch-wave execution model is designed to optimize execution time on cloud GPU instances (Vast.ai, RunPod) by minimizing expensive VRAM loading times. 

## The Model Swap Overhead Problem

ComfyUI runs workflows on the GPU. Loading large models (Flux 9B, LTX 22B) into VRAM takes anywhere from 45 to 90 seconds.
* **V1 (Sequential Mode)**: Swap models from CPU to GPU *per shot*. For a 6-shot story:
  `6 shots * 3 model swaps = 18 swaps (~15-27 minutes wasted in loading)`.
* **V2 (Batch-Wave Mode)**: Group operations of the same model family together across all shots.
  `7 fixed model swaps (~6-9 minutes total loading time, regardless of story length!)`.

---

## Detailed Swap Timeline

The following timeline shows exactly which model is loaded on the GPU during each wave of the pipeline:

| Wave | GPU Model Loaded | Action Description | Inputs | Outputs |
|------|------------------|--------------------|--------|---------|
| **Wave 0** | `ideogram-4-t2i` | Generate all character sheets | None (T2I) | `char_id_character_sheet.png` |
| **Wave 1** | `ideogram-4-t2i` | Generate raw FFs and raw LFs for all root shots | Narrative prompts | `sNN_shNN_ff_raw.png`, `_lf_raw.png` |
| **Wave 2** | `flux-2-klein-image-edit` | Edit FFs for character likeness + Derive LFs from FFs | Raw stills + character sheets | `sNN_shNN_ff_edited.png`, `_lf_edited.png` |
| **Wave 3** | `ltx-23-fflf-seed-hunter` | Render root videos and extract tail frames | Edited FFs + LFs | `videos/sNN_shNN.mp4`, `scenes_edited/sNN_shNN_tail_frame.png` |
| **Wave 4** | `flux-2-klein-image-edit` | Edit tail frames (FF) into continuation LFs | Predecessor tail frame + sheets | `sNN_shNN_lf_edited.png` (continuation LF) |
| **Wave 5** | `ltx-23-fflf-seed-hunter` | Render depth-1 continuation videos | Predecessor tail frame + derived LF | `videos/sNN_shNN.mp4`, `scenes_edited/sNN_shNN_tail_frame.png` |
| **Wave 6** | `flux-2-klein-image-edit` | Edit depth-1 tail frames into continuation LFs | Depth-1 tail frame + sheets | `sNN_shNN_lf_edited.png` (depth-2 LF) |
| **Wave 7** | `ltx-23-fflf-seed-hunter` | Render depth-2 continuation videos | Depth-1 tail frame + derived LF | `videos/sNN_shNN.mp4`, `scenes_edited/sNN_shNN_tail_frame.png` |

---

## Execution Logic & Failure Tolerance

If a shot fails at Wave 2 (e.g. Klein produces a corrupted image or times out), the orchestrator logs the error and proceeds with the rest of the batch. In Wave 3, only shots that successfully completed Wave 2 will be queued to LTX-Video. This ensures that a single failed shot does not block the entire pipeline from rendering the rest of the animation.
