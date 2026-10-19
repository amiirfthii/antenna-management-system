#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Display-only status overrides from گزارش 1405.04.13.xlsx (no DB writes)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Set, Tuple

import pandas as pd

from app.services.repair_report_excel_import import (
    normalize_dataframe,
    norm,
    norm_lower,
    norm_serial,
    parse_date,
    parse_personal_id,
)

PACKAGING_ITEM = "بسته بندی"
DISPLAY_CONFIRMED_STATUS = "تایید"

_DEFAULT_EXCEL = Path(r"c:\Users\user\Desktop\antennaapp8\گزارش 1405.04.13.xlsx")

_keys_cache: Optional[Set[Tuple[str, Optional[int], str]]] = None
_serial_pid_cache: Optional[Set[Tuple[str, Optional[int]]]] = None


def _excel_path() -> Path:
    return _DEFAULT_EXCEL


def _load_packaging_confirmed_keys() -> Tuple[Set[Tuple[str, Optional[int], str]], Set[Tuple[str, Optional[int]]]]:
    global _keys_cache, _serial_pid_cache
    if _keys_cache is not None and _serial_pid_cache is not None:
        return _keys_cache, _serial_pid_cache

    keys: Set[Tuple[str, Optional[int], str]] = set()
    serial_pid: Set[Tuple[str, Optional[int]]] = set()
    path = _excel_path()
    if path.exists() and not path.name.startswith("~$"):
        df = normalize_dataframe(pd.read_excel(path, sheet_name="Aligned", engine="openpyxl"))
        for _, row in df.iterrows():
            if norm(row.get("item_name")) != PACKAGING_ITEM:
                continue
            if not parse_date(row.get("end_date")):
                continue
            serial = norm_serial(row.get("antenna_serial_no"))
            if not serial:
                continue
            pid = parse_personal_id(row.get("personal_id"))
            vendor = norm_lower(row.get("Supplier Vendor"))
            keys.add((serial, pid, vendor))
            serial_pid.add((serial, pid))

    _keys_cache = keys
    _serial_pid_cache = serial_pid
    return keys, serial_pid


def should_display_packaging_as_confirmed(
    *,
    item_name: Optional[str],
    antenna_serial_no: Optional[str],
    personal_id: Optional[int],
    manufacturer: Optional[str],
) -> bool:
    if norm(item_name) != PACKAGING_ITEM:
        return False
    serial = norm_serial(antenna_serial_no)
    if not serial:
        return False
    keys, serial_pid = _load_packaging_confirmed_keys()
    if not keys:
        return False
    pid = personal_id
    vendor = norm_lower(manufacturer)
    if (serial, pid, vendor) in keys:
        return True
    return (serial, pid) in serial_pid


def display_status_for_report(
    *,
    item_name: Optional[str],
    status: Optional[str],
    final_status: Optional[str],
    antenna_serial_no: Optional[str],
    personal_id: Optional[int],
    manufacturer: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    if should_display_packaging_as_confirmed(
        item_name=item_name,
        antenna_serial_no=antenna_serial_no,
        personal_id=personal_id,
        manufacturer=manufacturer,
    ):
        return DISPLAY_CONFIRMED_STATUS, DISPLAY_CONFIRMED_STATUS
    return status, final_status
