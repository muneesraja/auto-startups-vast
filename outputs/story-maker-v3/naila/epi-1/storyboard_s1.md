# Scene s1 — Naila's crying and the shoulder-top view
target_seconds: 80
cast: [char_01, char_02, char_03, char_04, char_05]
location_ref_id: loc_forest_shelter

## Row 1 (LTX session 1)
| col | shot_id | duration_seconds | characters_present | depth_per_char | camera_angle | position_xy | looks_at | expression | mood | intent | facing | angle | spatial_relation | must_not_show |
| 1 | s1_p1 | 10 | [char_01] | {char_01:2} | wide | {char_01:[0.5,0.5]} | none | stirring | calm | rest | forward | 0deg | Naila alone on wooden swing seat between two trees, feet dangling, simple forest background | no parrot, no dog, no father, no horse, no elephant close |
| 2 | s1_p2 | 10 | [char_01,char_04] | {char_01:2,char_04:2} | eye_level | {char_01:[0.5,0.5],char_04:[0.62,0.42]} | char_01 | worried | tender | comfort | left | 0deg | green parrot landed on Naila's right shoulder, leaning toward her cheek; Naila still on swing seat | no dog, no father, no horse, no body contact from parrot beyond wing near cheek |
| 3 | s1_p3 | 10 | [char_01,char_03,char_04] | {char_01:2,char_03:3,char_04:2} | eye_level | {char_01:[0.5,0.45],char_03:[0.5,0.82],char_04:[0.62,0.4]} | char_03 | eager | worried | cheer | up | -5deg | golden dog sitting on ground directly below swing looking up; parrot still on Naila's shoulder; Naila on swing seat | no father, no horse, no elephant, dog does not touch swing |
| 4 | s1_p4 | 10 | [char_01,char_03,char_04] | {char_01:2,char_03:4,char_04:2} | wide | {char_01:[0.5,0.45],char_03:[0.15,0.8],char_04:[0.62,0.4]} | char_03 | determined | urgent | fetch | left | 0deg | golden dog now running left away from swing toward far paddock, receding into mid-ground; Naila and parrot remain on swing | no father, no horse, dog must not touch swing ropes |

## Row 2 (LTX session 2)
| col | shot_id | duration_seconds | characters_present | depth_per_char | camera_angle | position_xy | looks_at | expression | mood | intent | facing | angle | spatial_relation | must_not_show |
| 1 | s1_p5 | 10 | [char_02,char_03] | {char_02:2,char_03:3} | medium | {char_02:[0.5,0.5],char_03:[0.72,0.72]} | char_03 | alert | concerned | alert | right | 0deg | father standing beside wooden feed trough in far left paddock, turning toward golden dog that has just arrived barking at his feet; elephant visible in deep background only | no Naila, no parrot, no horse in foreground, elephant only in deep background |
| 2 | s1_p6 | 10 | [char_02,char_05] | {char_02:3,char_05:3} | wide | {char_02:[0.35,0.5],char_05:[0.35,0.62]} | none | determined | urgent | ride | right | 0deg | father mounted on chestnut horse, riding rightward across yard toward distant swing, receding into mid-ground; no dog in this frame | no Naila, no parrot, no dog, no elephant close, horse saddle and bridle visible |
| 3 | s1_p7 | 10 | [char_01,char_02,char_05] | {char_01:2,char_02:2,char_05:3} | two_shot | {char_01:[0.5,0.42],char_02:[0.5,0.62],char_05:[0.65,0.7]} | char_01 | transitional | relieved | comfort | up | 0deg | horse stopped a few steps to the left of the swing; father remains seated in saddle, leaning upper body only slightly toward Naila; Naila on swing seat, tears still wet, mouth just beginning to turn into a small surprised smile | no body contact, no fully resolved smile, no horse touching swing ropes, no father dismounted, no dog, no parrot |
| 4 | s1_p8 | 10 | [char_01,char_02] | {char_01:1,char_02:2} | low_angle | {char_01:[0.5,0.3],char_02:[0.5,0.55]} | none | wide-eyed | joyful | enjoy | forward | 10deg | father standing firmly on ground, lifting Naila up onto his shoulders; Naila high above, arms slightly out, looking out over the shelter; dog and parrot visible below/around them | no horse in immediate foreground, no elephant close, father must be standing not riding |

## Inter-column motion deltas (row 1)
| from -> to | depth_delta | camera_motion_hint |
| s1_p1->s1_p2 | Neju enters (cast grows) | pan |
| s1_p2->s1_p3 | Azhagi enters (cast grows) | pan |
| s1_p3->s1_p4 | char_03: 3->4 (+1 recede) | push_in |

## Inter-column motion deltas (row 2)
| from -> to | depth_delta | camera_motion_hint |
| s1_p5->s1_p6 | char_02: 2->3 (+1 recede) | push_in |
| s1_p6->s1_p7 | char_02: 3->2 (-1 approach) | pull_out |
| s1_p7->s1_p8 | char_01: 2->1 (-1 approach) | pull_out |

## Scene-end handoff -> scene end
on_screen: [char_01, char_02]
positions: {char_01:[0.5,0.3], char_02:[0.5,0.55]}
facing: {char_01: forward, char_02: forward}
mood: joyful
transition: hard_cut