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


def extract_continuation_frame(video_path, overlap_seconds=1.0, fps=25, output_path=None):
    """Extract the start-of-overlap frame from the tail of a video.
    
    If the video has N frames and overlap is O frames:
    We extract the frame at index N - O.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
        
    num_frames = get_video_frame_count(video_path)
    overlap_frames = int(overlap_seconds * fps)
    
    # Calculate target index (ensure it doesn't go negative or out of bounds)
    target_idx = max(0, num_frames - overlap_frames)
    
    if output_path is None:
        base, _ = os.path.splitext(video_path)
        output_path = f"{base}_ff_extracted.png"
        
    print(f"   🎞️  Extracting frame {target_idx}/{num_frames} from: {os.path.basename(video_path)}")
    
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", fr"select=eq(n\,{target_idx})",
        "-vframes", "1", output_path
    ]
    
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(output_path):
            print(f"   ✅ Saved context buffer frame: {output_path} ({os.path.getsize(output_path)/1024:.1f} KB)")
            return output_path
    except Exception as e:
        raise RuntimeError(f"Failed to extract frame using ffmpeg: {e}")
        
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
        
    # Generate ffmpeg filter_complex command
    # Trims each file and concats them
    filter_parts = []
    concat_inputs = ""
    for i, seg in enumerate(segments):
        filter_parts.append(f"[{i}:v]trim=end_frame={seg['trim_end_frame']},setpts=PTS-STARTPTS[v{i}]")
        concat_inputs += f"[v{i}]"
        
    filter_complex_str = "; ".join(filter_parts)
    filter_complex_str += f"; {concat_inputs}concat=n={len(segments)}:v=1:a=0[outv]"
    
    inputs_str = " ".join(f"-i {seg['file']}" for seg in segments)
    ffmpeg_cmd = f"ffmpeg {inputs_str} -filter_complex \"{filter_complex_str}\" -map \"[outv]\" stitched_output.mp4"
    
    metadata = {
        "overlap_seconds": overlap_seconds,
        "fps": fps,
        "total_segments": len(video_files),
        "total_duration_seconds": total_trimmed_duration,
        "segments": segments,
        "ffmpeg_concat_command": ffmpeg_cmd,
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
