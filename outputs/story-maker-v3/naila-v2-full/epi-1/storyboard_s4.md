# Scene s4 — Relief & High On Shoulders
target_seconds: 75
cast: [char_01, char_02, char_03, char_04]
location_ref_id: loc_01

## Row 1 (LTX session 1)
| col | shot_id | duration_seconds | characters_present | depth_per_char | camera_angle | position_xy | looks_at | expression | mood | intent | facing | angle | spatial_relation | must_not_show |
| 1 | s4_p1 | 9 | [char_01,char_02,char_03,char_04] | {char_01:2,char_02:3,char_03:3,char_04:4} | wide | {char_01:[0.4,0.5],char_02:[0.7,0.4],char_03:[0.6,0.6],char_04:[0.3,0.3]} | char_01 | shouting | calling | call_out | left | 0deg | char_02 riding horse up to banyan tree swing and calling Naila's name | no dismounted rider |
| 2 | s4_p2 | 9 | [char_01] | {char_01:2} | close_up | {char_01:[0.5,0.5]} | none | wiping_tears | relieved | hear | right | 0deg | char_01 wiping tears from eyes hearing Father's warm voice | no other characters |
| 3 | s4_p3 | 9 | [char_01,char_02] | {char_01:2,char_02:2} | medium | {char_01:[0.4,0.5],char_02:[0.6,0.5]} | char_02 | smiling | happy | greet | right | 0deg | char_01 looking up smiling brightly as char_02 dismounts and approaches swing | no horse |
| 4 | s4_p4 | 10 | [char_01,char_02] | {char_01:2,char_02:2} | medium | {char_01:[0.5,0.4],char_02:[0.5,0.5]} | char_01 | joyful | tender | lift | forward | 0deg | char_02 lifting char_01 off swing under arms into air | no horse |

## Row 2 (LTX session 2)
| col | shot_id | duration_seconds | characters_present | depth_per_char | camera_angle | position_xy | looks_at | expression | mood | intent | facing | angle | spatial_relation | must_not_show |
| 1 | s4_p5 | 9 | [char_01,char_02] | {char_01:2,char_02:2} | medium | {char_01:[0.5,0.3],char_02:[0.5,0.5]} | none | cheerful | proud | shoulder_mount | forward | 0deg | char_02 placing char_01 securely onto his broad shoulders | no other characters |
| 2 | s4_p6 | 9 | [char_01,char_02,char_03] | {char_01:2,char_02:2,char_03:3} | low_angle | {char_01:[0.5,0.2],char_02:[0.5,0.5],char_03:[0.3,0.7]} | none | beaming | triumphant | celebrate | forward | -15deg | low angle shot of char_01 riding high on char_02 shoulders with char_03 wagging tail below | no crying |
| 3 | s4_p7 | 10 | [char_01,char_02,char_04] | {char_01:2,char_02:2,char_04:1} | medium | {char_01:[0.5,0.3],char_02:[0.5,0.5],char_04:[0.8,0.2]} | char_04 | laughing | delighted | view | right | 0deg | char_01 laughing on shoulders while char_04 flies in circles around her head | no tears |
| 4 | s4_p8 | 10 | [char_01,char_02,char_03,char_04] | {char_01:2,char_02:2,char_03:3,char_04:3} | wide | {char_01:[0.5,0.3],char_02:[0.5,0.6],char_03:[0.3,0.7],char_04:[0.7,0.2]} | none | radiant | blissful | panorama | forward | 0deg | wide cinematic panorama of char_01 high on char_02 shoulders surveying whole lush shelter | no sadness |

## Inter-column motion deltas (row 1)
| from -> to | depth_delta | camera_motion_hint |
| s4_p1->s4_p2 | char_01: 2->2 (hold) | push_in |
| s4_p2->s4_p3 | char_02: 3->2 (-1 approach) | pan |
| s4_p3->s4_p4 | char_01: 2->2 (hold) | static |

## Inter-column motion deltas (row 2)
| from -> to | depth_delta | camera_motion_hint |
| s4_p5->s4_p6 | char_01: 2->2 (hold) | low_angle_tilt |
| s4_p6->s4_p7 | char_04: 3->1 (-2 approach) | pan |
| s4_p7->s4_p8 | char_01: 2->2 (hold) | pull_out |

## Scene-end handoff -> scene s5
on_screen: [char_01, char_02, char_03, char_04]
positions: {char_01:[0.5,0.3], char_02:[0.5,0.6], char_03:[0.3,0.7], char_04:[0.7,0.2]}
facing: {char_01: forward, char_02: forward, char_03: forward, char_04: forward}
mood: blissful
transition: hard_cut
