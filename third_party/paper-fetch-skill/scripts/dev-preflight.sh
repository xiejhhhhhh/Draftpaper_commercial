#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/dev-preflight.sh [--fast] [--skip-integration] [--skip-devtools] [--skip-typecheck]

Runs the local preflight gate:
  - ruff
  - contract-layer mypy
  - unit tests
  - devtools tests
  - extraction-rules validation
  - integration tests

Options:
  --fast              Run ruff, mypy, and unit tests only.
  --skip-integration Skip integration tests.
  --skip-devtools    Skip tests/devtools.
  --skip-typecheck   Skip mypy.
  -h, --help         Show this help.
USAGE
}

run_devtools=1
run_integration=1
run_typecheck=1

while (($#)); do
  case "$1" in
    --fast)
      run_devtools=0
      run_integration=0
      ;;
    --skip-devtools)
      run_devtools=0
      ;;
    --skip-integration)
      run_integration=0
      ;;
    --skip-typecheck)
      run_typecheck=0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

export PYTHONPATH="${PYTHONPATH:-src}"

python3 -m ruff check .

if [[ "$run_typecheck" == "1" ]]; then
  PYTHONPATH=src python3 -m mypy
fi

PYTHONPATH=src python3 -m pytest tests/unit -q

if [[ "$run_devtools" == "1" ]]; then
  PYTHONPATH=src python3 -m pytest tests/devtools -q
fi

python3 scripts/validate_extraction_rules.py

if [[ "$run_integration" == "1" ]]; then
  PYTHONPATH=src python3 -m pytest tests/integration -q
fi
