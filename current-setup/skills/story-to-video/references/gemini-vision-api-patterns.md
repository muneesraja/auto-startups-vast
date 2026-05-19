# Gemini 2.5 Flash Vision API — Direct Google REST API Pattern

## Why Gemini 2.5 Flash

- **Free tier** with generous quota (not daily-limited like `gemini-3.1-pro`)
- **`responseMimeType: "application/json"`** forces structured JSON output — no regex wrangling
- **Vision-capable** — accepts `inline_data` with base64 images
- `gemini-3.1-pro-preview` gets rate-limited quickly (429 errors)
- `qwen3-coder-next:cloud` does NOT support image input (400 error)
- MiniMax MCP vision: auth broken, subscription being dropped

## API Endpoint

```
POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}
```

Model: `gemini-2.5-flash`

## Python Pattern (via urllib — works for Gemini, NOT for Cloudflare-protected ComfyUI)

```python
import base64, json, urllib.request, urllib.error

def call_gemini_vision(prompt_text, image_path, api_key, model="gemini-2.5-flash"):
    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/png")

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "contents": [{"parts": [
            {"text": prompt_text},
            {"inline_data": {"mime_type": mime_type, "data": img_b64}},
        ]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2,
        }
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    req_data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=req_data,
                                 headers={"Content-Type": "application/json"})

    # Retry on 429 rate limits
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode())
            for candidate in data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "text" in part:
                        return part["text"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(5 * (attempt + 1))
                req = urllib.request.Request(url, data=req_data,
                                             headers={"Content-Type": "application/json"})
                continue
            raise
```

## API Key

Set in `~/.bashrc` as `GEMINI_API_KEY`. **NOT auto-exported** in subprocess calls — must either:
- `source ~/.bashrc` before running, OR
- `export GEMINI_API_KEY=$(grep 'export GEMINI_API_KEY=' ~/.bashrc | head -1 | sed 's/.*GEMINI_API_KEY="//;s/".*//')`, OR
- Pass `--api-key` flag to scripts

## Gemini CLI Pitfalls

The `gemini` CLI (v0.35.3) has issues:
- Broken `ripGrep.js` dependency causing crashes
- Requires `--yolo` flag for non-interactive use
- `-p` flag and positional query can't be combined
- Rate limits hit faster than direct API

**Recommendation:** Use direct REST API via `urllib` instead of the CLI. The CLI is unreliable for automation.

## Response Parsing

With `responseMimeType: "application/json"`, the model returns valid JSON directly. Fallback parsing for markdown-wrapped responses:

```python
try:
    result = json.loads(raw_response)
except json.JSONDecodeError:
    json_match = re.search(r'```json\s*(.*?)\s*```', raw_response, re.DOTALL)
    if json_match:
        result = json.loads(json_match.group(1))
```

## Evaluation Prompt Pattern

For structured image evaluation, use chain-of-thought:

```
STEP 1 - DESCRIBE WHAT YOU SEE:
Before scoring, describe exactly what you see in the image.

STEP 2 - SCORE BY CATEGORY:
Rate each category 0-10: [categories with weights]

Critical issues that automatically fail: [list]

STEP 3 - IDENTIFY ISSUES:
List specific problems.

STEP 4 - DECIDE:
passed: true if score >= threshold AND no critical issues
If false, provide refined_prompt

Respond in this exact JSON format only:
{schema}
```

The `responseMimeType: "application/json"` + low temperature (0.2) ensures consistent, parseable output.