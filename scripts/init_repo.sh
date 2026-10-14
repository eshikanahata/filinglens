#!/usr/bin/env bash
# One-time repository setup. Run from the project root.
set -euo pipefail
git init
dvc init
git add .
git commit -m "Initial project scaffold (phase 1)"
echo "Next: cp .env.example .env, edit it, then 'dvc repro'."
