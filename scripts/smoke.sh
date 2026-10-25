#!/usr/bin/env bash
# Golden end-to-end smoke table (LLM mocked). Prints message | care_type |
# urgency | question? | red_flag+source | pass/fail and exits non-zero on any fail.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python

exec "$PY" scripts/run_golden.py "$@"
