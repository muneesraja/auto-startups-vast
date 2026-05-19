# Facial Expression Vocabulary for Story-to-Video

This reference defines the approved vocabulary for `facial_expression` fields in shot manifests. **Use these descriptors in prompts** — Qwen Image Edit responds significantly better to specific visual descriptions than to emotion labels alone.

## Usage Rules

1. **Always use visual descriptors, not abstract labels.** "Downcast eyes, slight frown" > "sad"
2. **Combine 2-3 descriptors per character per shot.** One feature isn't enough; three gives strong guidance without over-constraining.
3. **Include the mouth, eyes, and brow/forehead** — these are the three key facial regions for expressions.
4. **Match expression to shot context.** If a character is sad in a joyful scene, describe both the scene mood and the character's specific face.
5. **Use intensity modifiers.** "Slight frown" ≠ "deep scowl". Be precise about how strong the expression is.

## Expression Categories

### 😊 Joy / Happiness

| Emotion | Visual Descriptors | Prompt Text |
|---|---|---|
| Beaming | Wide smile, crinkled eyes, raised cheeks | `beaming smile, eyes crinkled at corners, cheeks raised high` |
| Content/Gentle | Soft closed-mouth smile, relaxed eyes | `gentle closed-mouth smile, soft eyes, relaxed brow` |
| Excited | Wide grin, bright eyes, raised brows | `wide excited grin, bright wide eyes, raised eyebrows` |
| Amused | Slight smirk, twinkling eyes | `knowing smirk, one brow slightly raised, eyes twinkling` |
| Relieved | Deep exhale smile, closed eyes | `relieved smile, eyes gently closed, tension released from brow` |

### 😢 Sadness / Grief

| Emotion | Visual Descriptors | Prompt Text |
|---|---|---|
| Upset/Crying | Tears streaming, trembling lower lip, scrunched eyes | `tears on cheeks, lower lip trembling, eyes scrunched shut, nose red` |
| Downcast | Drooping eyes, slight frown, averted gaze | `downcast eyes looking at ground, slight downturned mouth, heavy brow` |
| Heartbroken | Anguish face, open mouth, wet eyes | `face contorted in anguish, mouth slightly open, eyes wet and red, brows drawn together` |
| Wistful | Distant gaze, faint melancholy smile | `distant gaze past the viewer, faint sad smile, eyes slightly unfocused` |
| Defeated | Slack jaw, hollow eyes, slumped | `hollow empty eyes, slack jaw, face drained of energy, brow slack` |

### 😠 Anger / Frustration

| Emotion | Visual Descriptors | Prompt Text |
|---|---|---|
| Furious | Bared teeth, flared nostrils, intense glare | `furious glare, teeth bared, nostrils flared, brows pulled down hard` |
| Scowling | Drawn-together brows, tight mouth, narrowed eyes | `deep scowl, brows drawn together, mouth tight thin line, eyes narrowed` |
| Frustrated | Clenched jaw, tight lips, wrinkled brow | `clenched jaw visible at temples, lips pressed tight, furrowed brow` |
| Annoyed | Slight eye-roll, one raised brow, thin smile | `one eyebrow raised, slight sneer, eyes narrowed in irritation` |
| Seething | Cold stare, rigid jaw, controlled fury | `cold intense stare, jaw muscles clenched, thin pressed lips, still and controlled` |

### 😨 Fear / Anxiety

| Emotion | Visual Descriptors | Prompt Text |
|---|---|---|
| Terrified | Wide eyes, open mouth, pale face | `eyes wide with terror, mouth open in gasp, face pale, brows raised high` |
| Nervous | Darting eyes, forced smile, sweat | `darting eyes, forced tight smile, small sweat drop on forehead, fidgeting` |
| Anxious | Worried brow, biting lip, wide eyes | `worried furrowed brow, lower lip caught between teeth, eyes wide and watchful` |
| Startled | Wide eyes, raised brows, mouth open | `suddenly wide eyes, brows shot up, mouth rounded in surprise, body jolted` |
| Panicked | Frantic eyes, gasping, wild look | `frantic wild eyes, mouth gasping, face flushed, brows high and tense` |

### 😮 Surprise / Shock

| Emotion | Visual Descriptors | Prompt Text |
|---|---|---|
| Amazed | Wide-open eyes, dropped jaw, eyebrows up | `eyes wide with wonder, jaw dropped, brows raised high, face lit up` |
| Shocked | Frozen expression, wide eyes, slack mouth | `frozen shocked stare, eyes wide unblinking, mouth slack open, pale` |
| Stunned | Blank stare, mouth slightly open, uncomprehending | `blank stunned stare, mouth hanging slightly, eyes unfocused, brows flat` |
| Astonished | Wide eyes, hand to mouth, raised brows | `eyes round and huge, one hand covering mouth, brows raised to hairline` |

### 😒 Disgust / Contempt

| Emotion | Visual Descriptors | Prompt Text |
|---|---|---|
| Disgusted | Wrinkled nose, curled upper lip, squinted eyes | `nose wrinkled in disgust, upper lip curled, eyes squinted, face turned aside` |
| Contemptuous | One-sided sneer, narrowed eyes, raised chin | `one-sided sneer, eyes narrowed in disdain, chin raised looking down at viewer` |
| Repulsed | Full cringe, eyes squeezed shut, turned away | `face cringed away, eyes squeezed shut, mouth grimacing, entire expression averted` |

### 🤔 Confusion / Uncertainty

| Emotion | Visual Descriptors | Prompt Text |
|---|---|---|
| Confused | Tilted head, furrowed brow, squinted eyes | `head slightly tilted, brow deeply furrowed, eyes squinting in confusion` |
| Puzzled | One raised brow, slight frown, looking sideways | `one eyebrow raised high, slight frown, eyes looking to the side searching for answers` |
| Doubtful | Narrowed eyes, tight skeptical mouth | `eyes narrowed in doubt, mouth a tight skeptical line, one brow slightly raised` |
| Hesitant | Biting lip, wide uncertain eyes, half-step back | `lower lip caught between teeth, wide uncertain eyes, body leaning slightly away` |

### 😌 Calm / Neutral / Serene

| Emotion | Visual Descriptors | Prompt Text |
|---|---|---|
| Serene | Soft half-smile, relaxed eyes, smooth brow | `peaceful serene expression, soft half-smile, eyes gently closed or half-lidded, smooth relaxed brow` |
| Stoic | Blank unreadable face, level gaze | `stoic unreadable expression, flat level gaze, mouth neutral line, brow smooth` |
| Neutral | Relaxed face, neither happy nor sad | `neutral relaxed face, mouth at rest, eyes open and calm, no strong expression` |
| Confident | Slight smile, direct gaze, lifted chin | `confident slight smile, direct steady gaze, chin slightly raised, brow smooth` |

### 😏 Smug / Sly / Mischievous

| Emotion | Visual Descriptors | Prompt Text |
|---|---|---|
| Smug | Self-satisfied grin, chin up, half-lidded eyes | `smug self-satisfied grin, chin raised, eyes half-lidded in amusement` |
| Sly | Knowing half-smile, narrowed eyes, one brow raised | `sly knowing half-smile, eyes narrowed to slits, one brow arched` |
| Mischievous | Wide playful grin, sparkling eyes | `wide mischievous grin, eyes sparkling with humor, brows raised playfully` |
| Taunting | Mocking smirk, chin out, challenging gaze | `mocking smirk, chin thrust forward, challenging direct gaze` |

### 😰 Shame / Embarrassment

| Emotion | Visual Descriptors | Prompt Text |
|---|---|---|
| Embarrassed | Blushing, looking down, tight awkward smile | `face flushed red, eyes looking down in embarrassment, tight awkward forced smile` |
| Ashamed | Head bowed, eyes averted, compressed lips | `head bowed low, eyes averted to the ground, lips compressed tight, face downturned` |
| Guilty | Avoiding eye contact, fidgeting, slight wince | `eyes refusing to meet the viewer, slight wince, jaw tight, fidgeting expression` |

### 😴 Tired / Weary

| Emotion | Visual Descriptors | Prompt Text |
|---|---|---|
| Exhausted | Drooping eyelids, slack mouth, heavy brow | `eyelids drooping heavy, mouth slightly slack, brow weighted down, face drained` |
| Sleepy | Half-closed eyes, yawn suppressed, soft expression | `eyes half-closed in drowsiness, suppressing a yawn, soft unfocused gaze` |
| Resigned | Flat expression, eyes distant, shoulders metaphorically shrugged | `flat resigned expression, eyes distant and blank, mouth slightly open, no energy` |

### 🔄 Transition Expressions

Use these when a shot captures a character changing from one emotion to another:

| Transition | Prompt Text |
|---|---|
| Joy → Sad | `smile fading, eyes losing their brightness, corners of mouth starting to turn down` |
| Anger → Calm | `fury draining from face, jaw unclenching, brows smoothing out, breathing steadying` |
| Calm → Shocked | `serene expression breaking into wide-eyed shock, mouth dropping open` |
| Confident → Nervous | `confident smile wavering, eyes darting, brow starting to crease with worry` |
| Smug → Humble | `smug grin faltering, eyes dropping, chin lowering, face softening` |

## Composing Multi-Feature Expressions

For best results with Qwen Image Edit, combine features from different regions:

**Three-region rule**: Describe at least the **mouth** + **eyes** + **brow/forehead** for each character.

```
Good:  "confident grin, eyes crinkled at corners, smooth relaxed brow"
Bad:   "happy"  ← too abstract, model may interpret loosely
```

**Intensity scale**: Use modifiers to control expression strength

| Modifier | Effect |
|---|---|
| Slight / faint / subtle | Gentle version of the expression |
| (unmodified) | Standard intensity |
| Deep / intense / strong | Amplified version |
| Extreme / full-blown | Maximum intensity, dramatic |

## Expression-Scene Consistency

When the scene mood conflicts with a character's expression, the prompt should **explicitly describe both**:

```
Scene: Joyful victory celebration
Character (who lost): "bitter tight smile, eyes glistening with unshed tears, 
                       jaw clenched — trying to look happy but clearly hurting underneath"
```

Qwen Image Edit handles emotional dissonance better when you describe it explicitly rather than relying on the model to infer it from context.