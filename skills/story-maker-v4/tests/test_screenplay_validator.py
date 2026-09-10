"""Tests for the screenplay format validator (validate_screenplay).

Verifies:
- Valid screenplays pass.
- Missing sluglines trigger errors.
- Prose walls trigger warnings.
- Missing metadata sections trigger errors.
- ALL-CAPS sound cues and dialogue cues are detected.
"""

import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from tools.validators import validate_screenplay


# -- Fixtures ----------------------------------------------------------------

VALID_SCREENPLAY = """\
# Screenplay

```text
EXT. SUNLIT POND - DAY

YOUNG OLLIE (5), an impossibly cute, fuzzy Pookoo with wild spiky fur
and massive green eyes, sits on a mossy boulder.

A sudden BUZZ. A glowing GREEN DRAGONFLY darts past his ears.

Ollie turns abruptly to follow it. His hind foot SLIPS.

SPLASH! The basket hits the water.

OLLIE'S POV - THROUGH THE CYLINDER

Underwater light dances across river stones.

BACK TO SHORE

Ollie's eyes widen.

OLLIE
(squeaky, sheepish)
Hey, Dad...
(beat)
Thirsty?

FADE OUT.
```

## Characters
- id: char_01
  name: Young Ollie

## Locations
- id: loc_01
  name: Sunlit Pond

## Objects
- id: obj_01
  name: Diving Helmet

## Constraints
- id: H1
  type: co_presence_exclusion
  severity: BLOCKER
"""

MISSING_SLUGLINES = """\
# Screenplay

```text
Ollie sits on a rock by the pond. He looks at his basket.
A dragonfly buzzes past. He turns and his basket falls into the water.
```

## Characters
- id: char_01

## Locations
- id: loc_01
"""

PROSE_WALL = """\
# Screenplay

```text
EXT. FOREST - DAY

Ollie walks through the forest and sees many trees and animals and the
sunlight filters through the canopy creating dappled patterns on the
mossy ground beneath his feet as he carefully navigates the winding
path that leads deeper into the heart of the ancient woodland where
mysterious creatures lurk in the shadows between the gnarled roots of
towering oak trees that have stood for centuries watching over the land.

OLLIE
Hello?

FADE OUT.
```

## Characters
- id: char_01

## Locations
- id: loc_01
"""

NO_METADATA = """\
# Screenplay

```text
EXT. GARDEN - DAY

OLLIE (5) picks flowers. A CRACK echoes from the house.

OLLIE
What was that?

FADE OUT.
```
"""

DIALOGUE_FREE = """\
# Screenplay

```text
EXT. DESERT - DAY

Wind HOWLS across barren dunes. A lone figure TRUDGES forward.

Sand WHIPS against weathered cloth. Each step CRUNCHES into dry crust.

The figure pauses. Ahead, a faint shimmer of water—or mirage.

FADE OUT.
```

## Characters
- id: char_01

## Locations
- id: loc_01
"""


# -- Tests -------------------------------------------------------------------

class TestScreenplayValidator(unittest.TestCase):

    def test_valid_screenplay_passes(self):
        res = validate_screenplay(VALID_SCREENPLAY)
        self.assertTrue(res.ok, f"Expected pass, got errors: {res.errors}")
        self.assertEqual(len(res.errors), 0)

    def test_valid_has_sound_cues(self):
        res = validate_screenplay(VALID_SCREENPLAY)
        # Should NOT have the "no sound cues" warning
        sound_warnings = [w for w in res.warnings if "sound cues" in w.lower()]
        self.assertEqual(len(sound_warnings), 0,
                         "Valid screenplay has BUZZ, SLIPS, SPLASH — should find sound cues")

    def test_missing_sluglines_errors(self):
        res = validate_screenplay(MISSING_SLUGLINES)
        self.assertFalse(res.ok)
        self.assertTrue(any("slugline" in e.lower() for e in res.errors),
                        f"Expected slugline error, got: {res.errors}")

    def test_prose_wall_warns(self):
        res = validate_screenplay(PROSE_WALL)
        self.assertTrue(any("prose wall" in w.lower() for w in res.warnings),
                        f"Expected prose wall warning, got warnings: {res.warnings}")

    def test_missing_characters_section_errors(self):
        res = validate_screenplay(NO_METADATA)
        self.assertFalse(res.ok)
        self.assertTrue(any("Characters" in e for e in res.errors),
                        f"Expected missing Characters error, got: {res.errors}")

    def test_missing_locations_section_errors(self):
        res = validate_screenplay(NO_METADATA)
        self.assertFalse(res.ok)
        self.assertTrue(any("Locations" in e for e in res.errors),
                        f"Expected missing Locations error, got: {res.errors}")

    def test_dialogue_free_screenplay_warns(self):
        res = validate_screenplay(DIALOGUE_FREE)
        # Should pass (dialogue-free is valid) but warn
        self.assertTrue(res.ok)
        self.assertTrue(any("dialogue" in w.lower() for w in res.warnings),
                        f"Expected dialogue warning, got: {res.warnings}")

    def test_dialogue_free_has_sound_cues(self):
        res = validate_screenplay(DIALOGUE_FREE)
        # HOWLS, TRUDGES, WHIPS, CRUNCHES should be found
        sound_warnings = [w for w in res.warnings if "sound cues" in w.lower()]
        self.assertEqual(len(sound_warnings), 0,
                         "Dialogue-free screenplay has HOWLS, TRUDGES, etc.")


if __name__ == "__main__":
    unittest.main()
