# PKL Labels — raw video2robot captures

After watching each MP4 in `vinod_workspace/videos/pkl_previews/`, fill in the fields below.
Pick up to 3 candidates for the demo (mark with `pick: yes`). The demo is on a gantry, so motions
with large root translation are effectively unusable — they will fight the tether.

Filled-in entries feed directly into the next step (`pkl_29_to_23.py` -> `kim_workspace/movements/`).

---

## `2026-03-12_07-07-09.pkl` (1589 frames, 53.0 s)

- auto-read: root travel 1.3x1.4 m, legs walking, torso active, both arms active
- what you see: <!-- e.g. "Full dance routine with spin and arm flourishes" -->
- suggested hero name: <!-- e.g. "dance_full" -->
- pick: <!-- yes / no -->
- notes: <!-- e.g. "Too long, could trim 10-20 s window" -->

## `2026-03-12_07-12-12.pkl` (137 frames, 4.6 s)

- auto-read: root travel 3.2x2.6 m, pure walking, quiet arms
- what you see:
- suggested hero name:
- pick: <!-- likely no — too much locomotion -->
- notes:

## `2026-03-12_07-13-37.pkl` (251 frames, 8.4 s)

- auto-read: root travel 6.0x3.2 m, pure walking, quiet arms
- what you see:
- suggested hero name:
- pick: <!-- likely no — too much locomotion -->
- notes:

## `2026-03-12_07-15-35.pkl` (1520 frames, 50.7 s) -- strong candidate

- auto-read: root travel 0.3x0.6 m, expressive arms + torso, mostly in-place
- what you see:
- suggested hero name: <!-- e.g. "iron_man_pose" -->
- pick:
- notes: <!-- could trim a 10-15 s signature window -->

## `2026-03-12_07-17-04.pkl` (459 frames, 15.3 s) -- strong candidate

- auto-read: root travel 0.2x0.1 m, expressive arms + torso, in-place
- what you see:
- suggested hero name: <!-- e.g. "dance_pose" -->
- pick:
- notes:

---

## Final picks (up to 3)

1. <source-pkl> -> <canonical_hero_name>_kinematics.pkl
2.
3.

## HERO_REGISTRY additions

For each picked motion, add to `vinod_workspace/persona_brain.py` HERO_REGISTRY:

```python
"<hero_name>": {
    "keywords": ["..."],
    "pkl": "kim_workspace/movements/<hero_name>_kinematics.pkl",
    "description": "...",
},
```
