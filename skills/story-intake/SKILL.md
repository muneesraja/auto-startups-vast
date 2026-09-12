---
name: story-intake
description: CLI for managing story-maker-v5 `stories/` input folders — init stories, create episode folders, import character/location/object images and audio with naming conventions applied automatically, check input quality, and trigger episode preparation. Use when the user wants to add or manage story inputs, drop reference images/audio, or check episode status.
---

# story-intake

Manages the `stories/<name>/` input contract defined by story-maker-v5
(`skills/story-maker-v5/tools/story_input.py`). Files on disk are the source
of truth — this CLI only writes them; it owns no pipeline state.

## Commands

```bash
python3 skills/story-intake/cli.py init olli --title "Olli"
python3 skills/story-intake/cli.py episode olli 2 --title "The Dive"
python3 skills/story-intake/cli.py add-asset olli characters ./ollie.png [--entity char_01|new]
python3 skills/story-intake/cli.py add-asset olli references ./seed.mp4 --episode 2
python3 skills/story-intake/cli.py add-audio olli ./v.mp3 \
    --role voice --speaker S1 [--episode 2] [--scene s1] [--gen g2]
python3 skills/story-intake/cli.py check olli     # input warnings
python3 skills/story-intake/cli.py status olli    # episodes + stages
python3 skills/story-intake/cli.py prepare olli 1 # → prepare_episode.py
python3 skills/story-intake/cli.py list           # all stories
```

Global flags: `--stories-root` (default `stories`), `--outputs-root`
(default `outputs/story-maker-v5`). Stdlib only — any Python 3.10+.

## Layout it manages

```text
stories/<name>/
├── config.json      # series defaults
├── series.md        # story bible (Agent 1 context)
├── episodes/
│   └── episode-N/       # one folder per episode
│       ├── episode-N.md     # script / concept
│       ├── meta.json        # per-episode overrides
│       ├── audio/           # this episode's audio (shadows series audio/)
│       └── references/      # this episode's video refs
├── audio/           # series-wide role-named refs
├── characters/      # char_01.png → char_01 (imported approved)
├── locations/       # loc_01.png → loc_01
├── objects/         # obj_01.png → obj_01
├── style/           # moodboard frames
└── references/      # series-wide video clips
```

## Conventions the CLI applies

- **Assets**: `--entity char_01` or omit for the next free id
  (`char_02`, `loc_01`, `obj_01` — files + `cast[]` both counted).
- **Audio**: `--role voice|dialogue|music|ambience|reference` +
  `--speaker S1` (required for voice) + optional `--scene s1 --gen g2`
  scope → `s1_g2__voice_S1.mp3`-style names per `tools/audio_refs.py`.
  `--episode N` routes into `episodes/episode-N/audio/`.
- **check** reports: empty episodes, cast refs pointing at missing files,
  non-canonical entity ids, audio names matching no role, and flat files
  shadowed by an episode folder.

## Non-CLI path

`python3 skills/story-maker-v5/scripts/init_story.py <name>` scaffolds the
same folder; `prepare_episode.py` consumes it — `cli.py prepare` runs
exactly that.
