# ------------------------
# config\__init__.py
# ------------------------
"""
FIN config package.

Purpose
-------
Mark the top-level `config/` directory as a Python package so that any future
configuration helpers (if added) can be imported consistently.

Design
------
- Side-effect free on import.
- Does not read or write configuration files.
"""

from __future__ import annotations

__all__: list[str] = []
