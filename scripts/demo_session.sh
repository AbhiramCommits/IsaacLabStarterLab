#!/usr/bin/env bash
# Two-minute narrated terminal session used by the walkthrough recording.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f .venv/bin/activate ]; then
  # The recording is often launched from a non-interactive shell; make the
  # console scripts available without requiring the caller to activate first.
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
mkdir -p demo/frames

banner() { printf '\n== %s ==\n' "$1"; }

banner "00:00 IsaacLabStarterLab — version and scope"
python -c "import isaac_starter_lab; print('isaac_starter_lab', isaac_starter_lab.__version__)"
python -c "from pxr import Usd; print('OpenUSD', Usd.GetVersion())"

banner "00:20 Environment self-check"
labcheck env | tail -4

banner "00:40 Deterministic OpenUSD scene"
lab-scene --seed 7 --out artifacts/scene_seed7.usda --render demo/frames/scene_seed7.png --force | tail -8

banner "01:05 Perception -> controller episode"
lab-episode --seed 7 --backend kinematic --bridge localbus --out artifacts/episodes/seed_7
cp artifacts/episodes/seed_7/frame_000.png demo/frames/episode_seed7_start.png
cp artifacts/episodes/seed_7/frame_final.png demo/frames/episode_seed7_final.png

banner "01:30 Perception evaluation across 200 DR seeds"
lab-eval perception | tail -5

banner "01:55 Episode sweep"
lab-eval episodes --seeds 0-9 --out results/walkthrough_episode_sweep.json | tail -5
cp datasets/dr/images/seed_0000.png demo/frames/dr_seed_0000.png

banner "02:15 Grade every artifact"
labcheck all | tail -6

banner "02:30 Done"
printf 'Artifacts: artifacts/, datasets/dr/manifest.json, results/\n'
