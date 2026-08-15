# Micro-Shot Grammar Reference

Fast-paced micro-shot grammar for H3 Chain Director. Derived from the `immesia.mp4` deconstruction (15 shots in 15 seconds) and the H3 Base multi-shot timeline. Load this when authoring per-clip shot lists.

---

## Core Rules

| # | Rule | Detail |
|---|---|---|
| 1 | Shot count | 6–9 micro-shots per clip (≈14.17s delivered). |
| 2 | Duration | 1.0–2.5s per shot. |
| 3 | Hinge shot | First shot of every clip after clip 1: 1.5–3.0s, continuation of the previous clip — never a hard cut. |
| 4 | Action → reaction | Every action beat is followed by a ≤1.5s reaction / face beat. |
| 5 | Framing rotation | No two adjacent shots share framing + angle (validator-enforced). |
| 6 | Sound per shot | Every shot carries exactly one sound cue (SFX, vocal hit, or beat). |
| 7 | One action | Exactly one dominant action per shot (hard H3 constraint). |
| 8 | Beat sync | `source_track` cut timestamps snap to beat onsets of the song window for that clip. |

---

## Framing Vocabulary

| Token | Meaning |
|---|---|
| `ECU` | Extreme close-up (eyes, object detail) |
| `CU` | Close-up (face fills frame) |
| `MCU` | Medium close-up (head + shoulders) |
| `medium` | Medium shot (waist up) |
| `wide` | Wide shot (full body + environment) |
| `EWS` | Extreme / epic wide (landscape scale) |
| `OTS` | Over-the-shoulder |
| `POV` | Point of view |

## Angle Vocabulary

| Token | Meaning |
|---|---|
| `eye-level` | Neutral, straight on |
| `high` | Looking down at subject |
| `low` | Looking up at subject |
| `dutch` | Tilted / canted frame |
| `bird's-eye` | Directly overhead |
| `worm's-eye` | Ground level looking up |

---

## The Hinge Rule

The last micro-shot of clip N and the first micro-shot of clip N+1 are the **same shot split across the boundary**.

- It is a held or simple-motion beat — a continuous gesture, glance, or freeze that bridges the cut.
- The clip boundary falls *inside* this shot; cut immediately after the hinge beat resolves.
- `hinge_out` (clip N) and `hinge_in` (clip N+1) reference the same beat in the ledger.
- The hinge shot is never a hard cut — it is a continuation.

---

## Worked Example — 7-Micro-Shot Clip (3×2 sheet)

Derived from the `immesia` analysis, mapped to a 3×2 six-panel storyboard sheet + 7 shots (shot 3 spans panels 3–4).

| Shot | Time (s) | Framing | Angle | Action | Sound | Panel |
|---|---|---|---|---|---|---|
| 1 | 0.0–1.5 | ECU | eye-level | Baby's wide eyes peering at beach | Ocean ambience | 1 |
| 2 | 1.5–3.0 | medium | low | Tiny feet padding through sand past crab | Padding footsteps | 2 |
| 3 | 3.0–5.0 | wide | high | Crab scuttles; baby reaches toward water | Crab click SFX | 3–4 |
| 4 | 5.0–6.5 | CU | eye-level | Baby's amazed face, mouth open | Gasps "Oh! Wow!" | 5 |
| 5 | 6.5–8.5 | OTS | eye-level | Giant wave cresting overhead | Wave roar swell | 6 |
| 6 | 8.5–10.5 | ECU | low | Baby's hand touches wall of clear water | Soft splash chime | — |
| 7 | 10.5–14.17 | wide | eye-level | Sunset; baby waves goodbye to wave | "Bye bye!" + ocean wash | — |

Panel mapping: shots 1–5 fill the 6-panel sheet (shot 3 takes two panels); shots 6–7 are video-only tail beats with no dedicated panel.

---

## Fallback Profile

If H3 cannot honour 6–9 cuts in 14s (motion coherence drops, shot count rejected), drop to the prompter's own budget floor:

| Profile | Shots | Duration range |
|---|---|---|
| Full | 6–9 | 1.0–2.5s |
| Fallback | 4–5 | 2.0–3.5s |

The H3 Base prompter's shot budget table specifies 3–5 shots for 11–15s clips. The fallback profile stays inside that envelope while preserving the action → reaction loop and framing rotation. Never go below 4 shots — below that the pacing collapses into the long-take anti-pattern diagnosed in the `bamboo-the-dino` comparison.
