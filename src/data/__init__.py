# ------------------------
# data\__init__.py
# ------------------------
"""
FIN data package.

Purpose
-------
Marks the top-level `data/` directory as a Python package. This package is
intentionally lightweight and contains no import-time side effects.

Notes
-----
- No filesystem access on import.
- Subpackages (e.g., raw loaders, artifacts) are accessed explicitly.
"""

from __future__ import annotations

__all__: list[str] = []
