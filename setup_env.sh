#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install --upgrade pip
python3 -m pip install poetry pre-commit

poetry install --no-interaction
pre-commit install

echo "Copy .env.example to .env and set CLOUDFLARE_TOKEN before running the app."
