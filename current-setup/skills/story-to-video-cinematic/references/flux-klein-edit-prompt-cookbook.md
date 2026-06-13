# Flux Klein 9B Edit Prompt Cookbook

A prompt engineering guide specifically for the Flux Klein edit pass in this cinematic pipeline.

## Edit Prompt Formula

```
[PRIMARY ACTION] + [SUBJECT IDENTIFICATION] + [REFERENCE DIRECTIVE] + [PRESERVATION CONSTRAINT]
```

## Prompt Patterns

### Pattern 1: Character Replacement (most common)
"Replace the [generic character description] in the scene with the character from reference 1, matching their exact appearance, outfit, and features while keeping the background, lighting, pose, and composition identical"

### Pattern 2: Character Identity Lock
"Make the [character position] character look exactly like reference 1 — match their face, hair, clothing, and proportions while preserving the scene's lighting, background, and overall composition"

### Pattern 3: Style-Consistent Character Edit
"Edit the [character] to match reference 1's appearance in the style of [3D Pixar / anime / cinematic realism]. Preserve all environmental elements and the character's pose unchanged"

---

## Anti-Patterns (Do NOT use)

❌ **"A beautiful scene with a girl standing in a fantasy village"**
- *Why:* This is a GENERATION prompt, not an EDIT prompt. Klein will ignore the scene image and hallucinate a new one.

❌ **"Make the character look better"**
- *Why:* Vague. Klein needs specific instructions about what to change.

❌ **"Generate a new image of the character from reference 1 in a village"**
- *Why:* Klein is an editor, not a generator. It needs the scene image as context.

❌ **Redescribing the entire scene**
- *Why:* Klein already "sees" the scene image. Redescribing it causes drift/hallucination in background elements.

---

## Reference Preprocessing Rules

### For SCENE IMAGE (Image 1 / node 76):
- ✅ Full scene from Ideogram with characters in position
- ✅ Keep full background, lighting, environment intact
- ✅ Resolution should match output target (1344×768 for 16:9)

### For CHARACTER REFERENCE (Image 2 / node 121):
- ✅ Clean character sheet on white/neutral background
- ✅ Background removed or minimal to prevent background bleed
- ✅ Upright faces — Klein struggles with rotated inputs
- ✅ Include face close-up for identity lock (or multi-view sheet)
- ❌ Do NOT use scene images as character references
- ❌ Do NOT use heavily stylized backgrounds in character refs
