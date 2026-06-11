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

## 2. Extraction Implementation Details

The `continuation_pipeline.py` script handles extraction tasks.

### 2.1 Frame Calculation Formula
$$\text{Extraction Frame Index} = \text{Total Frames} - (\text{Overlap Seconds} \times \text{FPS}) - 1$$

*Example*: For a 5-second video at 25 fps (126 frames total) with a 1.0-second overlap:
$$\text{Index} = 126 - (1.0 \times 25) - 1 = 100$$
The frame at index 100 is extracted.

### 2.2 FFmpeg Command
```bash
ffmpeg -y -i input_video.mp4 -vf "select=eq(n\,100)" -vframes 1 output_frame.png
```

---

## 3. The Chaining Pipeline Workflow

During generation, the agent coordinates Phase 4 automatically:

1. **Dependency Verification**: Before executing a shot of type `continuation`, the script verifies that the parent shot (in `continues_from`) has successfully completed and its final video exists.
2. **Tail Frame Extraction**: The script runs the FFmpeg extraction command on the parent video, saving the result in `scenes/film_{scene}_shot{shot}_ff_extracted.png`.
3. **Execution Routing**: The extracted image path is passed as the input `first_frame_image` parameter to Phase 3 for the subsequent shot.
4. **Metadata Storage**: The pipeline records overlap frames and trim boundaries to `stitch_metadata.json` to guide Phase 5 assembly.
