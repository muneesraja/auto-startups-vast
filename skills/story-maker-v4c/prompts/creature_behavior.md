# Creature behavior (every animal)

Role model for **all** animals on screen: wild, domestic, or invented. Not a
species encyclopedia. Read this before writing story, storyboard, sheets, or
H3 prompts whenever a non-human creature is visible.

Specialize last: after role/state/distance are set, add 1–2 kinematics lines
(crouch-stalk vs head-up freeze vs flock-scatter). Mixed shots must show
**conflicting** states, not one calm group.

## Per creature on screen

**Role:** `predator | prey | scavenger | herd_grazer | territorial |
guardian_parent | domestic_bonded | infant_of_species | stylized_character`

`stylized_character` (speech, cartoon acting, mascot smiles) is allowed only
when Tone is `stylized`. Grounded default forbids it.

**State:** `unaware | alert_assess | threat_display | stalk | chase | freeze |
flight | feed_or_graze | care_young | ignore_distance`

`ignore_distance` only when the animal is **far** and unthreatened.

**Distance to humans:** `far | flight_zone | close | contact`

Close or contact with `predator`, `territorial`, or wild `guardian_parent` is
**danger** unless a bond is already established in the story.

**Human reaction:** match role + distance.

- Danger + child → adults between child and animal, freeze or retreat, tense
  faces, quiet voices.
- Prey in flight does not make humans smile.
- Calm faces only for `domestic_bonded` with an established bond.

## Bans (every species, grounded)

No camera-smile, wave, person-greeting, posing, or pet-nuzzle unless
`domestic_bonded` or Tone is `stylized`. No ignoring a nearby danger-role
animal. Same rules for birds, ungulates, reptiles, insects, dogs, invented
creatures.

## Agent 1

On every non-human in `## Characters`, include `creature_role:` (and typical
state) in the free-form appearance block. This is **not** a parsed validator
field.
