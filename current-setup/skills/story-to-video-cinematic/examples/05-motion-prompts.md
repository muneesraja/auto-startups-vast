# FFLF Motion Prompts — Examples & Best Practices

In Wave 3 and subsequent video waves, LTX 2.3 FFLF takes the starting First Frame (FF) and ending Last Frame (LF) and generates a video segment interpolating between them. The motion prompt guides how this interpolation occurs.

## Motion Prompt Formula
`[Camera movement/speed] + [Character motion & action details] + [Environmental/atmospheric motion]`

## Best Examples

### Example 1: Panda Forest Walk (Shot 1)
```
Camera gently pushes forward along the path, the panda slows its walk and turns its head curiously to the right. Smooth slow-motion transition.
```

### Example 2: Reaching for Butterfly (Shot 2)
```
The panda slowly raises its right paw toward the butterfly, camera holds steady with a subtle slow zoom in on the panda.
```

### Example 3: Meeting at Waterfall (Shot 3)
```
Camera slowly zooms in on the two characters, the monkey turns and extends its hand, the panda reacts with surprised delight. Waterfall cascades in background.
```

## Good vs. Bad Motion Prompts

| Aspect | Good Motion Prompt | Bad Motion Prompt |
|--------|---------------------|-------------------|
| **Length** | `Camera slowly tracks left, panda steps forward.` (Brief, 10-25 words) | `A very detailed and cinematic shot of a cute panda with fluffy fur walking slowly on a mossy green path while a butterfly flies around...` (Too wordy, >50 words) |
| **Focus** | Focuses on the *transition* and *movement* from FF to LF. | Tries to describe character details and settings again. |
| **Consistency** | Anchored to the visual changes between FF and LF. | Describes movements that contradict the LF (e.g. asking character to jump when LF shows them sitting). |

## Anti-Jump-Cut Phrases
To prevent sudden jumps or visual popping between frames, include smooth transition words:
* `"Camera gently pushes forward..."`
* `"Subtle slow-motion transition..."`
* `"Slowly raises..."` / `"Gently turns..."`
* `"Camera holds steady..."`
* `"Smooth continuous motion..."`

## Key LTX FFLF Rules
1. **Keep it under 60 tokens**: Long prompts cause LTX to lose focus on the reference frames.
2. **Do not introduce off-screen elements**: Avoid prompts like `"a bird flies in from off-screen"` unless that bird is already in the LF.
3. **Describe camera and subject together**: Make sure camera movements match the framing changes between FF and LF.
