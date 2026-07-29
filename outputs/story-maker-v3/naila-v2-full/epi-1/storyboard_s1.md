# Scene s1 — Peaceful Morning & Distress
target_seconds: 75
cast: [char_01, char_03, char_04]
location_ref_id: loc_01

## Row 1 (LTX session 1)
| col | shot_id | duration_seconds | characters_present | depth_per_char | camera_angle | position_xy | looks_at | expression | mood | intent | facing | angle | spatial_relation | must_not_show |
| 1 | s1_p1 | 9 | [char_01,char_03,char_04] | {char_01:2,char_03:3,char_04:4} | wide | {char_01:[0.5,0.5],char_03:[0.3,0.6],char_04:[0.7,0.3]} | none | peaceful | serene | establish | forward | 0deg | char_01 sleeping on wooden swing under banyan tree, char_03 lying on grass, char_04 perched on branch | no father, no horse |
| 2 | s1_p2 | 9 | [char_01] | {char_01:2} | medium | {char_01:[0.5,0.5]} | none | sleepy | quiet | rest | forward | 0deg | char_01 alone on swing frame close-up | no other characters |
| 3 | s1_p3 | 9 | [char_01] | {char_01:2} | close_up | {char_01:[0.5,0.5]} | none | tearful | distressed | stir | left | 5deg | char_01 stirring on wooden swing with tear forming in eye | no other characters |
| 4 | s1_p4 | 10 | [char_01,char_03] | {char_01:2,char_03:2} | medium | {char_01:[0.4,0.5],char_03:[0.7,0.6]} | char_01 | weeping | sad | cry | right | 0deg | char_01 crying on swing with char_03 standing up on grass looking concerned | no father |

## Row 2 (LTX session 2)
| col | shot_id | duration_seconds | characters_present | depth_per_char | camera_angle | position_xy | looks_at | expression | mood | intent | facing | angle | spatial_relation | must_not_show |
| 1 | s1_p5 | 9 | [char_03,char_04] | {char_03:2,char_04:3} | medium | {char_03:[0.4,0.6],char_04:[0.6,0.3]} | char_01 | anxious | tense | notice | left | 0deg | char_03 and char_04 looking off-screen toward crying Naila | no Naila in frame |
| 2 | s1_p6 | 9 | [char_01,char_04] | {char_01:2,char_04:2} | medium | {char_01:[0.4,0.5],char_04:[0.6,0.4]} | char_04 | crying | emotional | react | right | 10deg | char_01 crying while char_04 perches closer on swing rope | no dog |
| 3 | s1_p7 | 10 | [char_01,char_03] | {char_01:2,char_03:2} | medium | {char_01:[0.4,0.5],char_03:[0.7,0.6]} | char_01 | crying | sorrowful | continue | left | 0deg | char_01 tears rolling down cheeks while char_03 barks softly | no father |
| 4 | s1_p8 | 10 | [char_01,char_03,char_04] | {char_01:2,char_03:3,char_04:4} | wide | {char_01:[0.5,0.5],char_03:[0.3,0.6],char_04:[0.7,0.3]} | char_01 | crying | helpless | seek_help | forward | 0deg | char_01 crying on swing under banyan tree with char_03 turning toward trail | no horse |

## Inter-column motion deltas (row 1)
| from -> to | depth_delta | camera_motion_hint |
| s1_p1->s1_p2 | char_01: 2->2 (hold) | push_in |
| s1_p2->s1_p3 | char_01: 2->2 (hold) | push_in |
| s1_p3->s1_p4 | char_01: 2->2 (hold) | static |

## Inter-column motion deltas (row 2)
| from -> to | depth_delta | camera_motion_hint |
| s1_p5->s1_p6 | char_04: 3->2 (-1 approach) | pan |
| s1_p6->s1_p7 | char_01: 2->2 (hold) | static |
| s1_p7->s1_p8 | char_03: 2->3 (+1 recede) | pull_out |

## Scene-end handoff -> scene s2
on_screen: [char_01, char_03, char_04]
positions: {char_01:[0.5,0.5], char_03:[0.3,0.6], char_04:[0.7,0.3]}
facing: {char_01: forward, char_03: right, char_04: left}
mood: helpless
transition: hard_cut
