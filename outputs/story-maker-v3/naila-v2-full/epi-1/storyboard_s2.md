# Scene s2 — Comfort Efforts & Heroic Dash
target_seconds: 75
cast: [char_01, char_03, char_04]
location_ref_id: loc_01

## Row 1 (LTX session 1)
| col | shot_id | duration_seconds | characters_present | depth_per_char | camera_angle | position_xy | looks_at | expression | mood | intent | facing | angle | spatial_relation | must_not_show |
| 1 | s2_p1 | 9 | [char_01,char_04] | {char_01:2,char_04:2} | medium | {char_01:[0.4,0.5],char_04:[0.6,0.4]} | char_01 | concerned | tense | comfort | left | 0deg | char_04 fluttering down to swing rope next to crying char_01 | no dog |
| 2 | s2_p2 | 9 | [char_01,char_03] | {char_01:2,char_03:2} | medium | {char_01:[0.4,0.5],char_03:[0.7,0.6]} | char_01 | urgent | earnest | cheer | left | 5deg | char_03 hopping up on hind legs barking gently to cheer char_01 | no parrot |
| 3 | s2_p3 | 9 | [char_01] | {char_01:2} | close_up | {char_01:[0.5,0.5]} | none | sobbing | sad | weep | forward | 0deg | char_01 sobbing with hands rubbing teary eyes on swing | no other characters |
| 4 | s2_p4 | 10 | [char_01,char_03,char_04] | {char_01:2,char_03:2,char_04:3} | wide | {char_01:[0.4,0.5],char_03:[0.6,0.6],char_04:[0.7,0.3]} | char_03 | crying | desperate | realize | right | 0deg | char_01 crying uncontrollably while char_03 looks toward forest path realizing help is needed | no father |

## Row 2 (LTX session 2)
| col | shot_id | duration_seconds | characters_present | depth_per_char | camera_angle | position_xy | looks_at | expression | mood | intent | facing | angle | spatial_relation | must_not_show |
| 1 | s2_p5 | 9 | [char_03,char_04] | {char_03:2,char_04:3} | medium | {char_03:[0.4,0.6],char_04:[0.6,0.3]} | char_04 | resolute | determined | signal | right | 0deg | char_03 barking firmly to char_04 before sprinting off | no Naila |
| 2 | s2_p6 | 9 | [char_03] | {char_03:2} | medium | {char_03:[0.5,0.6]} | none | focused | fast | sprint | right | 0deg | char_03 turning sharply and bounding toward forest path | no other characters |
| 3 | s2_p7 | 10 | [char_03] | {char_03:3} | wide | {char_03:[0.6,0.7]} | none | intense | urgent | run | away | 0deg | char_03 dashing at full speed down dirt trail through shelter pens | no Naila |
| 4 | s2_p8 | 10 | [char_01,char_04] | {char_01:2,char_04:3} | medium | {char_01:[0.4,0.5],char_04:[0.6,0.3]} | char_03 | weeping | hopeful | wait | right | 0deg | char_01 crying on swing as char_04 stays perched guarding her | no dog |

## Inter-column motion deltas (row 1)
| from -> to | depth_delta | camera_motion_hint |
| s2_p1->s2_p2 | char_03: 3->2 (-1 approach) | pan |
| s2_p2->s2_p3 | char_01: 2->2 (hold) | push_in |
| s2_p3->s2_p4 | char_01: 2->2 (hold) | pull_out |

## Inter-column motion deltas (row 2)
| from -> to | depth_delta | camera_motion_hint |
| s2_p5->s2_p6 | char_03: 2->2 (hold) | pan |
| s2_p6->s2_p7 | char_03: 2->3 (+1 recede) | push_in |
| s2_p7->s2_p8 | char_01: 2->2 (hold) | pan |

## Scene-end handoff -> scene s3
on_screen: [char_03]
positions: {char_03:[0.6,0.7]}
facing: {char_03: away}
mood: urgent
transition: hard_cut
