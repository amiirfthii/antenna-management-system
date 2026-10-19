#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Display-only dashboard figures from plan report 1405.04.13 (no DB writes)."""

from __future__ import annotations

from typing import Any, Dict, List

# Source: plan table shared by user (گزارش 1405.04.13)
_DISPLAY_ROWS: List[Dict[str, Any]] = [
    {
        "code": "x-pole",
        "label": "x-pole",
        "province_in": 49,
        "depreciated_in": 4270,
        "approved": 132,
        "exited": 132,
    },
    {
        "code": "2x-pole",
        "label": "2x-pole",
        "province_in": 26,
        "depreciated_in": 3071,
        "approved": 373,
        "exited": 373,
    },
    {
        "code": "3x-pole",
        "label": "3x-pole",
        "province_in": 97,
        "depreciated_in": 381,
        "approved": 295,
        "exited": 295,
    },
    {
        "code": "4x-pole",
        "label": "4x-pole",
        "province_in": 29,
        "depreciated_in": 222,
        "approved": 10,
        "exited": 10,
    },
    {
        "code": "5x-pole",
        "label": "5x-pole",
        "province_in": 829,
        "depreciated_in": 164,
        "approved": 614,
        "exited": 614,
    },
    {
        "code": "8x-pole",
        "label": "8x-pole",
        "province_in": 333,
        "depreciated_in": 47,
        "approved": 259,
        "exited": 259,
    },
    {
        "code": "TDD",
        "label": "TDD",
        "province_in": 482,
        "depreciated_in": 106,
        "approved": 326,
        "exited": 326,
    },
]


def _clone_row(row: Dict[str, Any]) -> Dict[str, Any]:
    approved = int(row["approved"])
    exited = int(row["exited"])
    province_in = int(row["province_in"])
    depreciated_in = int(row["depreciated_in"])
    return {
        "code": row["code"],
        "label": row["label"],
        "approved": approved,
        "exited": exited,
        "province_in": province_in,
        "depreciated_in": depreciated_in,
        "in_center": max(0, approved + province_in + depreciated_in - exited),
        "total": approved + exited + province_in + depreciated_in,
        "display_only": True,
    }


def get_display_antenna_type_x_bars() -> List[Dict[str, Any]]:
    """وضعیت آنتن‌ها: approved = کل تعمیری، exited = SAP."""
    return [_clone_row(row) for row in _DISPLAY_ROWS]


def get_display_center_inventory_bars() -> List[Dict[str, Any]]:
    """موجودی مرکز: province_in = ورودی جدید از استان، depreciated_in = موجودی مستهلک."""
    return [
        {
            "code": row["code"],
            "label": row["label"],
            "province_in": int(row["province_in"]),
            "depreciated_in": int(row["depreciated_in"]),
            "total": int(row["province_in"]) + int(row["depreciated_in"]),
            "display_only": True,
        }
        for row in _DISPLAY_ROWS
    ]


def get_display_sap_pie_rows() -> List[Dict[str, Any]]:
    """خروجی SAP pie chart rows (same SAP totals as plan)."""
    return [
        {
            "code": row["code"],
            "label": row["label"],
            "exited": int(row["exited"]),
            "display_only": True,
        }
        for row in _DISPLAY_ROWS
        if int(row["exited"]) > 0
    ]
