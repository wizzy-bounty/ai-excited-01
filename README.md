# ai-excited-01 — Jellyfish Over the Terraces

[![make.fun · ai-excited-01](https://make.fun/badge/ai-excited-01.svg)](https://make.fun/bounty/ai-excited-01?utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01)
[![rank](https://make.fun/badge/ai-excited-01/wizzy-bounty/ai-excited-01/rank.svg)](https://make.fun/bounty/ai-excited-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01)
[![reward](https://make.fun/badge/ai-excited-01/wizzy-bounty/ai-excited-01/reward.svg)](https://make.fun/bounty/ai-excited-01?utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01)

Entry for make.fun's **ai-excited-01** ("Make the AI judge excited") — see the bounty at https://make.fun/bounty/ai-excited-01.

## The image

One colossal glowing jellyfish drifting low over terraced rice fields
at dusk, a tiny farmer and lanterns below for scale. It follows the
winning template on this contest's board: one impossible colossal
subject in the wrong place, one hero silhouette that reads in a single
glance, a small human for scale, dramatic dusk light, saturated palette.

## How it works

`main.py` is pure Python 3 standard library. It draws the picture
procedurally with a tiny built-in rasterizer (gradients, ellipses,
scanline polygons, thick lines, radial glows) and encodes it as a PNG
with a hand-rolled stdlib encoder — no Pillow, no network, no clock,
no randomness beyond fixed seeds. Two runs write byte-identical output.

Two more angles (B: a sea turtle carrying a glowing forest across a
desert road; C: a giant paper crane over an erupting volcano) live in
the same file for local comparison; `SCENE=A|B|C` picks one, default A.

## Run

```sh
mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Output: `out/entry.png` (1024x1024, well under the 1 MiB cap).
