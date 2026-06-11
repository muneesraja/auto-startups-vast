# Phase 4: Shot Continuation

The key to creating long, coherent sequences is **shot continuation**. Standard Image-to-Video generation results in jarring jump cuts between shots. Shot continuation resolves this by feeding the tail region of one generated video clip as the starting frame (First Frame) of the next.

---

## 1. The Context Buffer Overlap Strategy

To achieve a seamless transition when stitching clips together, adjacent shots overlap slightly in time. This is controlled by the `overlap_seconds` global config parameter (default: `1.0` second, representing `25` frames at `25` fps).

```
Timeline:
Shot 1 Video:    [=======================================|  1.0s Tail Overlap  ]
                                                         ▲
                                                 Extraction Point
                                                         ▼
Shot 2 Video:                                            [=====================...]
                                                         [  1.0s Head Overlap  |  Remaining Clip  ]
```

### 1.1 Sourcing the Transition Keyframe
At the end of Shot 1, the video generator outputs a final video.
1. The pipeline calculates the frame index corresponding to the extraction point (e.g., $Total\_Frames - Overlap\_Frames$).
2. The pipeline extracts the exact frame at that index using FFmpeg.
3. This extracted image is uploaded as the `first_frame_image` for Shot 2.
4. When Shot 2 is generated, its animation begins exactly matching the end of Shot 1's overlap start, creating continuous motion.

---

## 2. Adaptive Extraction with Quality Gate

The `continuation_pipeline.py` script handles extraction tasks using **adaptive multi-candidate extraction** (updated 2026-06-11).

### 2.1 Multi-Candidate Extraction (Default)

Instead of extracting a single frame at a fixed offset, the pipeline extracts **3 candidate frames**:

| Candidate | Frame Index | Rationale |
|---|---|---|
| `last_frame` | N - 1 | The actual last frame (closest to LF target) |
| `last_0.5s` | N - 0.5×fps | Half-second before end (moderate drift) |
| `last_1.0s` | N - 1.0×fps | One second before end (original behavior) |

If the **target LF image** is available (the LF that was used to generate this shot), the pipeline computes **SSIM** (Structural Similarity Index) between each candidate and the target LF, then selects the candidate with the highest SSIM score.

### 2.2 Quality Gate (P0.5)

After selecting the best candidate, if its SSIM is below `quality_threshold` (default: 0.3), the pipeline emits a warning:

```
⚠️ QUALITY GATE WARNING: Best tail frame SSIM (0.1234) is below threshold (0.3).
   The video likely drifted far from the target LF.
⚠️ Consider regenerating the FF for the next shot from scratch instead of
   using this degraded tail frame.
```

> **Why this matters:** In the tiny-bee production run, Shot 1's video panned the camera upward (due to resolution mismatch + conflicting motion prompts). The extracted tail frame showed only the log ceiling — Barnaby was reduced to a yellow smudge at the bottom edge. This corrupted the entire continuation chain.

### 2.3 FFmpeg Commands
```bash
# Single frame extraction
ffmpeg -y -i input_video.mp4 -vf "select=eq(n\,100)" -vframes 1 output_frame.png

# SSIM comparison between candidate and target LF
ffmpeg -i candidate.png -i target_lf.png -lavfi ssim -f null -
```

### 2.4 Fallback Behavior

If SSIM computation is unavailable (e.g., ffmpeg build without `ssim` filter), the pipeline falls back to the original single-frame extraction at the overlap offset.

---

## 3. The Chaining Pipeline Workflow

During generation, the agent coordinates Phase 4 automatically:

1. **Dependency Verification**: Before executing a shot of type `continuation`, the script verifies that the parent shot (in `continues_from`) has successfully completed and its final video exists.
2. **Target LF Resolution**: The pipeline resolves the parent shot's `last_frame_image` to provide as the SSIM comparison target.
3. **Adaptive Tail Frame Extraction**: The script extracts 3 candidates, compares each to the target LF via SSIM, and picks the best match. The result is saved in `scenes/{prefix}_ff_extracted.png`.
4. **Quality Gate Check**: If SSIM is below threshold, a warning is emitted. The orchestrator may choose to regenerate the FF from scratch (using `first_frame_prompt`) instead of using the degraded tail.
5. **Execution Routing**: The extracted image path is passed as the input `first_frame_image` parameter to Phase 3 for the subsequent shot.
6. **Metadata Storage**: The pipeline records overlap frames and trim boundaries to `stitch_metadata.json` to guide Phase 5 assembly.

