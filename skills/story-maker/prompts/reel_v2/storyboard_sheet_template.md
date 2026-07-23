Create a text-free Pixar-style **photo album / contact sheet** of cinematic animation stills — not a production storyboard document.

This album feeds **LTX Director / FLF video**: each **row** is one preferred continuous clip pair (left = start frame, right = end frame).

{grid_layout_instruction}

Page layout (ON the image — no chrome):
• Mild portrait **8:9** page (e.g. 1024×1152) — **NOT 9:16**
• Exactly a **4 rows × 2 columns** grid (row-major: left→right, top→bottom) — **never 5 rows, never 6 rows, never 10 or 12 panels**
• Paint **exactly {panel_count}** panels in that 4×2 album (Panel 1 = row1 col1 … Panel 8 = row4 col2)
• Packed 8:9 page → each cell is approximately **16:9** landscape — fill every cell edge-to-edge with widescreen cinematic stills
• Thin uniform black or white gutters only as separators between panels
• No header, footer, title bar, timeline, notes, shot numbers, CAM labels, or action captions
• No typography of any kind on the page
• CRITICAL: do not invent extra rows or panels beyond the 4×2 contact sheet; do not add large empty letterbox bands

FLF row-pair map (guidance only — never letter onto the page):
• Row 1: Panel 1 = **start frame** → Panel 2 = **end frame**
• Row 2: Panel 3 = **start frame** → Panel 4 = **end frame**
• Row 3: Panel 5 = **start frame** → Panel 6 = **end frame**
• Row 4: Panel 7 = **start frame** → Panel 8 = **end frame**
• Within each row: paint a progressive morph (readable pose/camera change left→right); no identical twin panels; no teleport
• Across rows on `continue` edges: end of row N must hand off to start of row N+1 (same cast, geography, screen direction)
• `match_cut` may break the handoff; keep identity locks
• **Middle** guides are rare — only when an authored Director guide role says `middle` on a longer multi-panel chain (not a third column)

Each panel cell:
• Contains one landscape **16:9** cinematic still (wider than tall)
• Panel art fills its frame edge-to-edge; leftover vertical space between rows is the same gutter/background — never captions
• Fully painted Pixar-quality content in every active cell

Reference image roles (match these attached images in order — guidance only, not on-page text):
{reference_roles}

{continuity_note}

Scene context (guidance only — do not render as text on the page):
• Scene: {scene_id} / Sheet: {sheet_number} — "{sheet_subtitle}"
• Environment: {environment}
• Time of day: {time_of_day}
• Lighting: {lighting}
• Staging geography: {staging}

Maintain perfect character consistency across every panel:
{character_consistency}

Environment (match the location lock world geometry and lighting):
{environment_block}

Storyboard Sheet {sheet_number} includes these shots (paint in order; do not letter them onto the page):
{shot_listing}

{motion_spine}

Keyframe paint rules (guidance only — never letter onto the page):
• Default: each row is one FLF pair — left cell = start frame, right cell = end frame.
• Honor Incoming bridge / Outgoing bridge lines: land each still as the end of the prior morph and a valid start for the next.
• `long_gap_bridge` edges need a readable midpoint pose (partial turn / mid scale), not another extreme jump.
• `match_cut` edges may jump geography/subject but keep identity locks.
• When a panel lists an authored Director guide role (`start` / `middle` / `end`), that role overrides the default column hint for that cell.

Panel-by-panel direction (must match grid order; board-beat timing is editorial only — do not letter onto the page; do not treat board beats as LTX render durations):
{panel_lines}

Visual style:
Ultra cinematic Pixar animation
Disney-quality lighting
Warm natural colors
Photo-album contact sheet of 16:9 stills on an 8:9 page
Thin black or white separators only
No production document chrome

{render_style}

NEGATIVE PROMPT:
Text, labels, captions, titles, headers, footers, timelines, notes, shot numbers, CAM labels, DUR labels, Action: lines, watermarks, logos, dialogue balloons, blank panels, empty frames, white placeholder cells, unfinished panels, comic page, manga, sketch, rough draft, inconsistent characters, duplicate limbs, photorealistic human, portrait panel frames, repeated identical walk-away compositions, copy of previous scene sheet layouts, identical twin panels in the same row, 5-row grid, 6-row grid, 10 panels, 12 panels, extra rows beyond 4×2, tall 9:16 phone page, large empty letterbox bands.
