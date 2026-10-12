#!/usr/bin/env bash
# One-time setup on Linux / macOS: creates a virtual environment and installs dependencies.
set -e
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
echo "[setup] installing CPU-only PyTorch..."
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
echo "[setup] installing project requirements..."
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
echo "[setup] done. Next: ./run_demo.sh   (or see README.md)"
