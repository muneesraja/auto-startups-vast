# Continuity Chain & Tail Frame Extraction Walkthrough

This document explains the technical details of continuation chains, tail frame extraction, and how they ensure seamless transitions between shots.

## 1. What is a Continuation Chain?

A continuation chain is a sequence of shots that are visually continuous (no camera cuts, no sudden jumps in environment). 
* **Shot 1 (Start)**: The camera is running.
* **Shot 2 (Continuation)**: The camera continues from exactly where Shot 1 ended.
* **Shot 3 (Continuation)**: The camera continues from exactly where Shot 2 ended.

To ensure there is **zero jump-cut** between Shot 1 and Shot 2, the **First Frame (FF) of Shot 2** is literally the **Last Frame of Shot 1's video**.

---

## 2. Step-by-Step Execution Flow

Let's follow a 3-shot chain: `s01_sh01` (start), `s01_sh02` (continuation), and `s01_sh03` (continuation).

### Step 1: Initialize Shot 1 FF
1. Generate `s01_sh01_ff_raw.png` via Ideogram.
2. Align character identity using Flux Klein to produce `s01_sh01_ff.png`.

### Step 2: Derive Shot 1 LF
1. Use Flux Klein edit on `s01_sh01_ff.png` describing a small action/camera movement.
2. Output `s01_sh01_lf.png`.

### Step 3: Run FFLF on Shot 1
1. Run LTX-Video FFLF with `s01_sh01_ff.png` (first frame) and `s01_sh01_lf.png` (last frame).
2. Output `s01_sh01.mp4`.

### Step 4: Extract Tail Frame of Shot 1
1. Extract the final frame of `s01_sh01.mp4`.
2. Save it as `s01_sh02_ff.png`.
3. *Why?* This guarantees that when the user watches the transition from Shot 1 to Shot 2, there is a perfect 1-frame continuation.

### Step 5: Derive Shot 2 LF
1. Take `s01_sh02_ff.png` (the tail frame).
2. Apply Flux Klein edit on it describing the next action.
3. Output `s01_sh02_lf.png`.

### Step 6: Run FFLF on Shot 2
1. Run LTX-Video FFLF with `s01_sh02_ff.png` and `s01_sh02_lf.png`.
2. Output `s01_sh02.mp4`.

### Step 7: Extract Tail Frame of Shot 2
1. Extract the final frame of `s01_sh02.mp4`.
2. Save it as `s01_sh03_ff.png`.

### Step 8: Derive Shot 3 LF & Run FFLF
1. Apply Flux Klein edit on `s01_sh03_ff.png` to produce `s01_sh03_lf.png`.
2. Run FFLF on `s01_sh03_ff.png` and `s01_sh03_lf.png` to produce `s01_sh03.mp4`.

---

## 3. Python Tail Frame Extraction Implementation

The following python function (integrated in our orchestrator) is used to extract the tail frame from a generated video:

```python
import cv2

def extract_tail_frame(video_path, output_image_path):
    """
    Extracts the very last frame of a video file and saves it as an image.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Could not open video file {video_path}")
        
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # Set position to the last frame
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_count - 1)
    
    ret, frame = cap.read()
    if ret:
        cv2.imwrite(output_image_path, frame)
        print(f"✅ Extracted tail frame from {video_path} to {output_image_path}")
    else:
        raise ValueError(f"Failed to read the last frame of {video_path}")
        
    cap.release()
```
