---
name: social-publisher
version: 1.2.0
description: "Publish AI-generated videos from a Google Sheet queue to YouTube and Instagram. Instagram Login API (graph.instagram.com), token exchange, Drive via gws. Use when publishing final_film.mp4 to social channels from Hermes VPS agents."
triggers:
  - social-publisher
  - publish-video
  - youtube-upload
  - instagram-reels
---

# Social Publisher

Publish `final_film.mp4` videos from a Google Sheet queue to **YouTube** and **Instagram Reels**.

**Agent guide (prompting examples):** [README.md](README.md)  
**Sheet quick guide:** `README` tab in the Google Sheet

## Instagram API

Uses **Instagram Login API** (`graph.instagram.com`), not Facebook Login.

| Env var | Purpose |
|---------|---------|
| `IG_APP_SECRET` | Exchange/refresh tokens |
| `IG_SHORT_LIVED_TOKEN` | From Meta dashboard Generate token (~1h) |
| `IG_ACCESS_TOKEN` | Long-lived token (~60d) for publish |
| `IG_USER_ID` | Instagram professional account ID |
| `SOCIAL_PUBLISHER_PUBLIC_BASE_URL` | **HTTPS** — Meta fetches `video_url` from VPS |

Token scripts:

```bash
python scripts/exchange_instagram_token.py   # short → long-lived
python scripts/refresh_instagram_token.py    # extend before expiry
python scripts/verify_instagram_token.py     # check token + user_id
```

If `IG_ACCESS_TOKEN` is empty but `IG_SHORT_LIVED_TOKEN` + `IG_APP_SECRET` are set, publish will auto-exchange for the session (prints reminder to persist token).

## YouTube

- `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` with `youtube.upload` scope
- Sets `containsSyntheticMedia=true` (AI disclosure)
- Optional thumbnail via `thumbnail_drive_file_id` in Queue sheet

## Usage

See [README.md](README.md) for prompting examples.

```bash
python main.py --row <id> --platforms youtube --dry-run
python main.py --row <id> --platforms youtube
python main.py --row <id> --platforms instagram          # needs HTTPS PUBLIC_BASE_URL
python main.py --row <id> --platforms youtube,instagram
python scripts/exchange_instagram_token.py
python scripts/verify_instagram_token.py --use-short-lived
```

## Sheet schema

Queue columns: `id | brand | drive_file_id | thumbnail_drive_file_id | title | description | hashtags | platforms | visibility | status | yt_url | ig_url | errors`

Accounts maps `brand` → `credential_ref` → env keys (`YT_MAIN`, `IG_MAIN`).

## Troubleshooting

| Issue | Fix |
|-------|-----|
| IG token invalid | Regenerate in Meta dashboard; run `exchange_instagram_token.py` |
| IG container ERROR | Ensure `PUBLIC_BASE_URL` is HTTPS and video URL is reachable |
| Token exchange fails | Check `IG_APP_SECRET` is the Instagram app secret (not webhook verify token) |
| YT invalid_scope | Re-run `setup_youtube_oauth.py` |
