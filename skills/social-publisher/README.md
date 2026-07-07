# Social Publisher — Agent Guide

Use this skill to publish AI-generated videos from your **Google Sheet queue** to **YouTube** and **Instagram**. You talk to the agent in plain language — it reads the sheet, downloads from Drive, uploads, and writes results back.

**Sheet:** [Social Publisher Queue](https://docs.google.com/spreadsheets/d/1lCTrDp0m-B8N0EcFMzeK5xy7E1GO7eLRE5SSfnJJvf4/edit) — see the **README** tab for column colors and layout.

---

## How to invoke the skill

Mention any of these in your prompt so the agent loads `social-publisher`:

- `@social-publisher`
- "publish to YouTube"
- "upload from the publish queue"
- "social publisher skill"

On **Hermes VPS**, the agent runs from the repo and uses `skills/social-publisher/`. Credentials live in `~/.hermes/.env` or project `.env`.

---

## Prompting examples

### Publish one video (most common)

> Use the social-publisher skill to upload queue row **episode-03** to YouTube.

> Publish row **test-001** from the Social Publisher sheet to YouTube only.

> Upload the pending video for brand **CHELLA_PATTANI**, row id **new-mystery-02**, to YouTube as unlisted.

### Dry-run first (recommended for new rows)

> Dry-run social-publisher for row **episode-03** on YouTube — don't upload yet, just validate the sheet row and Drive access.

> Check if row **episode-03** is ready to publish (social-publisher dry-run).

### Publish everything pending

> Publish all pending rows in the Social Publisher queue to YouTube.

> Run social-publisher for every row with status pending, YouTube only.

### After story-maker finishes

> Story output is at `outputs/story-maker/baby-star/final_film.mp4` — add a new queue row for brand **CHELLA_PATTANI** and publish to YouTube as unlisted. Title: "Baby Star — Episode 1". Drive folder: [link or file id].

> The video `final_film.mp4` is in Drive folder CHELLA_PATTANI/New_mystery. Create a publish queue row and upload to YouTube.

### Queue setup (agent fills the sheet)

> Add a new row to the Social Publisher Queue sheet:
> - id: `episode-04`
> - brand: `CHELLA_PATTANI`
> - drive_file_id: `15O-l6ddlc1g3IEd17kwLanJeY6NI8Xa5`
> - title: `New Mystery`
> - description: `A cinematic AI short.`
> - hashtags: `#shorts #mystery`
> - platforms: `youtube`
> - visibility: `unlisted`
> - status: `pending`
> Then publish it.

> Queue this video for YouTube — here's the Drive file id, title, and description: [paste details]. Don't publish yet.

### Thumbnail

> Publish row **episode-03** to YouTube. Use thumbnail Drive id **abc123XYZ** from the sheet.

> Upload row **episode-03** without a custom thumbnail.

### Check status / fix failures

> Check the Social Publisher sheet — what happened with row **episode-02**? Read the errors column.

> Row **episode-02** failed. Recover stale status if needed and retry YouTube upload for that row only.

> Show me all published YouTube URLs from the queue sheet.

### Instagram

> Publish row **episode-03** to Instagram only.

> Exchange my Instagram token and publish row **episode-03** to Instagram.

> Publish row **episode-03** to YouTube and Instagram.

> Verify my Instagram token matches IG_USER_ID before publishing.

**Instagram token flow (one-time setup, agent can run scripts):**

1. Meta dashboard → Generate token → `IG_SHORT_LIVED_TOKEN` in `.env`
2. Meta dashboard → Instagram app secret → `IG_APP_SECRET` in `.env`
3. Ask agent: *"Run exchange_instagram_token.py and update IG_ACCESS_TOKEN"*
4. VPS needs HTTPS `SOCIAL_PUBLISHER_PUBLIC_BASE_URL` for video serving

---

## What to put in your prompt

The agent can read the sheet itself, but including these speeds things up:

| You say | Why it helps |
|---------|----------------|
| **Row id** (`episode-03`, `test-001`) | Targets the exact queue row |
| **Brand** (`CHELLA_PATTANI`) | Picks the right account from Accounts tab |
| **Platform** (`youtube`, `instagram`, or both) | Which networks to publish to |
| **Visibility** (`unlisted` for tests) | Overrides or confirms sheet value |
| **Drive file id** | If the row isn't in the sheet yet |
| **Dry-run** | Validates without uploading |

You do **not** need to mention CLI flags, scripts, or file paths — the agent knows how to run the skill.

---

## What the agent does (behind the scenes)

1. Reads your row from the **Queue** tab (blue columns = your inputs)
2. Downloads `final_film.mp4` (+ optional thumbnail) from Google Drive via `gws`
3. **YouTube:** uploads with AI disclosure + optional custom thumbnail
4. **Instagram:** serves video at HTTPS URL → publishes Reel via `graph.instagram.com`
5. Writes **yt_url** / **ig_url**, **status**, and any **errors** back to the sheet (green columns)

---

## Sheet quick reference

| Tab | Purpose |
|-----|---------|
| **README** | Color legend + column notes (in the sheet) |
| **Queue** | One row per video — fill blue cells, agent fills green |
| **Accounts** | Brand → platform → credential mapping (admin setup) |

**You fill (blue):** `id`, `brand`, `drive_file_id`, `thumbnail_drive_file_id` (optional), `title`, `description`, `hashtags`, `platforms`, `visibility`

**Agent fills (green):** `status`, `yt_url`, `ig_url`, `errors`

Set `status` to `pending` when ready. Use `platforms = youtube`, `instagram`, or `youtube,instagram`.

---

## Prerequisites (one-time, not per prompt)

**YouTube:**
- `SOCIAL_PUBLISHER_SHEET_ID`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`
- `gws` authenticated for Sheets + Drive

**Instagram (Instagram Login API):**
- `IG_APP_SECRET`, `IG_USER_ID`
- `IG_SHORT_LIVED_TOKEN` → exchange → `IG_ACCESS_TOKEN` (agent runs `scripts/exchange_instagram_token.py`)
- `SOCIAL_PUBLISHER_PUBLIC_BASE_URL` must be **HTTPS** on VPS

If YouTube fails with `invalid_scope`:

> Re-run YouTube OAuth setup for social-publisher and update YT_REFRESH_TOKEN in .env.

If Instagram token exchange fails:

> Check IG_APP_SECRET is the Instagram app secret from Meta dashboard (not the webhook verify token).

---

## Tips

- **Test with unlisted** — say "publish as unlisted" or set `visibility` to `unlisted` in the sheet.
- **One row at a time** — clearer than batch until you're confident.
- **Dry-run new rows** — ask for a dry-run before the first real upload.
- **Drive ids as plain text** — not hyperlink formulas in the sheet.
