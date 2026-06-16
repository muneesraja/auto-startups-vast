# Director Decisions — Examples & Reasoning

The Director Phase is where the agent reads the story and decides:
1. How to decompose the narrative into scenes and shots
2. Which shots require continuity (`##continue`) vs cuts (`##cut`)
3. What camera angles and framing to use per shot
4. Maximum continuous chain length (default: 3)

## Example: Panda Forest Story

### Input Story
> "Pippin the panda walks through a bamboo forest. He spots a glowing butterfly
> and reaches for it. Suddenly, a waterfall appears through the bamboo — and 
> there stands Miko the monkey, grinning."

### Director Reasoning

**Scene 1: Forest Discovery** (3 shots)
- **Shot 1 → Shot 2**: The panda is continuous in frame. Same environment.
  Camera pushes forward. **`##continue`** ✅
- **Shot 2 → Shot 3**: COMPLETELY different framing. New environment reveal
  (waterfall). New character introduced (Miko). **`##cut`** ✅

**Why not 3 continuous shots?**
Shot 3 introduces a new character (Miko) and a new environment (waterfall).
Even if the narrative is continuous, the visual discontinuity is too large
for FFLF to interpolate smoothly. The author warns: "ending image must 
follow a logical path from starting imagery."

### Decision Output
| Shot | Continuity | Reasoning |
|------|-----------|-----------|
| S1 Shot 1 | `start` | First shot of the story |
| S1 Shot 2 | `##continue` | Same character, same environment, subtle camera movement |
| S1 Shot 3 | `##cut` | New character + new environment = too large a visual delta |

### Anti-Pattern: Forcing Continuity on Scene Changes
❌ **DO NOT** set `##continue` when:
- A new character is introduced mid-chain
- The environment changes dramatically (indoor → outdoor)
- The camera angle changes radically (wide shot → extreme close-up)
- The time of day changes (day → night)

### Anti-Pattern: Cutting Too Aggressively
❌ **DO NOT** set `##cut` for:
- Minor camera pushes (wide → medium on same subject)
- Expression changes (happy → surprised) in same setting
- Object interactions (character picks up item) in same framing

### Maximum Chain Length: 3 Shots
After 3 continuous shots, the system forces a `##cut` to prevent:
- Character identity drift from accumulated Klein edits
- LTX artifact accumulation in extracted tail frames
- Motion coherence degradation from repeated frame extraction
