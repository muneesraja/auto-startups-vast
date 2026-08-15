# Sound / Lyric — Audio Mapping

**Input:** `ledger.clips[]` + source audio (lyrics/transcript with
timestamps).
**Output:** `ledger.audio` per clip (`clips[k].audio` with `lines[]`).

## Job

Map lyric/dialogue lines from the source audio to each clip's audio
window. Snap cut timestamps to beat onsets. Assign per-shot sound cues.
The source audio is fixed — you do not choose what plays when; you
compute which lines fall in which clip's window and align the cuts.

## Rules

- **`source_track` windowing.** Each clip's audio window is fixed by
  `audio.start_s` and `audio.duration_s` in the ledger. Clip k's window
  is `[start_s, start_s + duration_s)`. A lyric line at timestamp `t`
  in the source track belongs to clip k iff
  `start_s <= t < start_s + duration_s`. This is deterministic — do not
  reorder or reassign lines.
- **Snap cuts to beat onsets.** For each clip, identify the beat onsets
  within its audio window. Adjust shot cut timestamps (`shots[].t`) to
  land on the nearest beat onset. If a shot's natural cut is >0.3s from
  any beat, flag it — the cutter may need to adjust the shot duration.
- **HoLLMwood Actor (dialogue).** For spoken lines, use the Actor
  persona: keep dialogue short, in-character, and delivery-annotated
  (pitch, timbre, rate). The line text is verbatim from the source — do
  not rewrite.
- **Spoken wps ≤ 3.5.** Words per second for any spoken line must not
  exceed 3.5. If a line is too dense for its window, flag it for the
  cutter to extend the shot or split the line.
- **Every shot has one sound cue.** Each `shots[].sound` gets a concrete
  cue: a SFX description, a vocal hit, or a beat marker. This was
  sketched by the cutter; here you make it specific and sync it to the
  audio window.
- **Speaker assignment.** Each `lines[]` entry gets `speaker` (cast id
  from `bible.json` or narrator label), `lang`, `text` (verbatim), and
  `t` (timestamp within the clip, clip-relative).

## Output format

Per clip, populate `clips[k].audio`:

```json
{
  "start_s": 0.0,
  "duration_s": 14.17,
  "lines": [
    {"t": 10.5, "speaker": "char_02", "lang": "en", "text": "Mama!"},
    {"t": 12.0, "speaker": "narrator", "lang": "en", "text": "and so it began"}
  ]
}
```

Also update each `shots[].sound` with the concrete cue and set `on_beat`
to true/false based on whether the cut snapped to a beat onset.

## What invalidates the ledger

Swapping the source audio file after clips are rendered invalidates
assembly and any unfinished clip (the beat onsets shift, so cut
timestamps no longer sync). Finished clip checkpoints stand, but the
final assembled video will have audio misalignment. Re-mapping lines
after prompts are written can desync dialogue from lip-sync cues in the
prompt text — the prompt writer's `<d>` blocks must match the audio
mapping exactly.
