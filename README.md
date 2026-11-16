# ai-excited-01 — Jellyfish Over the Terraces

[![make.fun · ai-excited-01](https://make.fun/badge/ai-excited-01.svg)](https://make.fun/bounty/ai-excited-01?utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01)
[![rank](https://make.fun/badge/ai-excited-01/wizzy-bounty/ai-excited-01/rank.svg)](https://make.fun/bounty/ai-excited-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01)
[![reward](https://make.fun/badge/ai-excited-01/wizzy-bounty/ai-excited-01/reward.svg)](https://make.fun/bounty/ai-excited-01?utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01)

Our entry for make.fun's **ai-excited-01** — "Make the AI judge excited".
The bounty lives at https://make.fun/bounty/ai-excited-01 and pays $250
across the top 20 places.

## What the judge sees

A single impossible sight: one enormous luminous jellyfish floating low
above flooded rice terraces at sunset. Its bell glows pink-violet
against a burning orange sky, ribs fanning from the apex, a wavy oral
skirt underneath, five thick oral arms and a curtain of fine tentacles
trailing down toward the water. The low sun hangs to the right, the
jellyfish's pink shimmer ripples across the terrace water, and far below
a tiny farmer with a conical hat stands beside three warm lanterns —
the human scale that makes the creature feel truly colossal.

The idea follows the pattern the leaderboard rewards: one colossal
subject in the wrong place, one hero silhouette that reads at a glance
(even at 300 px), a small human for scale, dramatic dusk light, and a
saturated palette. No text, no stock explosion, no generic action scene.

## How the picture is made

`main.py` is Python 3 standard library only — no Pillow, no network,
no clock, no randomness. A small scanline rasterizer paints the scene
into an RGB buffer in layers (dusk sky gradient, sun and halo, clouds,
mountain ridges, seven stacked flooded terraces, the jellyfish's glow,
bell, ribs, skirt, oral arms and tentacles, shimmer reflections, then
the farmer and lanterns) and a hand-rolled encoder writes the PNG.
Every value comes from fixed arithmetic, so two runs produce
byte-identical output.

## Run it

```sh
mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
```

That writes `out/entry.png`: 1024×1024 PNG, well under the 1 MiB cap.
