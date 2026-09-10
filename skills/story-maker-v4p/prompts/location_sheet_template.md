# Location Lock Sheet

Create a single ultra-cinematic **empty-stage establishing plate** for a reusable location lock.

## Location
- **Id:** {location_id}
- **Name:** {location_name}
- **Description:** {location_description}

## Establishing brief
{establishing_prompt}

## Rules
- **Wide-angle 360-degree view** of the entire space — all walls, corners, and
  key landmarks visible in one frame as if the camera captures the full room.
  For indoor spaces, show the complete layout; for outdoor spaces, show the full
  environment panorama.
- 16:9 landscape establishing composition at 4K (3840×2160)
- Show landmarks, architecture, foliage, props, and lighting that define this place
- **No named heroes / protagonists** in frame (tiny unnamed ambient extras only if needed for scale)
- Animation-ready held environment; readable geography left-to-right
- Match the production render style below
- Render as a single clean plate; no panels, no collage, no storyboard grid

## MiniMax H3 360° Background Video Recipe (Contradiction-Free Walls)
This wide-angle establishing plate serves as the opening frame to generate a 360°
environment video (`assets/locations/{location_id}_360.mp4`) via MiniMax H3.
By first shooting the desired environment in a continuous form with H3, all four walls
and corners are locked in a single definitive video source, eliminating background
drift and redraw hallucinations across subsequent camera cuts.

Suggested H3 360° Video Prompt:
> [reference generation] The target video shows a full 360-degree panoramic sweep of the empty room.
> detailed_description:
> {render_style}
> [Shot 1] From a fixed central tripod pivot point, the camera pans 360 degrees horizontally to the right with small amplitude at slow constant speed, smoothly revealing all four walls, architectural corners, doorways, windows, and interior fixtures of the empty space, returning seamlessly to the opening framing. The space remains completely static with zero people, zero characters, and perfectly held illumination throughout.

*Core principle: It doesn't have to be an orbit video specifically; as long as you create a "source for backgrounds that can be extracted later without contradictions", that seems to do the trick.*

{render_style}

NEGATIVE PROMPT:
Named characters, hero portraits, close-ups of people, text, watermarks, logos, subtitles, photorealistic humans, empty white void, collage, comic panels.

