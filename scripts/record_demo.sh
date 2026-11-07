#!/usr/bin/env bash
# Record the walkthrough terminal session.
#
# If asciinema is installed the cast is written to demo/walkthrough.cast.
# Otherwise the standard `script` utility captures the same session to
# demo/walkthrough.log (macOS and Linux have different flag spellings).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p demo/frames

if command -v asciinema >/dev/null 2>&1; then
  asciinema rec --overwrite --command "bash scripts/demo_session.sh" demo/walkthrough.cast
  echo "wrote demo/walkthrough.cast"
elif [ "$(uname -s)" = "Darwin" ]; then
  script -q demo/walkthrough.log bash scripts/demo_session.sh
  echo "wrote demo/walkthrough.log (asciinema not installed)"
else
  script -q -c "bash scripts/demo_session.sh" demo/walkthrough.log
  echo "wrote demo/walkthrough.log (asciinema not installed)"
fi

echo "frames:"
find demo/frames -maxdepth 1 -type f -name '*.png' -print | sort
