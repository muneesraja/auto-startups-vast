# Reddit Scraping Patterns for Qwen Research

Crawling Reddit for practical AI prompting tips. Reddit blocks most browser and HTTP scraping — here's what works.

## What Works

### Reddit Search JSON API (bulk)

Search across subreddits via the JSON API. Works from server IPs with a standard User-Agent header.

```bash
# Search a subreddit (returns up to 100 posts)
curl -s -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  -H "Accept: application/json" \
  "https://www.reddit.com/r/LocalLLaMA/search.json?q=Qwen+image+edit&sort=relevance&restrict_sr=on&limit=25"
```

Parse with Python:
```python
import json, subprocess
result = subprocess.run(['curl', '-s', '-H', 'User-Agent: Mozilla/5.0', '-H', 'Accept: application/json', url],
                       capture_output=True, text=True, timeout=30)
data = json.loads(result.stdout)
posts = data['data']['children']
for p in posts:
    d = p['data']
    print(f"[score={d['score']}] {d['title']}")
    print(f"  Permalink: https://old.reddit.com{d['permalink']}")
```

### Individual Thread JSON API

**This works when ScraplingServer gets 403.** Use `curl` with a browser User-Agent and `Accept: application/json`.

```bash
curl -s -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  -H "Accept: application/json" \
  "https://www.reddit.com/r/comfyui/comments/1nxrptq/how_to_get_the_highest_quality_qwen_edit_2509/.json"
```

Returns a 2-element array:
- `[0]` = post listing (title, selftext, score, etc.)
- `[1]` = comments listing (with nested replies)

```python
data = json.loads(result.stdout)
post = data[0]['data']['children'][0]['data']
comments = data[1]['data']['children']
for c in comments:
    if c['kind'] == 't1':
        print(f"[score={c['data']['score']}] {c['data']['body'][:500]}")
```

### Old.reddit.com via curl

Sometimes `old.reddit.com` works when `www.reddit.com` blocks:
```bash
curl -s -H "User-Agent: Mozilla/5.0" -H "Accept: application/json" \
  "https://old.reddit.com/r/LocalLLaMA/search.json?q=..."
```

## What Doesn't Work

| Method | Result |
|--------|--------|
| `browser_navigate` to reddit.com | Times out |
| ScraplingServer `stealthy_fetch` | Page crashes |
| ScraplingServer `bulk_get` with `impersonate` | 403 "network security" block |
| ScraplingServer `fetch` with browser | Page crashes |
| `www.reddit.com/.json` via ScraplingServer | 403 |
| `old.reddit.com` via ScraplingServer bulk_get | Works for search JSON, 403 for threads |

## Bulk Fetch Pattern (3 subreddits at once)

Use `ScraplingServer_bulk_get` with `old.reddit.com` search JSON URLs for discovery, then `curl` for individual thread content.

```python
# Discovery phase — bulk get search results
urls = [
    "https://old.reddit.com/r/LocalLLaMA/search.json?q=Qwen+image+edit&sort=relevance&restrict_sr=on&limit=25",
    "https://old.reddit.com/r/StableDiffusion/search.json?q=Qwen+image+edit+prompting&sort=relevance&restrict_sr=on&limit=25",
    "https://old.reddit.com/r/ComfyUI/search.json?q=Qwen+image+edit&sort=relevance&restrict_sr=on&limit=25",
]
# Returns deeply nested JSON — parse carefully
# Each response has data.children[].data with title, score, permalink, selftext
```

**Parsing caveat**: The bulk_get response wraps each subreddit JSON as a triple-escaped string inside a content array. Parse the outer JSON first, then inner strings.

## Relevant Subreddits for AI Image Generation

| Subreddit | Focus | Key Threads Found |
|-----------|-------|-------------------|
| r/LocalLLaMA | Model releases, comparisons, benchmarks | Qwen-Image-Edit release (1.1k), 2511 upgrade (231), 2512 (728) |
| r/StableDiffusion | Workflows, LoRAs, comparison posts | Quality workflow (283), face dataset (984), Next Scene LoRA (725), upscale LoRA (879) |
| r/ComfyUI | ComfyUI workflows, node debugging, custom workflows | Mask editing (497), dataset workflow (493), model comparison (5+ comments), 2511 model files (272) |
| r/FOSSAI | Open-source AI | Not crawled yet — low volume but worth checking |

## Search Queries That Work

For Qwen Image Edit research:
```
qwen image edit
qwen image edit prompting
qwen 2511
qwen 2509
qwen image edit face
qwen image edit expression
qwen image edit consistency
qwen image edit workflow
```

Sort by `relevance` for quality posts, `new` for recent findings.

## Session Log

- **2026-05-19**: Scraped 8 threads (600+ comments) across r/StableDiffusion, r/LocalLLaMA, r/ComfyUI. Key findings: offset bug root cause, Lightning LoRA quality tradeoff, consistence/AnyPose/Next Scene LoRAs, multi-ref strategies, zeroed negative conditioning trick, face dataset technique, 2509-vs-2511 comparison, Chinese prompting neutral. All findings integrated into `qwen-image-edit-prompting-guide.md`.