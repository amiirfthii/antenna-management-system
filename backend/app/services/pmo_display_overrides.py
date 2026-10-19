#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""In-memory PMO display overrides (cleared on server restart)."""

from __future__ import annotations

from typing import Any, Dict, List

PMO_NUMERIC_FIELDS = ("dep", "p1", "p2", "tot", "sap", "wait")

# {row_type: {dep, p1, p2, tot, sap, wait}}
_PMO_DISPLAY_OVERRIDES: Dict[str, Dict[str, int]] = {}


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def has_pmo_display_overrides() -> bool:
    return bool(_PMO_DISPLAY_OVERRIDES)


def clear_pmo_display_overrides() -> None:
    _PMO_DISPLAY_OVERRIDES.clear()


def set_pmo_display_overrides(rows: List[Dict[str, Any]], valid_types: set[str]) -> None:
    """Replace all in-memory overrides with admin-edited rows."""
    _PMO_DISPLAY_OVERRIDES.clear()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        row_type = (str(row.get("type")) or "").strip()
        if row_type not in valid_types:
            continue
        _PMO_DISPLAY_OVERRIDES[row_type] = {
            field: _safe_int(row.get(field)) for field in PMO_NUMERIC_FIELDS
        }


def apply_pmo_display_overrides(
    rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Apply in-memory overrides on top of DB-computed PMO rows."""
    if not _PMO_DISPLAY_OVERRIDES:
        return rows
    result: List[Dict[str, Any]] = []
    for row in rows:
        row_type = (row.get("type") or "").strip()
        override = _PMO_DISPLAY_OVERRIDES.get(row_type)
        if override is None:
            result.append(row)
            continue
        merged = {"type": row_type}
        merged.update(override)
        result.append(merged)
    return result
