# Scene s3 — The Alarm & Gallop to Rescue
target_seconds: 75
cast: [char_02, char_03, char_05, char_06]
location_ref_id: loc_01

## Row 1 (LTX session 1)
| col | shot_id | duration_seconds | characters_present | depth_per_char | camera_angle | position_xy | looks_at | expression | mood | intent | facing | angle | spatial_relation | must_not_show |
| 1 | s3_p1 | 9 | [char_02,char_05] | {char_02:2,char_05:3} | wide | {char_02:[0.4,0.5],char_05:[0.7,0.5]} | char_05 | calm | gentle | feed | right | 0deg | char_02 handing fresh sugarcane bundle to elephant char_05 near wooden enclosure | no dog, no horse |
| 2 | s3_p2 | 9 | [char_02,char_03,char_05] | {char_02:2,char_03:2,char_05:4} | medium | {char_02:[0.4,0.5],char_03:[0.2,0.6],char_05:[0.8,0.5]} | char_02 | startled | alert | arrive | right | 10deg | char_03 bursting out of treeline barking frantically and tugging char_02 trousers | no horse |
| 3 | s3_p3 | 9 | [char_02,char_03] | {char_02:2,char_03:2} | medium | {char_02:[0.5,0.5],char_03:[0.3,0.6]} | char_03 | concerned | serious | listen | left | 0deg | char_02 dropping sugarcane basket and bending down to listen to char_03 | no elephant |
| 4 | s3_p4 | 10 | [char_02,char_03,char_06] | {char_02:2,char_03:3,char_06:2} | wide | {char_02:[0.4,0.5],char_03:[0.2,0.6],char_06:[0.7,0.5]} | char_06 | resolute | urgent | prepare | right | 0deg | char_02 turning quickly toward saddled horse char_06 tied near paddock | no elephant |

## Row 2 (LTX session 2)
| col | shot_id | duration_seconds | characters_present | depth_per_char | camera_angle | position_xy | looks_at | expression | mood | intent | facing | angle | spatial_relation | must_not_show |
| 1 | s3_p5 | 9 | [char_02,char_06] | {char_02:2,char_06:2} | medium | {char_02:[0.5,0.4],char_06:[0.5,0.5]} | none | determined | focused | mount | right | 0deg | char_02 swinging leg over saddle mounting horse char_06 smoothly | no dog |
| 2 | s3_p6 | 9 | [char_02,char_03,char_06] | {char_02:2,char_03:3,char_06:2} | wide | {char_02:[0.5,0.4],char_03:[0.2,0.6],char_06:[0.5,0.5]} | char_03 | energetic | active | ride | right | 0deg | char_02 holding reins as horse char_06 starts galloping with char_03 running ahead | no elephant |
| 3 | s3_p7 | 10 | [char_02,char_03,char_06] | {char_02:2,char_03:3,char_06:2} | tracking | {char_02:[0.5,0.4],char_03:[0.2,0.6],char_06:[0.5,0.5]} | none | urgent | fast | gallop | right | 0deg | horse char_06 galloping briskly down dirt shelter path alongside running char_03 | no elephant |
| 4 | s3_p8 | 10 | [char_02,char_03,char_06] | {char_02:3,char_03:4,char_06:3} | wide | {char_02:[0.6,0.4],char_03:[0.3,0.6],char_06:[0.6,0.5]} | none | hopeful | heroic | approach | away | 0deg | char_02 riding horse char_06 through forest clearing toward banyan tree in distance | no elephant |

## Inter-column motion deltas (row 1)
| from -> to | depth_delta | camera_motion_hint |
| s3_p1->s3_p2 | char_03: 4->2 (-2 approach) | pan |
| s3_p2->s3_p3 | char_02: 2->2 (hold) | push_in |
| s3_p3->s3_p4 | char_06: 2->2 (hold) | pan |

## Inter-column motion deltas (row 2)
| from -> to | depth_delta | camera_motion_hint |
| s3_p5->s3_p6 | char_02: 2->2 (hold) | pull_out |
| s3_p6->s3_p7 | char_06: 2->2 (hold) | tracking_shot |
| s3_p7->s3_p8 | char_06: 2->3 (+1 recede) | push_in |

## Scene-end handoff -> scene s4
on_screen: [char_02, char_03, char_06]
positions: {char_02:[0.6,0.4], char_03:[0.3,0.6], char_06:[0.6,0.5]}
facing: {char_02: right, char_03: right, char_06: right}
mood: heroic
transition: hard_cut
