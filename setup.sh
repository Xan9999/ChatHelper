#!/usr/bin/env bash
# One-command setup (macOS / Linux): creates a venv and installs the tool.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -e .
echo
echo "Installed. Next:"
echo "  source .venv/bin/activate"
echo "  chathelper init"
echo "  chathelper ingest https://your-site.com --collection mysite"
echo "  chathelper serve --collection mysite"
