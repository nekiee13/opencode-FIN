# ------------------------
# utils\__init__.py
# ------------------------
"""
FIN utilities package.

Purpose
-------
Shared helper utilities and compatibility layers used across FIN, including:
- Optional dependency detection
- Small mathematical or data utilities
- Backward-compatibility helpers

Design
------
- Side-effect free on import.
- Utilities are imported explicitly by consumers.
"""

from __future__ import annotations

__all__: list[str] = []
