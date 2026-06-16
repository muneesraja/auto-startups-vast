# Phase 5: Post-Production Assembly

This phase details how to assemble the individual generated video segments into a cohesive, fluid scene or final film.

Since chained shots overlap in time to preserve motion flow, they must be aligned and stitched together. This can be done programmatically using FFmpeg or manually in a Non-Linear Editor (NLE) like DaVinci Resolve.

---

## 1. Automated Stitching via FFmpeg

After a scene or story pipeline completes, `continuation_pipeline.py` outputs a structured `stitch_metadata.json` alongside a custom shell command.

### 1.1 Concat without Crossfade (Pre-Trimmed)
If you want to perform a simple cut-to-cut edit where the overlap is trimmed out:
1. Create a `concat.txt` file listing the files:
   ```text
   file 'film_001_shot001_trimmed.mp4'
   file 'film_001_shot002_trimmed.mp4'
   ```
2. Execute the fast concat copy command:
   ```bash
   ffmpeg -f concat -safe 0 -i concat.txt -c copy final_scene.mp4
   ```

### 1.2 Seamless Crossfading via `xfade` (Recommended)
To blend the motion of overlapping regions smoothly, use FFmpeg's `xfade` filter.

For two 5.0-second shots with a 1.0-second overlap, the crossfade begins at $4.0$ seconds (Offset = Duration - Overlap) and lasts for $1.0$ second.

#### Example FFmpeg command:
```bash
ffmpeg -i film_001_shot001.mp4 -i film_001_shot002.mp4 -filter_complex \
  "[0:v][1:v]xfade=transition=fade:duration=1.0:offset=4.0[outv]" \
  -map "[outv]" final_scene.mp4
```

*For multiple clips*, the filter complex chains the crossfades sequentially:
```bash
ffmpeg -i shot1.mp4 -i shot2.mp4 -i shot3.mp4 -filter_complex \
  "[0:v][1:v]xfade=transition=fade:duration=1.0:offset=4.0[int1]; \
   [int1][2:v]xfade=transition=fade:duration=1.0:offset=8.0[outv]" \
  -map "[outv]" final_scene.mp4
```
*(Note: The second offset increases to $8.0$ seconds because the timeline accumulates the lengths of the combined videos.)*

---

## 2. Manual Assembly in DaVinci Resolve (Best Quality)

For the highest cinematic control, manual assembly in an NLE is preferred. Follow this editing workflow:

1. **Import Clips**: Drag all generated `.mp4` video files into your DaVinci Resolve Media Pool.
2. **Arrange on Timeline**: Place Shot 1 on Track 1, and Shot 2 directly following it.
3. **Align Overlaps**:
   - Slide Shot 2 backward in time over Shot 1 by the exact overlap duration (e.g., exactly `25 frames` or `1.0 second` for 25fps projects).
   - This creates a vertical overlap stack on the timeline.
4. **Apply Cross-Dissolve**:
   - Place a standard **Cross Dissolve** transition centered on the boundary between the overlap.
   - Adjust the transition duration to match the overlap length (e.g., `1.0 second`).
5. **Verify Coherence**: Play through the transition. Because the start of Shot 2 was generated using an extracted tail frame from Shot 1, the objects and characters will align perfectly, creating a smooth motion blend instead of a visual jump.
