# V16 — Story to Video Deterministic Skill Progress & Verification (Leo Story)

**Date:** 2026-06-18  
**Status:** In Progress (Generating Leo Story)

---

## 1. Milestones Reached
- **Model Switching:** Switched model configurations to run lightweight tasks on `openai/MiniMax-M2.7-highspeed` and reasoning tasks on `openai/MiniMax-M3`.
- **API Key & SDK Verification:** Successfully queried both models using Google ADK and validated their responses.
- **ComfyUI Connectivity:** The user updated `.env` with a live Cloudflare tunnel URL (`https://trio-temporal-collar-comment.trycloudflare.com`) and updated token. Connectivity test returned `401` (successful authentication challenge) rather than `NXDOMAIN` or timeout.
- **API Latency Diagnostic:** Verified that `openai/MiniMax-M3` and `openai/MiniMax-M2.7-highspeed` are fully responsive but exhibit high latency (approx. 3-4 minutes per call for large outputs like the screenplay or blueprint JSONs). Discovered that 30s/60s socket read timeouts in our scratch scripts were due to this expected model response time.
- **Auto-Save Resilience:** Modified `main.py` to auto-save intermediate files (`Director_script.md`, structural and visual blueprints, and `prompts.json`) after each step completes. If any downstream step fails or the task is interrupted, all previous steps' progress is persisted.

## 2. In-Progress Action
We are running the deterministic generation pipeline for the new story **"Leo"** located at [Leo/Story.md](file:///Users/muneesraja/Documents/growthlabs-vault/story-to-video-cinematic/Leo/Story.md).

Command:
```bash
python3 -u main.py --story "/Users/muneesraja/Documents/growthlabs-vault/story-to-video-cinematic/Leo/Story.md" --name "leo_adventure"
```

## 3. Goals of this Run
1. Generate the director script and visual blueprints.
2. Produce structured prompts for characters, first/last frames, consistency patches, and motion.
3. Queue Wave 1 (Character sheet, first frames, last frames) to ComfyUI.
4. Queue Wave 2 (LTX video generation using reference frame injection) to ComfyUI.
5. Verify output assets inside the `leo_adventure` directory.
