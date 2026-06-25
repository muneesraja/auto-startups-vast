Your goal is to understand the current implementation of `story-to-video-deterministic` skill and current implementation old user plan by checking `discussion-and-docs/deterministic-implementation-resource/User-Plan.md`. Then we are going to plan a migration implementation plan from Flux and Ideogram to generate images to `Grok imagine image` via fal.ai's to generate character sheet, generate FF and LF for each shot of story and later. Come with an architecture diagram which helps me understand the plan. 

Notes:
- Grok imagine takes image reference unlike ideogram 4, so the consistency patches should be re-wired and can be deprecated in our new `story-to-video-cloud` skill implementation plan.
- Shouldn't change anything that is relevant to FFLF and continuity logic and steps of prompt planning.
- Now FF image itself will get passed with the generated character sheet.
- I've noticed a strange issue, we need to create an agent or a seprate step to check if required references were attached to the shot regardless of the steps.
For ex scenarios. 
 * LLMs are missing to reference of a character that is in the scene. Elephant, panda and monkey in the scene - three of these should get referenced in the shot prompt but it's missing in the array.
 * Duplicate of character reference in the array should be avoided either programmatically or by agents
