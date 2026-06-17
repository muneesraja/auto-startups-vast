# Progress Log: V12 Story-to-Video Naming Conventions & Counter Resolution

## Objective
Implement a robust naming scheme that prefixes all generated image and video assets with the story folder name (e.g. `rabbit-forest-rescue_`). Furthermore, adapt the orchestrator waves to save files locally using their exact server-returned filenames (which include ComfyUI-generated counters like `_00004_`) and resolve these files dynamically via a new `find_latest_file` helper.

## Design Details
1. **Dynamic Story Name Prefixing**:
   * Extract parent directory name of the prompts path as `self.story_name`.
   * Modify the orchestrator `_flatten_shots` to prefix `filename_prefix` and `continues_from` with `self.story_name`.
   * Prefix character sheet filenames as `f"{self.story_name}_{char_id}_character_sheet.png"`.

2. **Counter Suffix Resolution (`find_latest_file`)**:
   * Locate the file with the highest numerical counter (e.g., `prefix_(\d+)_\.extension`) in the target output folder.
   * If no counter file is present, fall back to matching files starting with `prefix` and ending with `extension`.
   * Apply this resolution across all waves to dynamically determine skip conditions and input file paths.

## Next Steps
* Await user approval on the implementation plan.
* Perform file renaming on the existing character sheets.
* Implement code modifications in `filmmaking_utils.py`, `cinematic_orchestrator.py`, and `wave_executors.py`.
* Verify via dry run and execution with `--skip-existing`.
