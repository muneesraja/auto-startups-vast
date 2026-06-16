#!/usr/bin/env python3
"""
PipelineLogger: Dual-output logging (stdout + file) and progress/status tracking in JSON format.
"""

import json
import os
import datetime

class PipelineLogger:
    """Dual-output logger: stdout + pipeline_run.log + pipeline_status.json"""

    def __init__(self, output_dir, run_id, total_shots, total_characters, waves_plan):
        """
        Args:
            output_dir: Root output directory for the run
            run_id: Unique run identifier (e.g., "run_20260614_153000")
            total_shots: Total number of shots in the story
            total_characters: Total number of characters
            waves_plan: Dict mapping wave names to lists of item IDs
                        e.g., {"wave_0_character_sheets": ["pippin", "miko"],
                               "wave_1_ideogram_ffs": ["s01_sh01", "s01_sh03"]}
        """
        self.output_dir = output_dir
        self.run_id = run_id
        self.total_shots = total_shots
        self.total_characters = total_characters
        self.waves_plan = waves_plan

        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)

        self.log_file_path = os.path.join(self.output_dir, "pipeline_run.log")
        self.status_file_path = os.path.join(self.output_dir, "pipeline_status.json")

        # Open log file in append mode
        self.log_fh = open(self.log_file_path, "a", encoding="utf-8")

        # Initialize status json
        self._init_status_json()

    def _init_status_json(self):
        """Initializes the pipeline_status.json file with all waves set to pending."""
        now_str = datetime.datetime.now().isoformat() + "Z"
        
        waves_data = {}
        for wave_name, items in self.waves_plan.items():
            items_data = {}
            for item_id in items:
                items_data[item_id] = {
                    "status": "pending",
                    "output": None,
                    "error": None
                }
            waves_data[wave_name] = {
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "items": items_data
            }

        status_dict = {
            "run_id": self.run_id,
            "started_at": now_str,
            "updated_at": now_str,
            "status": "running",
            "current_wave": None,
            "progress_pct": 0,
            "total_shots": self.total_shots,
            "total_characters": self.total_characters,
            "waves": waves_data,
            "summary": {
                "videos_generated": 0,
                "evaluations_passed": 0,
                "evaluations_failed": 0,
                "errors": []
            }
        }
        self._write_status(status_dict)

    def _write_status(self, status_dict):
        """Write status_dict to pipeline_status.json atomically."""
        tmp_path = self.status_file_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(status_dict, f, indent=2)
            os.replace(tmp_path, self.status_file_path)
        except Exception as e:
            # Fallback direct write if replace fails
            try:
                with open(self.status_file_path, "w", encoding="utf-8") as f:
                    json.dump(status_dict, f, indent=2)
            except Exception as inner_e:
                self.log(f"Failed to write status JSON: {inner_e}", "ERROR")

    def get_status(self):
        """Read and return the current pipeline_status.json dict."""
        if os.path.exists(self.status_file_path):
            try:
                with open(self.status_file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                self.log(f"Failed to read status JSON: {e}", "ERROR")
        return None

    def log(self, message, level="INFO"):
        """Write to both stdout and pipeline_run.log with ISO timestamp."""
        now_str = datetime.datetime.now().isoformat()
        formatted = f"[{now_str}] [{level}] {message}"
        
        # Write to stdout
        print(formatted)
        
        # Write to log file
        try:
            self.log_fh.write(formatted + "\n")
            self.log_fh.flush()
        except Exception as e:
            print(f"Error writing to log file: {e}")

    def update_wave(self, wave_name, status):
        """Update a wave's overall status."""
        status_dict = self.get_status()
        if not status_dict:
            return

        now_str = datetime.datetime.now().isoformat() + "Z"
        status_dict["updated_at"] = now_str
        
        if wave_name in status_dict["waves"]:
            wave_info = status_dict["waves"][wave_name]
            wave_info["status"] = status
            if status == "in_progress" or status == "running":
                wave_info["started_at"] = now_str
                status_dict["current_wave"] = wave_name
            elif status == "completed" or status == "failed":
                wave_info["completed_at"] = now_str
                
                # Check if all waves are completed
                all_done = True
                for w_name, w_data in status_dict["waves"].items():
                    if w_data["status"] not in ["completed", "failed", "skipped"]:
                        all_done = False
                        break
                if all_done:
                    status_dict["status"] = "completed"
                    status_dict["current_wave"] = None

        self._recalculate_progress_and_summary(status_dict)
        self._write_status(status_dict)

    def update_item(self, wave_name, item_id, status, output=None, eval_score=None, error=None, eval_result=None):
        """Update a specific item's status in pipeline_status.json.
        
        Args:
            wave_name: e.g., "wave_0_character_sheets"
            item_id: e.g., "pippin" or "s01_sh01"
            status: "pending" | "running" | "completed" | "failed" | "skipped"
            output: Output filename if completed
            eval_score: Quality gate score if evaluated
            error: Error message string if failed
            eval_result: Detailed evaluation dict (e.g. quality gate JSON)
        """
        status_dict = self.get_status()
        if not status_dict:
            return

        now_str = datetime.datetime.now().isoformat() + "Z"
        status_dict["updated_at"] = now_str

        if wave_name in status_dict["waves"]:
            wave_info = status_dict["waves"][wave_name]
            # Ensure items structure exists
            if "items" not in wave_info:
                wave_info["items"] = {}
            
            # Update or create item
            item_data = wave_info["items"].setdefault(item_id, {})
            item_data["status"] = status
            
            if output is not None:
                item_data["output"] = output
            if error is not None:
                item_data["error"] = error
                if error not in status_dict["summary"]["errors"]:
                    status_dict["summary"]["errors"].append(error)
            
            if eval_score is not None:
                item_data["eval_score"] = eval_score
            
            if eval_result is not None:
                item_data["eval"] = eval_result
                # Update evaluations count
                passed = eval_result.get("passed", False) or eval_result.get("overall_score", 0) >= 6 or eval_result.get("overall", 0) >= 6
                if passed:
                    status_dict["summary"]["evaluations_passed"] += 1
                else:
                    status_dict["summary"]["evaluations_failed"] += 1

        self._recalculate_progress_and_summary(status_dict)
        self._write_status(status_dict)

    def _recalculate_progress_and_summary(self, status_dict):
        """Recalculates progress_pct based on completed items / total items across all waves."""
        total_items = 0
        completed_items = 0
        
        # Count videos generated
        videos_count = 0

        for wave_name, wave_info in status_dict["waves"].items():
            for item_id, item_data in wave_info.get("items", {}).items():
                total_items += 1
                if item_data.get("status") in ["completed", "failed", "skipped"]:
                    completed_items += 1
                
                # If this item generated an MP4/video in a video wave, increment count
                if item_data.get("status") == "completed" and wave_name.endswith("video_eval") or "fflf" in wave_name:
                    if item_data.get("output") and (item_data["output"].endswith(".mp4") or "video" in item_id):
                        videos_count += 1
        
        if total_items > 0:
            status_dict["progress_pct"] = int((completed_items / total_items) * 100)
        else:
            status_dict["progress_pct"] = 0
            
        # Update stitched videos summary count from actual files in videos list if we can
        # Let's count keys in state["videos"] equivalent or just count files in wave_3/wave_n completed
        status_dict["summary"]["videos_generated"] = videos_count

    def close(self):
        """Flush and close the log file."""
        if hasattr(self, "log_fh") and self.log_fh:
            try:
                self.log_fh.flush()
                self.log_fh.close()
            except Exception:
                pass
