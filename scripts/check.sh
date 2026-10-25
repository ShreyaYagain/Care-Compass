#!/usr/bin/env bash
# Local CI-equivalent: pytest, golden scenarios (LLM mocked), secret scan.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python

echo "== 1/3 pytest =="
"$PY" -m pytest -q

echo
echo "== 2/3 golden scenarios (LLM mocked) =="
"$PY" scripts/run_golden.py

echo
echo "== 3/3 secret scan =="
"$PY" scripts/scan_secrets.py

echo
echo "All checks passed."
