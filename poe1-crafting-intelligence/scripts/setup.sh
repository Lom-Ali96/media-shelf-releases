#!/usr/bin/env bash
# Linux/macOS equivalent of setup.ps1
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install -q -e 'backend[dev]'
.venv/bin/python -m poeci.knowledge.importer
