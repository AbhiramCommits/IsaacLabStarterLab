#!/usr/bin/env bash
# Install the lab into Isaac Sim's bundled Python without Docker.
#
# Run from the repository root inside an Isaac Sim 4.5 container/pod:
#
#   bash scripts/setup_isaac_nodocker.sh
#   LAB_BACKEND=isaac LAB_BRIDGE=localbus lab-episode --seed 7 \
#       --backend isaac --bridge localbus --out artifacts/episodes/gpu_seed_7
#
# The --no-deps flags are deliberate: usd-core and numpy from
# requirements.lock.txt would replace Isaac Sim's own pxr/numpy and break the
# Omniverse runtime. Isaac Sim already provides both.
set -euo pipefail

PY="${ISAAC_PYTHON:-/isaac-sim/python.sh}"

"$PY" -m pip install --no-cache-dir --no-deps pillow==12.0.0 PyYAML==6.0.3
"$PY" -m pip install --no-cache-dir --no-deps -e .

"$PY" - <<'PYCODE'
import numpy
import pxr
print(f"numpy {numpy.__version__}; pxr {pxr.__file__}")
PYCODE
