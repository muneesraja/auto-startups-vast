# Hare and Tortoise Race - Character Sheets and Scene Prompts

Source story: `temp.md`

Output root: `temp/hare-and-tortoise-race/`

Style: Pixar-style 3D animation, rich lighting, expressive anthropomorphic woodland characters, warm storybook color palette.

## Character Reference Sheet Prompts

These are the prompts used by the Gemini character-sheet phase. Each generated sheet should be saved in `temp/hare-and-tortoise-race/characters/`.

### Hare

Output file: `characters/hare_reference_sheet.png`

```text
Create a professional character reference sheet for the following character.

Character: anthropomorphic hare, tall and wiry athletic build, sandy brown fur with lighter cream muzzle and belly, long upright ears with pink inner ears, sharp green eyes, expressive cocky grin, oversized hind paws, wearing a neon-green sweatband, slim red running shorts, and a small shiny gold wristwatch

Layout:
- Top row: four full-body standing views (front, left 3/4 view, right side profile, back view)
- Bottom row: three face close-up portraits (front, left 3/4 angle, right side profile)

Requirements:
- CONSISTENT identity across ALL seven views - same face, same body, same outfit
- Clean white/neutral background
- Even studio lighting
- Style: Pixar-style 3D animation, rich lighting, expressive anthropomorphic woodland characters, warm storybook color palette
- Each view clearly separated with space between them
- Character should be the same scale/proportion in each view
```

### Tortoise

Output file: `characters/tortoise_reference_sheet.png`

```text
Create a professional character reference sheet for the following character.

Character: anthropomorphic tortoise, short and sturdy body, olive-green skin, large dark green domed shell with golden hexagonal scute pattern, gentle brown eyes behind round silver spectacles, wrinkled kind face, short thick legs, wearing a small sky-blue neckerchief

Layout:
- Top row: four full-body standing views (front, left 3/4 view, right side profile, back view)
- Bottom row: three face close-up portraits (front, left 3/4 angle, right side profile)

Requirements:
- CONSISTENT identity across ALL seven views - same face, same body, same outfit
- Clean white/neutral background
- Even studio lighting
- Style: Pixar-style 3D animation, rich lighting, expressive anthropomorphic woodland characters, warm storybook color palette
- Each view clearly separated with space between them
- Character should be the same scale/proportion in each view
```

### Fox

Output file: `characters/fox_reference_sheet.png`

```text
Create a professional character reference sheet for the following character.

Character: anthropomorphic fox, medium height and lean build, orange-red fur, white chest and muzzle, sharp amber eyes, bushy tail with white tip, wearing a tidy black vest, small bow tie, and carrying a small betting ledger

Layout:
- Top row: four full-body standing views (front, left 3/4 view, right side profile, back view)
- Bottom row: three face close-up portraits (front, left 3/4 angle, right side profile)

Requirements:
- CONSISTENT identity across ALL seven views - same face, same body, same outfit
- Clean white/neutral background
- Even studio lighting
- Style: Pixar-style 3D animation, rich lighting, expressive anthropomorphic woodland characters, warm storybook color palette
- Each view clearly separated with space between them
- Character should be the same scale/proportion in each view
```

### Squirrel

Output file: `characters/squirrel_reference_sheet.png`

```text
Create a professional character reference sheet for the following character.

Character: anthropomorphic squirrel, small energetic body, reddish-brown fur, cream belly, bright black eyes, huge curled fluffy tail, wearing a tiny referee cap and holding a black-and-white checkered flag

Layout:
- Top row: four full-body standing views (front, left 3/4 view, right side profile, back view)
- Bottom row: three face close-up portraits (front, left 3/4 angle, right side profile)

Requirements:
- CONSISTENT identity across ALL seven views - same face, same body, same outfit
- Clean white/neutral background
- Even studio lighting
- Style: Pixar-style 3D animation, rich lighting, expressive anthropomorphic woodland characters, warm storybook color palette
- Each view clearly separated with space between them
- Character should be the same scale/proportion in each view
```

### Forest Animals

Output file: `characters/forest_animals_reference_sheet.png`

```text
Create a professional character reference sheet for the following character group.

Character group: group of varied anthropomorphic woodland animals including rabbits, hedgehogs, birds, deer, mice, and chipmunks, colorful small outfits, rounded expressive faces, arranged as a lively cheering crowd

Layout:
- Top row: four small group lineup views (front, left 3/4 view, side profile grouping, back view grouping)
- Bottom row: three close-up cluster portraits showing representative crowd faces

Requirements:
- CONSISTENT group identity across ALL seven views - same species mix, same outfit colors, same friendly storybook style
- Clean white/neutral background
- Even studio lighting
- Style: Pixar-style 3D animation, rich lighting, expressive anthropomorphic woodland characters, warm storybook color palette
- Each view clearly separated with space between them
- The group should stay readable as a reusable crowd reference
```

## Scene Image Generation Prompts

Use only the listed reference sheets for each scene. These prompts are for creating still scene images with Gemini or an open-source image model. Save results as `scenes/scene_001.png`, etc.

### Scene 1 - The Callout

Reference images: `hare_reference_sheet.png`, `tortoise_reference_sheet.png`, `fox_reference_sheet.png`, `forest_animals_reference_sheet.png`

```text
Characters in this scene must match the provided reference images exactly:
- Hare: anthropomorphic hare, tall and wiry athletic build, sandy brown fur with lighter cream muzzle and belly, long upright ears with pink inner ears, sharp green eyes, expressive cocky grin, oversized hind paws, wearing a neon-green sweatband, slim red running shorts, and a small shiny gold wristwatch
- Tortoise: anthropomorphic tortoise, short and sturdy body, olive-green skin, large dark green domed shell with golden hexagonal scute pattern, gentle brown eyes behind round silver spectacles, wrinkled kind face, short thick legs, wearing a small sky-blue neckerchief
- Fox: anthropomorphic fox, medium height and lean build, orange-red fur, white chest and muzzle, sharp amber eyes, bushy tail with white tip, wearing a tidy black vest, small bow tie, and carrying a small betting ledger
- Forest Animals: group of varied anthropomorphic woodland animals including rabbits, hedgehogs, birds, deer, mice, and chipmunks, colorful small outfits, rounded expressive faces, arranged as a lively cheering crowd

Scene setting: edge of the Old Oak Forest, massive oak trunks, mossy roots, scattered wildflowers, morning sunlight filtering through leaves.
Action: Hare bounces on his toes and mocks Tortoise while Tortoise adjusts his spectacles and calmly proposes a five-mile race to the Ancient Willow. Forest animals gasp as Fox prepares odds in his ledger.
Mood: public challenge, smug teasing against quiet confidence and crowd surprise.
Camera: medium wide shot at eye level, Hare and Tortoise centered with crowd behind them.
Style: Pixar-style 3D animation, rich lighting, expressive anthropomorphic woodland characters, warm storybook color palette.
```

### Scene 2 - The Explosive Start

Reference images: `hare_reference_sheet.png`, `tortoise_reference_sheet.png`, `squirrel_reference_sheet.png`, `forest_animals_reference_sheet.png`

```text
Characters in this scene must match the provided reference images exactly:
- Hare: anthropomorphic hare, tall and wiry athletic build, sandy brown fur with lighter cream muzzle and belly, long upright ears with pink inner ears, sharp green eyes, expressive cocky grin, oversized hind paws, wearing a neon-green sweatband, slim red running shorts, and a small shiny gold wristwatch
- Tortoise: anthropomorphic tortoise, short and sturdy body, olive-green skin, large dark green domed shell with golden hexagonal scute pattern, gentle brown eyes behind round silver spectacles, wrinkled kind face, short thick legs, wearing a small sky-blue neckerchief
- Squirrel: anthropomorphic squirrel, small energetic body, reddish-brown fur, cream belly, bright black eyes, huge curled fluffy tail, wearing a tiny referee cap and holding a black-and-white checkered flag
- Forest Animals: group of varied anthropomorphic woodland animals including rabbits, hedgehogs, birds, deer, mice, and chipmunks, colorful small outfits, rounded expressive faces, arranged as a lively cheering crowd

Scene setting: forest starting line marked in packed dirt, checkered banner between two posts, dusty path stretching into the distance.
Action: Squirrel drops the checkered flag. Hare launches forward in a blur and kicks up a dust cloud while Tortoise coughs softly and takes his first deliberate step.
Mood: explosive speed contrasted with patient resolve.
Camera: low-angle wide shot tracking along the race path from the starting line.
Style: Pixar-style 3D animation, rich lighting, expressive anthropomorphic woodland characters, warm storybook color palette.
```

### Scene 3 - The Mid-Race Hubris

Reference images: `hare_reference_sheet.png`

```text
Characters in this scene must match the provided reference image exactly:
- Hare: anthropomorphic hare, tall and wiry athletic build, sandy brown fur with lighter cream muzzle and belly, long upright ears with pink inner ears, sharp green eyes, expressive cocky grin, oversized hind paws, wearing a neon-green sweatband, slim red running shorts, and a small shiny gold wristwatch

Scene setting: sunny clover patch at the halfway mark beneath a shady elm tree, soft grass, clover blossoms, warm midday light.
Action: Hare checks his pulse, looks back at the empty path, yawns with overconfidence, then curls up under the elm for a short nap.
Mood: smug ease turning into sleepy carelessness.
Camera: medium shot from a slight high angle, framing Hare beside the clover patch.
Style: Pixar-style 3D animation, rich lighting, expressive anthropomorphic woodland characters, warm storybook color palette.
```

### Scene 4 - The Grind

Reference images: `tortoise_reference_sheet.png`, `hare_reference_sheet.png`

```text
Characters in this scene must match the provided reference images exactly:
- Tortoise: anthropomorphic tortoise, short and sturdy body, olive-green skin, large dark green domed shell with golden hexagonal scute pattern, gentle brown eyes behind round silver spectacles, wrinkled kind face, short thick legs, wearing a small sky-blue neckerchief
- Hare: anthropomorphic hare, tall and wiry athletic build, sandy brown fur with lighter cream muzzle and belly, long upright ears with pink inner ears, sharp green eyes, expressive cocky grin, oversized hind paws, wearing a neon-green sweatband, slim red running shorts, and a small shiny gold wristwatch

Scene setting: dusty forest path near the halfway point, sun lower in the sky, sleeping Hare under a nearby elm, Ancient Willow direction ahead.
Action: Tortoise sweats and trudges past the sleeping Hare without stopping, keeping his eyes fixed ahead on the path to the Ancient Willow.
Mood: exhausted determination and disciplined focus.
Camera: side-on tracking medium wide shot, Tortoise moving foreground while Hare sleeps in background.
Style: Pixar-style 3D animation, rich lighting, expressive anthropomorphic woodland characters, warm storybook color palette.
```

### Scene 5 - The Rude Awakening

Reference images: `hare_reference_sheet.png`, `tortoise_reference_sheet.png`

```text
Characters in this scene must match the provided reference images exactly:
- Hare: anthropomorphic hare, tall and wiry athletic build, sandy brown fur with lighter cream muzzle and belly, long upright ears with pink inner ears, sharp green eyes, expressive cocky grin, oversized hind paws, wearing a neon-green sweatband, slim red running shorts, and a small shiny gold wristwatch
- Tortoise: anthropomorphic tortoise, short and sturdy body, olive-green skin, large dark green domed shell with golden hexagonal scute pattern, gentle brown eyes behind round silver spectacles, wrinkled kind face, short thick legs, wearing a small sky-blue neckerchief

Scene setting: beneath the elm tree, long afternoon shadows stretching across the path toward the distant Ancient Willow.
Action: Hare bolts upright, checks his gold watch in panic, then spots Tortoise as a small dark shape close to the finish line.
Mood: sudden panic and disbelief.
Camera: medium close-up on Hare with a shallow view down the path behind him.
Style: Pixar-style 3D animation, rich lighting, expressive anthropomorphic woodland characters, warm storybook color palette.
```

### Scene 6 - The Photo Finish

Reference images: `hare_reference_sheet.png`, `tortoise_reference_sheet.png`, `forest_animals_reference_sheet.png`

```text
Characters in this scene must match the provided reference images exactly:
- Hare: anthropomorphic hare, tall and wiry athletic build, sandy brown fur with lighter cream muzzle and belly, long upright ears with pink inner ears, sharp green eyes, expressive cocky grin, oversized hind paws, wearing a neon-green sweatband, slim red running shorts, and a small shiny gold wristwatch
- Tortoise: anthropomorphic tortoise, short and sturdy body, olive-green skin, large dark green domed shell with golden hexagonal scute pattern, gentle brown eyes behind round silver spectacles, wrinkled kind face, short thick legs, wearing a small sky-blue neckerchief
- Forest Animals: group of varied anthropomorphic woodland animals including rabbits, hedgehogs, birds, deer, mice, and chipmunks, colorful small outfits, rounded expressive faces, arranged as a lively cheering crowd

Scene setting: finish line beneath the huge Ancient Willow, painted line across dirt path, crowd gathered around roots, golden late-afternoon light.
Action: Hare sprints desperately toward the finish while Tortoise stretches his neck forward and crosses the line just before Hare reaches him. The forest animals react in shock and excitement.
Mood: desperate sprint, painful effort, sudden victory.
Camera: dramatic low-angle wide shot at the finish line, Tortoise foreground and Hare closing in behind.
Style: Pixar-style 3D animation, rich lighting, expressive anthropomorphic woodland characters, warm storybook color palette.
```

## LTX 2.3 I2V Motion Prompts

These prompts are for animating the generated scene images later. They intentionally describe motion rather than re-describing the still image.

### Scene 1

```text
Hare bounces lightly on his toes and jabs one paw forward with a smug grin, his ears springing with each taunting motion. Tortoise lifts one hand to his spectacles, straightens them, and extends a calm paw in challenge. The crowd behind them recoils and leans forward in waves of surprise while leaves flutter above the clearing. The camera holds steady in a medium wide shot, letting the challenge land between the two racers.
```

### Scene 2

```text
Squirrel snaps the flag downward in one sharp motion as Hare blasts forward and dust erupts from the path. Tortoise coughs once, blinks through the dust, and plants one careful foot ahead. The crowd throws up paws and wings as the dust cloud rolls backward through the starting line. The camera tracks low along the path, following the first burst of speed before settling on the small deliberate step.
```

### Scene 3

```text
Hare presses two fingers to his wrist, raises his eyebrows at the easy pulse, and lets a wide yawn stretch across his face. He lowers himself into the clover, folds his arms, and lets one ear flop lazily against the grass. Clover blossoms sway in the warm breeze while small patches of sunlight drift over him. The camera performs a gentle slow dolly-in from a medium shot toward his sleeping face.
```

### Scene 4

```text
Tortoise drags one heavy foot forward, pauses for a breath, then takes another step past the sleeping figure. Sweat beads slide down his face as his jaw tightens and his gaze stays locked ahead. The nearby grass barely stirs while afternoon light lengthens across the dusty path. The camera tracks beside him at shell height, keeping his steady progress in frame.
```

### Scene 5

```text
Hare jolts upright, ears snapping high as he fumbles for the gold watch on his wrist. His eyes widen, his mouth falls open, and he twists toward the finish line with a sharp inhale. Long shadows stretch farther across the path as leaves tremble in a cooler breeze. The camera pushes in from a medium close-up to a tighter view as panic takes over his face.
```

### Scene 6

```text
Hare pounds forward in a desperate sprint, kicking dirt behind him with each powerful stride. Tortoise strains his neck forward, squeezes his eyes, and slides one foot across the finish mark. The crowd surges toward the line with raised arms as dust and golden light swirl around the racers. The camera holds low near the finish, then pushes in slightly as the winning step lands.
```

