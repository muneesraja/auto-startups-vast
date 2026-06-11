# Gemini Image Generation Quota Notes

## Model: `gemini-2.5-flash-preview-image`

Separate quota from `gemini-2.5-flash` (text/vision). Image generation is much more restricted.

### Free Tier Limits (as of 2025)

| Quota | Limit |
|---|---|
| Requests per day per project | Very low (can hit 0) |
| Requests per minute per project | Very low |
| Input tokens per minute | Very low |

### Key Behaviors

- Quota exhaustion returns `429 RESOURCE_EXHAUSTED` with `limit: 0` — this means **daily** quota, not rate-limiting
- Retry-after is typically 25-30s but retrying won't help if daily quota is truly exhausted
- Text/vision models (`gemini-2.5-flash`) may still work fine when image gen quota is exhausted
- Daily reset: midnight Pacific Time

### Workarounds

1. **Stagger generation** — generate 1-2 character sheets per day across multiple sessions
2. **Paid plan** — enables higher quotas
3. **Use ComfyUI text-to-image** as fallback for reference sheet generation (no API quota needed)
4. **Manual reference images** — find/upload existing character reference sheets

### Error Pattern

```
429 RESOURCE_EXHAUSTED
  quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier
  model: gemini-2.5-flash-preview-image
  limit: 0
```

If `limit: 0` → daily quota exhausted, not rate-limited. No point retrying.