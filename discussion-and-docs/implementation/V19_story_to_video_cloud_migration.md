# V19 — Story-to-Video Cloud Migration Architecture

**Date:** 2026-06-23
**Status:** Architecture Review — Awaiting Approval (v3)

## Summary

Architecture plan for migrating `story-to-video-deterministic` to `story-to-video-cloud`:
- **Image backend**: Ideogram 4 + Flux Klein 9B (ComfyUI) → Grok Imagine (fal.ai)
- **Video workflow**: `ltx-23-fflf-seed-hunter.json` → `ltx-2.3-flf2v.json`
- **New agents**: FFLF Visual Planner (Step 1.5), Reference Integrity Node (Step 4.6)
- **Deprecated**: consistency_prompter, lf_consistency_prompter
- **Cost**: ~$0.43/story (10 shots, 3 chars) for images via fal.ai

## v3 Changes
- **NEW: FFLF Visual Planner Agent (Step 1.5)** — Separates visual composition planning from the director's narrative script. Takes the Director_script.md and produces per-shot FF/LF composition plans: how characters enter frame, camera framing, what changes between FF and LF. This feeds into Blueprint Visuals for enrichment.
- **LTX Workflow Migration** — From `ltx-23-fflf-seed-hunter.json` (multi-seed trial) to `ltx-2.3-flf2v.json` (single-pass FLF2V with spatial upsampler, 24fps, 1280×720 with upscale)

## Pipeline (11 steps)
```
1.   Director Script Agent        (MODIFIED — narrative only)
1.5  FFLF Visual Planner          ★ NEW — shot composition
2a.  Blueprint Structure          (unchanged)
2b.  Blueprint Visuals            (MODIFIED — consumes FFLF plan)
3.   Character Sheet Prompter     (MODIFIED → grok_t2i)
4.   Char Spatial Mapper          (unchanged)
4.5  FF Shot Prompter             (MODIFIED → grok_edit + refs)
4.6  Reference Integrity Node     ★ NEW — FunctionNode
5.   LF Delta Planner             (unchanged)
5.5  LF Shot Prompter             (MODIFIED → grok_edit + FF + char refs)
     Reference Integrity Check    (2nd pass)
6.   Motion Prompter              (MODIFIED — simplified refs)
7.   Validate Prompts             (MODIFIED — new rules)
8.   Wave Organizer               (unchanged)
9.   Wave Executor                (MODIFIED — fal.ai + ltx-2.3-flf2v.json)
```

## Full Architecture
See implementation plan artifact for detailed Mermaid diagrams, FFLF Visual Planner output format, LTX workflow node mappings, and complete file structure.
