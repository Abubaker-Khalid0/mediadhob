#!/usr/bin/env bash
# Install into a project-local environment; no sudo or shell-profile changes.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

PYTHON_CMD=""
for candidate in python3 python python3.13 python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
        PYTHON_CMD="$candidate"
        break
    fi
done
if [ -z "$PYTHON_CMD" ]; then
    echo "Python 3.11+ is required: https://www.python.org/downloads/" >&2
    exit 1
fi
if [ ! -x .venv/bin/python ]; then
    "$PYTHON_CMD" -m venv .venv
fi
.venv/bin/python -c 'import sys; sys.exit(sys.version_info < (3, 11))'
.venv/bin/python -m pip install .

for program in ffmpeg ffprobe; do
    if ! command -v "$program" >/dev/null 2>&1; then
        echo "Warning: $program is missing. Install FFmpeg and add it to PATH."
    fi
done
printf '\nInstalled. Run from this directory:\n  .venv/bin/mediadhob\n'
echo "Or activate with: source .venv/bin/activate"
echo "For local transcription: .venv/bin/python -m pip install '.[captions]'"
