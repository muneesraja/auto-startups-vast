# V21 — Reference Images Passing Review

**Date:** 2026-06-23  
**Status:** Review Complete

## Summary

Reviewed the `panda_test` dry run outputs to validate that `reference_images` arrays are correctly populated per the [User-Plan-V2-cloud](file:///Users/pandismart/Documents/projects/auto-startups-vast/discussion-and-docs/deterministic-implementation-resource/User-Plan-V2-cloud.md) requirements.

## Findings

### ✅ Passing
- **FF shots**: Character sheets correctly referenced for all characters in `characters_present`
- **LF shots**: FF image always first in `reference_images`, character sheets follow
- **Continuation shots**: Correctly set to `extracted_frame` with empty refs
- **Deduplication**: Handled programmatically in reference_integrity_node
- **7-ref Grok limit**: Enforced with spatial priority truncation
- **Wave 1/2 split**: Correct — FF-first shots in wave 1, continuations in wave 2
- **Motion prompts**: Correctly reference both FF and LF output_paths

### ⚠️ Gaps
1. **Multi-character path untested**: Panda test has only 1 character. Code handles multi-char correctly but no end-to-end dry run validates it.
2. **Prompt text coverage gap**: The reference_integrity_node fixes `reference_images` arrays but cannot validate whether the LLM omitted a character from the **prompt text** itself.

## Recommendations
1. Run a multi-character dry run (2-3 chars per scene)
2. Consider a prompt-text validator that checks character mention coverage in the prompt string
