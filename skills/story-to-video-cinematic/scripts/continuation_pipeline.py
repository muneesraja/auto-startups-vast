#!/usr/bin/env python3
"""
Story-to-Video-Filmmaking: Continuation Pipeline (Phase 4 & 5)
============================================================
Handles context buffer extraction (tail frames) from completed videos,
and generates post-production stitching instructions and ffmpeg concat commands.
"""
import argparse
import json
import os
import subprocess
import sys

# Reuse helper from motion_evaluator to get frame count
try:
    from motion_evaluator import get_video_frame_count
except ImportError:
    def get_video_frame_count(video_path):
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=nb_frames", "-of", "default=nokey=1:noprint_wrappers=1",
            video_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            val = result.stdout.strip()
            if val and val.isdigit():
                return int(val)
        except Exception:
            pass
        return 125  # Fallback: 5s at 25fps


def extract_continuation_frame(video_path, overlap_seconds=1.0, fps=25, output_path=None,
                                target_lf_path=None, quality_threshold=0.3):
    """Extract the best continuation frame from the tail of a video.

    Adaptive extraction strategy (P0.6):
    1. Extract 3 candidate frames: last frame, last-0.5s, last-1.0s
    2. If target_lf_path is provided, compute SSIM against each candidate
       and pick the one closest to the target LF composition
    3. If SSIM of best candidate is below quality_threshold, emit a warning
       (P0.5 quality gate)

    Falls back to single-frame extraction if SSIM dependencies are unavailable.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    num_frames = get_video_frame_count(video_path)

    if output_path is None:
        base, _ = os.path.splitext(video_path)
        output_path = f"{base}_ff_extracted.png"

    # Define candidate frame indices (last frame, -0.5s, -1.0s)
    candidate_offsets = [
        ("last_frame", max(0, num_frames - 1)),
        ("last_0.5s", max(0, num_frames - int(0.5 * fps))),
        ("last_1.0s", max(0, num_frames - int(1.0 * fps))),
    ]
    # De-duplicate if video is very short
    seen_indices = set()
    candidates = []
    for label, idx in candidate_offsets:
        if idx not in seen_indices:
            candidates.append((label, idx))
            seen_indices.add(idx)

    # If no target LF or only one candidate, fall back to original behavior
    if not target_lf_path or not os.path.exists(target_lf_path) or len(candidates) == 1:
        # Use the overlap-based frame (original behavior)
        overlap_frames = int(overlap_seconds * fps)
        target_idx = max(0, num_frames - overlap_frames)
        print(f"   🎞️  Extracting frame {target_idx}/{num_frames} from: {os.path.basename(video_path)}")
        return _extract_single_frame(video_path, target_idx, output_path)

    # Adaptive extraction: extract all candidates and compare to target LF
    print(f"   🎞️  Adaptive extraction: testing {len(candidates)} candidate frames against target LF")
    
    base_dir = os.path.dirname(output_path)
    base_name = os.path.splitext(os.path.basename(output_path))[0]
    candidate_paths = []

    for label, idx in candidates:
        cand_path = os.path.join(base_dir, f"{base_name}_cand_{label}.png")
        extracted = _extract_single_frame(video_path, idx, cand_path, quiet=True)
        if extracted:
            candidate_paths.append((label, idx, cand_path))

    if not candidate_paths:
        raise RuntimeError("Failed to extract any candidate frames")

    # Compute SSIM for each candidate against target LF
    best_ssim = -1.0
    best_candidate = candidate_paths[0]  # fallback to first
    ssim_available = True

    for label, idx, cand_path in candidate_paths:
        ssim_score = _compute_ssim(cand_path, target_lf_path)
        if ssim_score is None:
            ssim_available = False
            break
        print(f"      [{label}] frame {idx}: SSIM = {ssim_score:.4f}")
        if ssim_score > best_ssim:
            best_ssim = ssim_score
            best_candidate = (label, idx, cand_path)

    if not ssim_available:
        # SSIM not available — fall back to last-1.0s (original behavior)
        print("      ⚠️ SSIM comparison unavailable — falling back to overlap-based extraction")
        overlap_frames = int(overlap_seconds * fps)
        target_idx = max(0, num_frames - overlap_frames)
        # Cleanup candidate files
        for _, _, cand_path in candidate_paths:
            if os.path.exists(cand_path):
                os.remove(cand_path)
        return _extract_single_frame(video_path, target_idx, output_path)

    # Use best candidate
    best_label, best_idx, best_path = best_candidate
    print(f"   ✅ Best candidate: [{best_label}] frame {best_idx} (SSIM: {best_ssim:.4f})")

    # Quality gate (P0.5): warn if best SSIM is below threshold
    if best_ssim < quality_threshold:
        print(f"   ⚠️ QUALITY GATE WARNING: Best tail frame SSIM ({best_ssim:.4f}) is below "
              f"threshold ({quality_threshold}). The video likely drifted far from the target LF.")
        print(f"   ⚠️ Consider regenerating the FF for the next shot from scratch instead of "
              f"using this degraded tail frame.")

    # Move best candidate to output path
    import shutil
    if best_path != output_path:
        shutil.copy2(best_path, output_path)

    # Cleanup other candidate files
    for _, _, cand_path in candidate_paths:
        if cand_path != output_path and os.path.exists(cand_path):
            os.remove(cand_path)

    size = os.path.getsize(output_path)
    print(f"   ✅ Saved context buffer frame: {output_path} ({size/1024:.1f} KB)")
    return output_path


def _extract_single_frame(video_path, frame_idx, output_path, quiet=False):
    """Extract a single frame from a video at the given index."""
    if not quiet:
        print(f"   🎞️  Extracting frame {frame_idx} from: {os.path.basename(video_path)}")

    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", fr"select=eq(n\,{frame_idx})",
        "-vframes", "1", output_path
    ]

    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(output_path):
            if not quiet:
                print(f"   ✅ Saved context buffer frame: {output_path} ({os.path.getsize(output_path)/1024:.1f} KB)")
            return output_path
    except Exception as e:
        if not quiet:
            raise RuntimeError(f"Failed to extract frame using ffmpeg: {e}")
        print(f"      ⚠️ Failed to extract frame {frame_idx}: {e}")

    return None


def _compute_ssim(image_a_path, image_b_path):
    """Compute structural similarity (SSIM) between two images using ffmpeg.
    
    Returns SSIM score (0.0-1.0) or None if computation fails.
    """
    cmd = [
        "ffmpeg", "-i", image_a_path, "-i", image_b_path,
        "-lavfi", "ssim", "-f", "null", "-"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        # Parse SSIM from ffmpeg stderr output
        # Format: "SSIM Y:0.950123 (13.021234) U:... V:... All:0.945678 (12.654321)"
        for line in result.stderr.split("\n"):
            if "All:" in line:
                import re
                match = re.search(r"All:([\d.]+)", line)
                if match:
                    return float(match.group(1))
    except Exception:
        pass
    return None


def generate_stitch_metadata(video_files, overlap_seconds=1.0, fps=25, output_json_path=None):
    """Generate trimming and concatenation instructions for a list of video files."""
    segments = []
    total_trimmed_duration = 0.0
    
    for i, file_path in enumerate(video_files):
        num_frames = get_video_frame_count(file_path)
        duration = num_frames / fps
        overlap_frames = int(overlap_seconds * fps)
        
        # Last segment is not trimmed at the end
        if i == len(video_files) - 1:
            trim_end_frame = num_frames
            trimmed_duration = duration
        else:
            trim_end_frame = max(1, num_frames - overlap_frames)
            trimmed_duration = trim_end_frame / fps
            
        segments.append({
            "index": i,
            "file": os.path.abspath(file_path),
            "basename": os.path.basename(file_path),
            "original_frames": num_frames,
            "original_duration": duration,
            "trim_end_frame": trim_end_frame,
            "trimmed_duration": trimmed_duration
        })
        total_trimmed_duration += trimmed_duration
        
    # Generate ffmpeg filter_complex commands
    
    # Method 1: Simple trim + concat (removes overlap region entirely)
    filter_parts = []
    concat_inputs = ""
    for i, seg in enumerate(segments):
        filter_parts.append(f"[{i}:v]trim=end_frame={seg['trim_end_frame']},setpts=PTS-STARTPTS[v{i}]")
        concat_inputs += f"[v{i}]"
        
    filter_complex_str = "; ".join(filter_parts)
    filter_complex_str += f"; {concat_inputs}concat=n={len(segments)}:v=1:a=0[outv]"
    
    inputs_str = " ".join(f"-i {seg['file']}" for seg in segments)
    ffmpeg_trim_cmd = f"ffmpeg -y {inputs_str} -filter_complex \"{filter_complex_str}\" -map \"[outv]\" stitched_output.mp4"
    
    # Method 2: Crossfade with xfade (smoother transitions — recommended)
    # Uses xfade filter to blend overlap regions instead of hard cutting
    if len(segments) >= 2:
        xfade_parts = []
        xfade_inputs = ""
        for i, seg in enumerate(segments):
            xfade_inputs += f"-i {seg['file']} "
        
        # Build chained xfade filters
        # First pair: [0:v][1:v]xfade=transition=fade:duration=D:offset=O[xf0]
        # Subsequent: [xf0][2:v]xfade=...
        running_offset = 0.0
        xfade_chain = []
        for i in range(len(segments) - 1):
            seg_dur = segments[i]["trimmed_duration"]
            running_offset += seg_dur - overlap_seconds
            
            if i == 0:
                src = "[0:v]"
                dst = "[1:v]"
            else:
                src = f"[xf{i-1}]"
                dst = f"[{i+1}:v]"
            
            out_label = f"[xf{i}]" if i < len(segments) - 2 else "[outv]"
            xfade_chain.append(
                f"{src}{dst}xfade=transition=fade:duration={overlap_seconds}:offset={running_offset:.3f}{out_label}"
            )
        
        xfade_filter = "; ".join(xfade_chain)
        ffmpeg_xfade_cmd = f"ffmpeg -y {xfade_inputs.strip()} -filter_complex \"{xfade_filter}\" -map \"[outv]\" stitched_xfade_output.mp4"
    else:
        ffmpeg_xfade_cmd = ffmpeg_trim_cmd  # Single segment, no crossfade needed
    
    metadata = {
        "overlap_seconds": overlap_seconds,
        "fps": fps,
        "total_segments": len(video_files),
        "total_duration_seconds": total_trimmed_duration,
        "segments": segments,
        "ffmpeg_trim_concat_command": ffmpeg_trim_cmd,
        "ffmpeg_xfade_command": ffmpeg_xfade_cmd,
        "davinci_resolve_instructions": (
            f"1. Import all {len(video_files)} clips into DaVinci Resolve.\n"
            f"2. Align each clip sequentially on the timeline.\n"
            f"3. For each overlapping pair (clip i and clip i+1):\n"
            f"   - Place clip i+1 on track 2, overlapping the last {overlap_seconds} seconds of clip i.\n"
            f"   - Align the start of clip i+1 exactly with the overlap start point in clip i.\n"
            f"   - Add a crossfade transition over the {overlap_seconds} second overlap region for smooth blend."
        )
    }
    
    if output_json_path:
        with open(output_json_path, "w") as f:
            json.dump(metadata, f, indent=2)
            
    return metadata


# ── CLI Main ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Story-to-Video-Filmmaking: Continuation Stitching Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--test-extract", type=str, default=None,
                        help="Path to a video to test extracting the context frame")
    parser.add_argument("--overlap", type=float, default=1.0,
                        help="Overlap region duration in seconds (default: 1.0)")
    parser.add_argument("--fps", type=int, default=25,
                        help="Video frame rate (default: 25)")
    parser.add_argument("--output-img", type=str, default=None,
                        help="Target output image path for extraction")
                        
    parser.add_argument("--stitch", nargs="+", default=None,
                        help="Stitch a list of video files together sequentially")
    parser.add_argument("--output-metadata", type=str, default="stitch_metadata.json",
                        help="Output JSON path for stitching instructions (default: stitch_metadata.json)")

    args = parser.parse_args()
    
    # 1. Run extraction test
    if args.test_extract:
        try:
            out = extract_continuation_frame(
                video_path=args.test_extract,
                overlap_seconds=args.overlap,
                fps=args.fps,
                output_path=args.output_img
            )
            if out:
                print(f"🎉 Success: frame extracted to {out}")
        except Exception as e:
            print(f"❌ Extraction failed: {e}")
            sys.exit(1)
            
    # 2. Run stitching generator
    elif args.stitch:
        print(f"🔗 Generating stitching metadata for {len(args.stitch)} video files...")
        try:
            meta = generate_stitch_metadata(
                video_files=args.stitch,
                overlap_seconds=args.overlap,
                fps=args.fps,
                output_json_path=args.output_metadata
            )
            print(f"🎉 Success: metadata saved to {args.output_metadata}")
            print(f"   Total Duration: {meta['total_duration_seconds']:.2f}s")
            print(f"\n   Run this command to stitch using ffmpeg:\n   {meta['ffmpeg_concat_command']}")
        except Exception as e:
            print(f"❌ Stitch metadata generation failed: {e}")
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
