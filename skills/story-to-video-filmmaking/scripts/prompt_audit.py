#!/usr/bin/env python3
"""
Pre-flight FF ↔ LF text-based risk audit for story-to-video-filmmaking.

Reads a filmmaking_prompt.json and checks every shot's first_frame_prompt and
last_frame_prompt for the failure modes the elephant story exposed (frozen,
subtle, radical). Pure text analysis — no images, no API calls, no GPU.

Usage:
    python3 scripts/prompt_audit.py path/to/filmmaking_prompt.json

Output:
    - Console: per-shot risk table + summary
    - Markdown: feedback/ff_lf_audit_preflight.md (per-shot risks + suggestions)

Heuristics (text-only):
    - frozen_risk:  text similarity > 0.85 + no spatial-delta keywords in LF
    - subtle_risk:  presence of expression/eyes/mouth words without spatial-delta words
    - radical_risk: presence of "different location" / "new place" / "meanwhile" /
                    "later" / "elsewhere" OR no shared character nouns between FF and
                    LF OR break_continuity: true not set when it should be

Not perfect. Text-only, can't see actual images. Catches obvious cases
cheaply (0.5% of post-render audit cost). False positives expected and easy
to dismiss. False negatives caught by the post-render audit.
"""
import argparse
import difflib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime


# ── Keyword sets (calibrated on elephant story 2026-06-11) ─────────

# Words that signal a spatial-delta in the LF. If the LF has NONE of these
# and is very similar to the FF, it's a frozen risk.
SPATIAL_DELTA_KEYWORDS = {
    # movement verbs
    "stepping", "released", "releasing", "turning", "leaning", "looking",
    "pushing in", "push in", "pulling back", "pull back", "zooming", "zoom",
    "panning", "tilt", "lowering", "raising", "lifting", "lowering",
    "reaching", "gripping", "walking", "running", "stopping", "starting",
    "falling", "rising", "jumping", "landing", "sliding", "pressing",
    "pulling", "pushing", "twisting", "bending", "crouching", "standing",
    "sitting", "kneeling", "crawling", "climbing", "descending", "ascending",
    "dropping", "scooping", "carrying", "throwing", "catching", "wading",
    "diving", "surfacing", "emerging", "submerging",
    # explicit motion nouns
    "mouth", "eyes", "expression", "eyebrows", "grip firming", "grip loosening",
    "body deflat", "body sags", "body inflates", "body tense", "body relax",
    "weight shift", "weight transfer", "sigh", "exhale", "inhale",
    "ear", "ears", "tail", "wings", "arms", "legs", "trunk", "snout",
    "water drips", "dust rises", "leaves flutter", "leaves fall",
    "camera", "framing", "shot", "wider", "tighter", "closer", "farther",
    "behind her", "behind him", "in front of her", "in front of him",
    "in the background", "in the foreground", "now smaller", "now larger",
    "above", "below", "to the left", "to the right", "left side", "right side",
    "spine", "shoulders", "head tilt", "chin", "cheek", "brow",
    # camera & composition
    "medium", "close-up", "closeup", "wide", "establishing", "over-the-shoulder",
    "dutch angle", "low angle", "high angle", "eye level", "birds-eye",
}

# Words that suggest an expression-only change. By themselves, these mean
# subtle risk (no real spatial motion).
EXPRESSION_KEYWORDS = {
    "expression", "eyes", "mouth", "eyebrow", "brow", "gaze", "look", "stare",
    "sigh", "exhale", "inhale", "smile", "frown", "grimace", "grip firming",
    "grip loosening", "ears pinned", "ears lift", "ears unpin", "ears flop",
    "blinking", "winking", "squinch", "squint",
}

# Words that suggest the LF is in a different scene (radical risk).
SCENE_CHANGE_KEYWORDS = {
    "different location", "new place", "new location", "meanwhile", "later",
    "elsewhere", "in another", "across the", "far away", "miles away",
    "next morning", "next day", "hours later", "suddenly",
}

# Common stopwords to ignore when comparing text similarity
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "should", "could", "may", "might", "must", "shall", "can",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as", "into",
    "through", "during", "before", "after", "above", "below", "up", "down",
    "out", "off", "over", "under", "again", "further", "then", "once",
    "this", "that", "these", "those", "i", "me", "my", "we", "our", "you",
    "your", "he", "she", "it", "they", "them", "their", "his", "her", "its",
}


def tokenize(text):
    """Lowercase + split on non-alpha + remove stopwords."""
    if not text:
        return []
    text = text.lower()
    words = re.findall(r"[a-z]+(?:'[a-z]+)?", text)
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def text_similarity(a, b):
    """SequenceMatcher ratio of two strings. 0.0 to 1.0."""
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def keyword_count(text, keywords):
    """Count how many of the keywords appear in the text (whole-phrase aware)."""
    if not text:
        return 0
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw in text_lower)


def shared_noun_ratio(ff_tokens, lf_tokens):
    """Ratio of character/content nouns shared between FF and LF token sets.

    Returns 0.0 (no shared nouns) to 1.0 (fully shared). Drops high-frequency
    English nouns to focus on content.
    """
    if not ff_tokens or not lf_tokens:
        return 0.0
    # Get unique token sets
    ff_set = set(ff_tokens)
    lf_set = set(lf_tokens)
    # Drop very common English nouns
    common_nouns = {
        "frame", "shot", "camera", "image", "background", "foreground", "color",
        "light", "lighting", "mood", "style", "scene", "shot", "view",
    }
    ff_set -= common_nouns
    lf_set -= common_nouns
    if not ff_set or not lf_set:
        return 1.0  # can't tell, treat as shared
    shared = ff_set & lf_set
    # Jaccard: |intersection| / |union|
    union = ff_set | lf_set
    return len(shared) / len(union) if union else 1.0


def assess_shot_risk(shot):
    """Assess a single shot's FF↔LF risk. Returns a risk dict.

    Risk levels:
        - 'frozen':   FF and LF nearly identical, no spatial delta (expected SSIM > 0.92)
        - 'subtle':   Only expression/gaze/breath change, no body motion (expected SSIM 0.80-0.92)
        - 'radical':  LF appears to be in a different scene OR no shared nouns (expected SSIM < 0.40)
        - 'healthy':  None of the above (expected SSIM 0.60-0.80)
    """
    ff = shot.get("first_frame_prompt") or ""
    lf = shot.get("last_frame_prompt") or ""
    shot_type = shot.get("shot_type", "chain_start")
    break_continuity = shot.get("break_continuity", False)
    prefix = shot.get("filename_prefix", "?")

    # If this is a continuation shot, FF is the prev tail — we can't text-compare
    # because we only have the prev shot's LF. Flag it with reduced confidence.
    is_continuation = shot_type in ("continuation", "bridge")

    risks = []
    suggestions = []

    # 1. Frozen risk: high text similarity + no spatial-delta keywords
    sim = text_similarity(ff, lf) if (ff and lf) else 0.0
    lf_spatial_kws = keyword_count(lf, SPATIAL_DELTA_KEYWORDS)
    lf_expression_kws = keyword_count(lf, EXPRESSION_KEYWORDS)
    lf_scene_change_kws = keyword_count(lf, SCENE_CHANGE_KEYWORDS)

    if ff and lf and sim > 0.85 and lf_spatial_kws == 0:
        risks.append("FROZEN")
        suggestions.append(
            "LF is too similar to FF (text similarity {sim:.0%}) and has no spatial-delta keywords. "
            "Rewrite LF as an edit-instruction with KEEP UNCHANGED + CHANGE sections."
            .format(sim=sim)
        )
    elif ff and lf and sim > 0.70 and lf_spatial_kws == 0:
        # Borderline — flag as warning but not full frozen
        suggestions.append(
            f"LF is {sim:.0%} text-similar to FF with no spatial-delta keywords — borderline frozen risk. "
            "Add explicit CHANGE verbs (stepping, turning, releasing, leaning, looking)."
        )

    # 2. Subtle risk: expression-only change, no body motion
    if lf_expression_kws >= 2 and lf_spatial_kws == 0:
        risks.append("SUBTLE")
        if not is_continuation:
            suggestions.append(
                "LF has expression-only changes (no body motion). Either: (a) add a body delta "
                "(shoulder, head tilt, weight shift), or (b) reduce segment_duration to 2-3s and "
                "accept the held-still with the short-shot heuristic."
            )

    # 3. Radical risk: scene change in LF text OR no shared nouns
    if lf_scene_change_kws > 0:
        if not break_continuity:
            risks.append("RADICAL")
            suggestions.append(
                "LF implies a scene change (\"{kw}\" detected) but break_continuity is false. "
                "Either: (a) set break_continuity: true, (b) rewrite LF as a transition "
                "(character exits frame, camera reveals new location), or (c) add the new "
                "location to break_continuity + bridge shot."
                .format(kw=[k for k in SCENE_CHANGE_KEYWORDS if k in lf.lower()][0])
            )
        # else: break_continuity is true, scene change is intentional — no risk

    if ff and lf:
        ff_tokens = tokenize(ff)
        lf_tokens = tokenize(lf)
        shared = shared_noun_ratio(ff_tokens, lf_tokens)
        if shared < 0.10 and not break_continuity:
            risks.append("RADICAL")
            suggestions.append(
                f"FF and LF share only {shared:.0%} of content nouns (very low). "
                "Rewrite LF to keep shared character + setting nouns, "
                "or set break_continuity: true if a real scene change is intended."
            )

    # 4. Anti-pattern: LF is longer than FF (LF should be a delta, not a full scene)
    if ff and lf and len(lf) > len(ff) * 1.5 and lf_spatial_kws < 3:
        suggestions.append(
            f"LF ({len(lf)} chars) is much longer than FF ({len(ff)} chars) "
            "but has few spatial-delta keywords. The LF may be re-describing the scene "
            "instead of describing a delta. Trim and re-author as an edit-instruction."
        )

    # 5. Anti-pattern: FF-style vocabulary in LF (T2I words like "wide shot", "medium shot")
    t2i_vocab_in_lf = sum(1 for w in ("wide shot", "medium shot", "close-up", "closeup",
                                       "establishing shot", "extreme close-up", "low angle",
                                       "high angle", "overhead shot", "dutch angle")
                          if w in lf.lower())
    if t2i_vocab_in_lf > 0 and lf_spatial_kws < 2:
        suggestions.append(
            f"LF has {t2i_vocab_in_lf} T2I vocabulary word(s) (e.g. 'wide shot', 'medium shot') "
            "but few spatial-delta keywords. This is the T2I-vs-I2I anti-pattern — see "
            "phase-1-prompt-composition.md § Edit-Instruction LF Pattern. "
            "Rewrite LF as 'Edit image 1. KEEP UNCHANGED: ... CHANGE: ...'."
        )

    # Determine final verdict
    if "FROZEN" in risks:
        verdict = "FROZEN"
    elif "RADICAL" in risks:
        verdict = "RADICAL"
    elif "SUBTLE" in risks:
        verdict = "SUBTLE"
    elif suggestions and not risks:
        verdict = "WARNING"
    else:
        verdict = "HEALTHY"

    return {
        "filename_prefix": prefix,
        "shot_type": shot_type,
        "is_continuation": is_continuation,
        "ff_len": len(ff) if ff else 0,
        "lf_len": len(lf) if lf else 0,
        "text_similarity": sim,
        "lf_spatial_delta_kws": lf_spatial_kws,
        "lf_expression_kws": lf_expression_kws,
        "lf_scene_change_kws": lf_scene_change_kws,
        "shared_noun_ratio": shared_noun_ratio(tokenize(ff), tokenize(lf)) if (ff and lf) else None,
        "t2i_vocab_in_lf": t2i_vocab_in_lf,
        "risks": list(set(risks)),
        "suggestions": suggestions,
        "verdict": verdict,
    }


def render_console_report(audits, prompts_path):
    print(f"\n{'═'*80}")
    print(f"  Pre-flight FF↔LF Audit — {os.path.basename(prompts_path)}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*80}\n")

    # Per-shot table
    print(f"{'#':<4}{'Shot':<32}{'Type':<14}{'Verdict':<10}{'Sim':<6}{'Δkws':<5}{'Expr':<5}{'Scn':<4}{'Shrd'}")
    print("─" * 95)
    for i, a in enumerate(audits, 1):
        prefix = a["filename_prefix"][:30]
        st = a["shot_type"][:12]
        verdict = a["verdict"]
        flag = {"FROZEN": "❌", "RADICAL": "⚠️", "SUBTLE": "⚠️",
                "WARNING": "💡", "HEALTHY": "✓"}.get(verdict, "·")
        sim = f"{a['text_similarity']:.2f}" if a['text_similarity'] else "—"
        dkw = str(a['lf_spatial_delta_kws'])
        ekw = str(a['lf_expression_kws'])
        skw = str(a['lf_scene_change_kws'])
        shared = (f"{a['shared_noun_ratio']:.2f}"
                  if a['shared_noun_ratio'] is not None else "—")
        print(f"{i:<4}{prefix:<32}{st:<14}{flag} {verdict:<8}{sim:<6}{dkw:<5}{ekw:<5}{skw:<4}{shared}")

    # Summary
    print(f"\n{'─'*80}")
    counts = Counter(a["verdict"] for a in audits)
    total = len(audits)
    print(f"  Summary: {total} shots audited")
    for verdict in ("FROZEN", "RADICAL", "SUBTLE", "WARNING", "HEALTHY"):
        n = counts.get(verdict, 0)
        if n > 0:
            flag = {"FROZEN": "❌", "RADICAL": "⚠️", "SUBTLE": "⚠️",
                    "WARNING": "💡", "HEALTHY": "✓"}.get(verdict, "·")
            pct = n * 100 // total if total else 0
            print(f"    {flag} {verdict:<8} {n:>3} / {total} ({pct}%)")

    risky = sum(1 for a in audits if a["verdict"] in ("FROZEN", "RADICAL", "SUBTLE"))
    if risky:
        print(f"\n  ⚠️  {risky} of {total} shots are at risk. Re-author their LFs before Phase 2.")
        print(f"     See feedback/ff_lf_audit_preflight.md for per-shot suggestions.")
    else:
        print(f"\n  ✅ No frozen, radical, or subtle risks detected. LFs look healthy.")
    print()


def render_markdown_report(audits, prompts_path):
    lines = []
    lines.append(f"# Pre-flight FF↔LF Audit")
    lines.append("")
    lines.append(f"**Source:** `{prompts_path}`  ")
    lines.append(f"**Run at:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
    lines.append(f"**Total shots:** {len(audits)}")
    lines.append("")
    lines.append("This audit checks every shot's `first_frame_prompt` and `last_frame_prompt` "
                 "for the failure modes the elephant story (2026-06-11) exposed: "
                 "**frozen** (FF≈LF, no motion signal), **radical** (LF in different scene), "
                 "and **subtle** (expression-only change with no body motion).")
    lines.append("")

    counts = Counter(a["verdict"] for a in audits)
    total = len(audits)
    lines.append("## Summary")
    lines.append("")
    lines.append("| Verdict | Count | % |")
    lines.append("|---|---|---|")
    for verdict in ("FROZEN", "RADICAL", "SUBTLE", "WARNING", "HEALTHY"):
        n = counts.get(verdict, 0)
        if n > 0:
            pct = n * 100 // total if total else 0
            lines.append(f"| {verdict} | {n} | {pct}% |")
    lines.append(f"| **Total** | **{total}** | **100%** |")
    lines.append("")

    lines.append("## Per-shot detail")
    lines.append("")
    for a in audits:
        lines.append(f"### `{a['filename_prefix']}` — {a['verdict']}")
        lines.append("")
        lines.append(f"- **shot_type:** `{a['shot_type']}`"
                     + (" (continuation, FF=prev tail — text-only audit has reduced confidence)" if a['is_continuation'] else ""))
        lines.append(f"- **ff_len:** {a['ff_len']} chars, **lf_len:** {a['lf_len']} chars")
        if a['text_similarity']:
            lines.append(f"- **text_similarity (FF↔LF):** {a['text_similarity']:.2f}")
        if a['shared_noun_ratio'] is not None:
            lines.append(f"- **shared_noun_ratio (FF↔LF):** {a['shared_noun_ratio']:.2f}"
                         + (" — low, possible radical risk" if a['shared_noun_ratio'] < 0.10 else ""))
        lines.append(f"- **LF spatial-delta keywords:** {a['lf_spatial_delta_kws']}")
        lines.append(f"- **LF expression-only keywords:** {a['lf_expression_kws']}")
        lines.append(f"- **LF scene-change keywords:** {a['lf_scene_change_kws']}")
        if a['t2i_vocab_in_lf']:
            lines.append(f"- **T2I vocabulary in LF:** {a['t2i_vocab_in_lf']} (anti-pattern)")
        if a['risks']:
            lines.append(f"- **Detected risks:** {', '.join(a['risks'])}")
        if a['suggestions']:
            lines.append("")
            lines.append("**Suggestions:**")
            for s in a['suggestions']:
                lines.append(f"- {s}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("**Heuristic accuracy:** text-only audit. False positives (warning on healthy shots) "
                 "are expected and safe to dismiss. False negatives (radical shot that passes) "
                 "will be caught by the post-render SSIM audit at the end of the pipeline. "
                 "For calibration, see `fflf-production-learnings.md` § LF Edit-Mode Prompting.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Pre-flight FF↔LF text-based risk audit for filmmaking_prompt.json"
    )
    parser.add_argument("prompts_path", help="Path to filmmaking_prompt.json")
    parser.add_argument("--output", "-o", default=None,
                        help="Output markdown path (default: feedback/ff_lf_audit_preflight.md "
                             "relative to the prompts_path directory)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress console output (markdown only)")
    args = parser.parse_args()

    if not os.path.exists(args.prompts_path):
        print(f"❌ File not found: {args.prompts_path}", file=sys.stderr)
        sys.exit(1)

    with open(args.prompts_path) as f:
        prompts = json.load(f)

    shots = prompts.get("shots", [])
    if not shots:
        print(f"❌ No shots found in {args.prompts_path}", file=sys.stderr)
        sys.exit(1)

    audits = [assess_shot_risk(shot) for shot in shots]

    if not args.quiet:
        render_console_report(audits, args.prompts_path)

    # Determine output path
    if args.output:
        out_path = args.output
    else:
        prompts_dir = os.path.dirname(os.path.abspath(args.prompts_path))
        feedback_dir = os.path.join(prompts_dir, "feedback")
        os.makedirs(feedback_dir, exist_ok=True)
        out_path = os.path.join(feedback_dir, "ff_lf_audit_preflight.md")

    md = render_markdown_report(audits, args.prompts_path)
    with open(out_path, "w") as f:
        f.write(md)
    if not args.quiet:
        print(f"  📄 Markdown report: {out_path}")

    # Exit code: 0 = healthy, 1 = at least one risky shot
    risky = any(a["verdict"] in ("FROZEN", "RADICAL", "SUBTLE") for a in audits)
    sys.exit(1 if risky else 0)


if __name__ == "__main__":
    main()
