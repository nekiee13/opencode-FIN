#!/usr/bin/env bash
set -euo pipefail
cd /repo

# Create clean venv (uv is preinstalled in this image)
rm -rf .venv
uv venv .venv
source .venv/bin/activate

# Minimal deps required by the requested tests + ruff
uv pip install -U pytest pandas numpy ruff

# Run the exact requested test set (use PYTHONPATH because repo is not package-installable)
PYTHONPATH=/repo python3 -m pytest tests/test_tda_module_contract.py -q
PYTHONPATH=/repo python3 -m pytest tests/test_compat_capability_bridge.py -q
PYTHONPATH=/repo python3 -m pytest tests/test_svl_indicators_unit.py tests/test_tda_indicators_unit.py -q
PYTHONPATH=/repo python3 -m pytest tests/test_tda_export_partial_degradation.py -q
PYTHONPATH=/repo python3 -m pytest tests/test_part3_structural_exporters_acceptance.py -q --run-cpi
PYTHONPATH=/repo python3 -m pytest tests/test_compat_import_hygiene.py tests/test_compat_thinness_shape.py -q

python3 -m ruff check src compat scripts tests || true
