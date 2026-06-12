# Story-to-Video Migration & Execution Analysis

This document summarizes the findings from the information gathering phase regarding our Hermes setup, the migration from the legacy monolithic `story-to-video-filmmaking` skill to the modular `story-production-orchestrator`, and our analysis of the execution logs for the `panda-pippin` board.

---

## 1. Hermes Setup & Agent Profiles

The story production pipeline has transitioned from a single-agent monolith to a multi-agent system managed via a **Hermes Kanban board**. Six specialist profiles collaborate to produce a film:

| Profile | Primary Skill | Core Responsibilities |
| :--- | :--- | :--- |
| **`stv-director`** | [story-direction](file:///root/.hermes/skills/creative/story-direction) | Expands raw story to `story_manifest.json` v3, approves character sheets, reviews FF/LF prompts and motion. |
| **`stv-t2i-writer`** | [flux-t2i-prompting](file:///root/.hermes/skills/creative/flux-t2i-prompting) | Generates character sheets (T2I) and drafts first-frame (FF) prompts. |
| **`stv-i2i-writer`** | [flux-edit-prompting](file:///root/.hermes/skills/creative/flux-edit-prompting) | Drafts last-frame (LF) prompts using Edit-Instruction format (I2I). |
| **`stv-motion-writer`** | [ltx-motion-prompting](file:///root/.hermes/skills/creative/ltx-motion-prompting) | Drafts motion and timing prompts. |
| **`stv-reviewer`** | [qc-image-review](file:///root/.hermes/skills/creative/qc-image-review) | Performs binary, evidence-based quality control checks on generated stills. |
| **`stv-ops`** | [comfyui-ops](file:///root/.hermes/skills/creative/comfyui-ops) | Interacts with ComfyUI to render stills, videos, and stitch final clips using ffmpeg. |

---

## 2. Past Execution Log Analysis (`panda-pippin` Board)

Checking the tasks on the `panda-pippin` board reveals the following status:

*   **`t_ba490a88` (T7-redo2) — `blocked`**: Assigned to `stv-i2i-writer`, crashed immediately twice. 
    *   *Error:* `Error: Unknown skill(s): flux-i2i-editing`.
*   **`t_75d3f24d` (T7-redo) — `blocked`**: Assigned to `stv-i2i-writer`, failed due to Turn/Iteration Budget Exhaustion (60/60 iterations used).
*   **`t_d5a0dbda` (T3: Character Sheets) — `done`**: Succeeded eventually but took an hour and exhausted the 60/60 iteration budget on the first attempt.

---

## 3. Root Cause Investigation

We investigated why these specific issues occur and how we can improve performance.

### Issue A: `Error: Unknown skill(s): flux-i2i-editing`
When the director (`stv-director`) reviewed prompts in the `T10` pre-flight stage and found that 13 LF prompts exceeded the 120-word hard cap, it dynamically created the task `T7-redo2` (`t_ba490a88`) via the `kanban_create` command. 

*   **Root Cause:** The `stv-director`'s instructions ([stv-director/SOUL.md](file:///root/.hermes/profiles/stv-director/SOUL.md)) do not contain an explicit profile-to-skill mapping. When creating tasks dynamically, the LLM hallucinated the skill name as `flux-i2i-editing` instead of the profile's actual skill `flux-edit-prompting`. Since no such skill is defined globally or symlinked to the profile, the dispatcher failed to launch the worker.

---

### Issue B: High Token Usage and Iteration Exhaustion (60/60 turns)
Analyzing the logs for `t_d5a0dbda` ([t_d5a0dbda.log](file:///root/.hermes/kanban/boards/panda-pippin/logs/t_d5a0dbda.log)) and `t_75d3f24d` ([t_75d3f24d.log](file:///root/.hermes/kanban/boards/panda-pippin/logs/t_75d3f24d.log)) reveals three compounding causes:

#### 1. ComfyUI Authentication Mismatch
The skill's default api helper ([comfyui_api.py](file:///root/repos/auto-startups-vast/current-setup/skills/story-to-video-filmmaking/scripts/comfyui_api.py)) is configured for Basic Authentication. However, the Cloudflare tunnel routing ComfyUI requests requires `Authorization: Bearer <token>` (the `COMFYUI_AUTH` env variable). 
*   **Impact:** The worker wasted several initial turns debugging HTTP 403 errors and writing custom curl wrappers to call ComfyUI via Bearer token.

#### 2. Aggressive Secret Redaction Mangling (Critical)
The Hermes system runs a security redact parser (`redact_secrets` in `config.yaml`). The parser matched variable names in the Python files written by the worker (such as `TOKEN_PATH = SCRIPT_DIR / ".comfyui_token"`) because they contained the word `token`.
*   **Impact:** The parser automatically mangled the files on disk, replacing `SCRIPT_DIR` with `***`, resulting in syntax like `TOKEN_PATH = *** / ".comfyui_token"`. This broke Python compilation.
*   **Loop:** The worker got trapped in a repetitive loop:
    1. Write script → 2. Scanner mangles it → 3. Run script → 4. Syntax Error → 5. Attempt patch → 6. Scanner mangles again.
    The agent eventually had to use base64/char-concatenation tricks (e.g., `chr(83) + chr(67)...` to construct `SCRIPT_DIR`) to bypass the mangler, consuming dozens of iterations.

#### 3. Strict QC Gates & Prompt Refinement Loops
The QC gate model (`google/gemini-3.1-flash-lite`) is binary and very strict. During character sheet generation, minor deviations (e.g., Pippin's mouth being slightly downturned/pouty in the front view, Bamboo having a slight smirk, or the leaf flipping ears on profile turn) triggered failures.
*   **Impact:** The agent had to implement prompt-refinement loops (prepending "EXPRESSION LOCK" instructions to the front of Flux prompts since Flux weights leftmost tokens most heavily) and re-render on ComfyUI with new seeds, multiplying execution time.

---

### Issue C: Fallback to Klein Templates (`flux-2-klein-t2i.json`)
The user noted that since migrating to the Flux 2 Dev Turbo model, workers sometimes still read the old `flux-2-klein-t2i.json` template.

*   **Root Cause:** In the shared workflow generation helper ([workflow_builder.py](file:///root/repos/auto-startups-vast/current-setup/skills/story-to-video-filmmaking/scripts/workflow_builder.py#L405-L410)), there is a fallback block:
    ```python
    if builder_type == "flux_reference_chain" and num_refs == 0:
        # Auto-switch to T2I template (no references)
        print("   🔄 Zero references — auto-switching to flux-2-klein-t2i template")
        t2i_template = load_workflow_template("flux-2-klein-t2i")
        return build_dynamic_workflow(t2i_template, shot_data, global_cfg)
    ```
    If the workflow template metadata specifies the legacy builder `"flux_reference_chain"` and references is empty, it switches to the hardcoded `flux-2-klein-t2i` template. The newer `"flux_dev_turbo_chain"` builder handles zero references natively by disabling the reference switch inside the same template without loading a fallback.

---

## 4. Proposed Fixes & Recommendations

To resolve these issues, we recommend the following changes:

### 1. Fix Director Task Creation (Skill Names)
Inject the explicit profile-to-skill map into the instructions of the director agent.
*   **Action:** Update the `stv-director` [SOUL.md](file:///root/.hermes/profiles/stv-director/SOUL.md) so that it knows:
    > "When creating or assigning tasks to **`stv-i2i-writer`**, you must always specify the skill **`flux-edit-prompting`** (NOT `flux-i2i-editing`)."

### 2. Standardize Bearer Auth & Avoid Mangling
*   **Action:** Update the common ComfyUI API helper in `comfyui_api.py` to check for a bearer token structure and automatically format headers as `Authorization: Bearer <token>` if no Basic colon is present.
*   **Action:** In card instructions created by the orchestrator ([build_kanban_board.py](file:///root/repos/auto-startups-vast/current-setup/skills/story-production-orchestrator/scripts/build_kanban_board.py)), warn the profiles:
    > "Do not write literal token paths or assign variables with names containing 'token' or 'auth' in a way that triggers system secret redaction. Read auth keys from environment variables (`COMFYUI_AUTH`) instead."

### 3. Update Workflow Fallback Logic
*   **Action:** Update the fallback in [workflow_builder.py](file:///root/repos/auto-startups-vast/current-setup/skills/story-to-video-filmmaking/scripts/workflow_builder.py#L408) to load the newer T2I template (`flux-2-dev-turbo` or a dedicated turbo T2I json) instead of `flux-2-klein-t2i`, or ensure all manifests specify `"flux_dev_turbo_chain"` as their builder.
