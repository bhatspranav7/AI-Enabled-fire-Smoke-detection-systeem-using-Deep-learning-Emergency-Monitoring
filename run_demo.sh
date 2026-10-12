#!/usr/bin/env bash
# Starts backend+dashboard, sensor simulator and live inference. Ctrl-C stops everything.
# Usage: ./run_demo.sh                 -> webcam
#        ./run_demo.sh demo_media/images   -> sample images
#        ./run_demo.sh video.mp4
cd "$(dirname "$0")"
[ -d .venv ] || { echo "Run ./setup.sh first"; exit 1; }
# shellcheck disable=SC1091
source .venv/bin/activate
SRCARG=()
[ -n "$1" ] && SRCARG=(--source "$1")
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000 &
B=$!
sleep 4
python iot/sensor_simulator.py < /dev/null &
S=$!
trap 'kill $B $S 2>/dev/null' EXIT
( command -v xdg-open >/dev/null && xdg-open http://127.0.0.1:8000/ ) || ( command -v open >/dev/null && open http://127.0.0.1:8000/ ) || true
python inference/run_live.py "${SRCARG[@]}"
