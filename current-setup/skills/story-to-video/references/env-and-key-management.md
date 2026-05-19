# .env & API Key Management

## Pattern: Skill-Local `.env` File

Each skill that needs API keys should have a `.env` file next to its `SKILL.md` with a `.env.example` committed to git.

### File Structure

```
skills/story-to-video/
├── .env            # gitignored — contains actual API keys
├── .env.example    # committed — template showing key names
├── SKILL.md
├── scripts/
└── references/
```

### `.env.example` Template

```
# Gemini API key for character reference sheet generation (gemini-2.5-flash-image)
GEMINI_API_KEY=your_gemini_api_key_here
```

### `.env` (gitignored)

```
GEMINI_API_KEY=<actual paid tier key>
```

### Key Loading Priority

1. **`.env` file** — next to skill directory (stdlib-only parser, no `python-dotenv`)
2. **Environment variable** — `GEMINI_API_KEY` from shell
3. **Token JSON file** — `--token` flag (legacy, backward compat)

### Why No `python-dotenv`?

The `.env` parser is ~15 lines of stdlib code (`Path` + string split). Adding a dependency just to parse KEY=value lines is overkill. The parser in `generate_story_assets.py` (`load_api_key()`) handles:
- Comments (lines starting with `#`)
- Blank lines
- Inline values after `=`
- Stripping whitespace

### Why No Virtual Environment?

The vast-ai skill tried venv but reverted (commit `bbc53f6`) due to "local environment incompatibilities". System-wide `pip install` is simpler and reliable for scripts that use stdlib + 1-2 packages. The `.env` file reading works without venv because it's pure stdlib file I/O.

### Subprocess Key Loading

**Subprocess doesn't load `.bashrc`** — so `export GEMINI_API_KEY=...` in `.bashrc` is invisible to scripts run from `terminal()`. The `.env` file approach fixes this completely because the script reads the file directly, not the environment.

If you need the env var explicitly (e.g., for a script that only reads `os.environ`):
```bash
export GEMINI_API_KEY=$(grep GEMINI_API_KEY ~/.bashrc | head -1 | sed 's/.*="\([^"]*\)".*/\1/')
```