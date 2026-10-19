#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply packaging Excel on antenna status-change screen.

Excel layout (per column), same as serial import:
  row 1: packaging date (Jalali)
  row 2: vendor
  row 3: antenna type
  row 4+: serial numbers (packaged on warehouse floor)

Rules:
  1) Serials in the file whose DB vendor/type match Excel → status «تایید»
     (packaging date stored in antenna_admin_check_date)
  2) Mismatches / missing serials → collected as errors (no status change)
  3) Every other repair (serial NOT listed in the Excel) → status «خروج»
     with exit_date = 1405/01/01
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.core.jalali_dates import normalize_jalali_date_string
from app.db import models
from app.services.serial_uniqueness import (
    find_all_repairs_by_serial,
    normalize_serial,
    serial_key,
)

STATUS_PACKAGED = "تایید"
STATUS_EXIT = "خروج"
DEFAULT_EXIT_DATE = "1405/01/01"


def _norm(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        return text[:-2]
    return text


def _norm_key(value: Any) -> str:
    return _norm(value).lower()


def _norm_type_key(value: Any) -> str:
    """Loose type key: lower, strip spaces/hyphens/dots (NTYPE ≈ N-Type)."""
    s = _norm_key(value)
    s = s.replace(" ", "").replace("-", "").replace("_", "").replace(".", "")
    return s


def _parse_packaging_date(value: Any) -> Optional[str]:
    raw = _norm(value)
    if not raw:
        return None
    if hasattr(value, "strftime") and not isinstance(value, str):
        try:
            raw = str(value)
        except Exception:
            pass
    normalized = normalize_jalali_date_string(raw)
    return normalized if normalized else raw


def _parse_columns(content: bytes) -> List[Dict[str, Any]]:
    wb = load_workbook(BytesIO(content), data_only=True)
    ws = wb.active
    max_col = ws.max_column or 0
    max_row = ws.max_row or 0
    columns: List[Dict[str, Any]] = []

    for col in range(1, max_col + 1):
        packaging_date = _parse_packaging_date(ws.cell(1, col).value)
        vendor = _norm(ws.cell(2, col).value)
        antenna_type = _norm(ws.cell(3, col).value)
        if not packaging_date and not vendor and not antenna_type:
            probe = [
                _norm(ws.cell(r, col).value)
                for r in range(4, min(max_row, 6) + 1)
            ]
            if not any(probe):
                continue

        serials: List[Tuple[int, str]] = []
        for row in range(4, max_row + 1):
            serial = _norm(ws.cell(row, col).value)
            if serial:
                serials.append((row, serial))

        columns.append(
            {
                "col": col,
                "packaging_date": packaging_date,
                "vendor": vendor,
                "antenna_type": antenna_type,
                "serials": serials,
            }
        )
    return columns


def _vendor_matches(db_vendor: str, excel_vendor: str) -> bool:
    return _norm_key(db_vendor) == _norm_key(excel_vendor)


def _type_matches(db_type: str, excel_type: str) -> bool:
    if _norm_key(db_type) == _norm_key(excel_type):
        return True
    return _norm_type_key(db_type) == _norm_type_key(excel_type)


def apply_packaging_excel(db: Session, content: bytes) -> Dict[str, Any]:
    try:
        columns = _parse_columns(content)
    except Exception as exc:
        return {
            "total_in_file": 0,
            "packaged": 0,
            "exited": 0,
            "failed": 0,
            "errors": [f"خواندن فایل اکسل ناموفق بود: {exc}"],
            "packaged_rows": [],
        }

    vendor_canon = {
        _norm_key(r.company_constructor): _norm(r.company_constructor)
        for r in db.query(models.AntennaConstructor).all()
        if _norm(r.company_constructor)
    }
    type_canon = {
        _norm_key(r.antenna_type): _norm(r.antenna_type)
        for r in db.query(models.AntennaType).all()
        if _norm(r.antenna_type)
    }
    # also index by hyphen-stripped type key
    type_loose = {_norm_type_key(k): v for k, v in type_canon.items()}

    total = packaged = failed = 0
    errors: List[str] = []
    packaged_rows: List[Dict[str, Any]] = []
    packaged_serials: Set[str] = set()
    seen_in_file: set[str] = set()

    for col_info in columns:
        col = col_info["col"]
        packaging_date = col_info["packaging_date"] or ""
        raw_vendor = col_info["vendor"]
        raw_type = col_info["antenna_type"]

        if not raw_vendor or not raw_type:
            for row_no, serial in col_info["serials"]:
                total += 1
                failed += 1
                errors.append(
                    f"ستون {col} ردیف {row_no} (سریال {serial}): وندور یا نوع آنتن خالی است"
                )
            if not col_info["serials"]:
                failed += 1
                errors.append(f"ستون {col}: وندور یا نوع آنتن خالی است")
            continue

        for row_no, serial in col_info["serials"]:
            total += 1
            serial = normalize_serial(serial)
            if not serial:
                failed += 1
                errors.append(f"ستون {col} ردیف {row_no}: سریال خالی است")
                continue

            serial_lookup = serial_key(serial)
            if serial_lookup in seen_in_file:
                failed += 1
                errors.append(
                    f"ستون {col} ردیف {row_no}: سریال تکراری در فایل ({serial})"
                )
                continue
            seen_in_file.add(serial_lookup)

            matches = find_all_repairs_by_serial(db, serial)
            if not matches:
                failed += 1
                errors.append(
                    f"ستون {col} ردیف {row_no}: سریال {serial} در سیستم یافت نشد"
                )
                continue
            if len(matches) > 1:
                repair_nos = ", ".join(str(item.repair_no) for item in matches)
                failed += 1
                errors.append(
                    f"ستون {col} ردیف {row_no}: سریال {serial} چند رکورد تکراری در سیستم دارد "
                    f"(شماره تعمیرها: {repair_nos})"
                )
                continue

            repair = matches[0]

            db_vendor = repair.constructor or ""
            db_type = repair.antenna_type or ""
            canon_vendor = vendor_canon.get(_norm_key(raw_vendor), "")
            canon_type = type_canon.get(_norm_key(raw_type)) or type_loose.get(
                _norm_type_key(raw_type), ""
            )
            matched = (
                _vendor_matches(db_vendor, raw_vendor)
                or (canon_vendor and _vendor_matches(db_vendor, canon_vendor))
            ) and (
                _type_matches(db_type, raw_type)
                or (canon_type and _type_matches(db_type, canon_type))
            )
            if not matched:
                failed += 1
                errors.append(
                    f"ستون {col} ردیف {row_no} (سریال {serial}): "
                    f"عدم تطبیق وندور/نوع — اکسل: {raw_vendor}/{raw_type} "
                    f"— سیستم: {db_vendor}/{db_type}"
                )
                continue

            repair.antenna_status = STATUS_PACKAGED
            if packaging_date:
                repair.antenna_admin_check_date = packaging_date
            packaged_serials.add(serial_lookup)
            packaged += 1
            packaged_rows.append(
                {
                    "repair_no": repair.repair_no,
                    "serial": serial,
                    "vendor": db_vendor,
                    "antenna_type": db_type,
                    "packaging_date": packaging_date,
                    "status": STATUS_PACKAGED,
                }
            )

    # Exit every antenna whose serial is NOT in the Excel file at all
    exited = 0
    all_repairs = db.query(models.Repair).all()
    for repair in all_repairs:
        serial_lookup = serial_key(repair.antenna_serial_no)
        if not serial_lookup:
            continue
        if serial_lookup in seen_in_file:
            continue
        repair.antenna_status = STATUS_EXIT
        repair.exit_date = DEFAULT_EXIT_DATE
        exited += 1

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        return {
            "total_in_file": total,
            "packaged": 0,
            "exited": 0,
            "failed": total,
            "errors": [f"خطا در ذخیره نهایی: {exc}"],
            "packaged_rows": [],
        }

    return {
        "total_in_file": total,
        "packaged": packaged,
        "exited": exited,
        "failed": failed,
        "errors": errors[:300],
        "packaged_rows": packaged_rows[:200],
    }
