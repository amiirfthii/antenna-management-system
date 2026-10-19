#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import a contiguous numeric serial range into repairs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import models
from app.services.no_serial_antenna import consume_no_serial_unit
from app.services.serial_uniqueness import find_repair_by_serial, normalize_serial, serial_key


MAX_RANGE_COUNT = 500


def expand_serial_range(start: str, end: str, *, max_count: int = MAX_RANGE_COUNT) -> List[str]:
    start_s = normalize_serial(start)
    end_s = normalize_serial(end)
    if not start_s or not end_s:
        raise ValueError("سریال شروع و پایان را وارد کنید.")
    if not start_s.isdigit() or not end_s.isdigit():
        raise ValueError("بازه سریال باید عددی باشد (مثلاً 1000 تا 1010).")

    a = int(start_s)
    b = int(end_s)
    if b < a:
        raise ValueError("سریال پایان باید بزرگ‌تر یا مساوی سریال شروع باشد.")

    count = b - a + 1
    if count > max_count:
        raise ValueError(f"حداکثر {max_count} سریال در یک بازه مجاز است (درخواست: {count}).")

    # Keep zero-padding when the start serial is zero-padded.
    pad = len(start_s) if start_s.startswith("0") and len(start_s) > 1 else 0
    serials: List[str] = []
    for n in range(a, b + 1):
        s = str(n)
        if pad:
            s = s.zfill(pad)
        serials.append(s)
    return serials


def import_serial_range(
    db: Session,
    *,
    serial_from: str,
    serial_to: str,
    vendor: str,
    antenna_type: str,
    antenna_entry_type: str,
    item_code: str,
    no_serial_category: str,
    entry_date: Optional[str] = None,
) -> Dict[str, Any]:
    vendor = (vendor or "").strip()
    antenna_type = (antenna_type or "").strip()
    antenna_entry_type = (antenna_entry_type or "").strip()
    item_code = (item_code or "").strip()
    no_serial_category = (no_serial_category or "").strip()

    if not vendor or not antenna_type:
        return {
            "total": 0,
            "imported": 0,
            "failed": 0,
            "errors": ["وندور و نوع آنتن الزامی است."],
            "imported_rows": [],
        }
    if not item_code:
        return {
            "total": 0,
            "imported": 0,
            "failed": 0,
            "errors": ["آیتم‌کد را انتخاب کنید. بدون آیتم‌کد سریال ثبت نمی‌شود."],
            "imported_rows": [],
        }
    if not no_serial_category:
        return {
            "total": 0,
            "imported": 0,
            "failed": 0,
            "errors": ["دسته (استان یا مستهلک) را انتخاب کنید. بدون دسته سریال ثبت نمی‌شود."],
            "imported_rows": [],
        }
    if antenna_entry_type not in ("ورودی_تعمیر", "ورودی_خروجی"):
        return {
            "total": 0,
            "imported": 0,
            "failed": 0,
            "errors": ["نوع ورودی نامعتبر است."],
            "imported_rows": [],
        }

    try:
        serials = expand_serial_range(serial_from, serial_to)
    except ValueError as exc:
        return {
            "total": 0,
            "imported": 0,
            "failed": 0,
            "errors": [str(exc)],
            "imported_rows": [],
        }

    total = imported = failed = 0
    errors: List[str] = []
    imported_rows: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for serial in serials:
        total += 1
        serial = normalize_serial(serial)
        key = serial_key(serial)
        if not serial:
            failed += 1
            errors.append("سریال خالی در بازه نادیده گرفته شد.")
            continue
        if key in seen:
            failed += 1
            errors.append(f"سریال {serial}: تکراری داخل بازه.")
            continue
        seen.add(key)

        existing = find_repair_by_serial(db, serial)
        if existing:
            failed += 1
            errors.append(
                f"سریال {serial}: قبلاً ثبت شده "
                f"(تعمیر {existing.repair_no}، وندور {existing.constructor or 'نامشخص'}، "
                f"نوع {existing.antenna_type or 'نامشخص'})."
            )
            continue

        try:
            with db.begin_nested():
                repair = models.Repair(
                    antenna_serial_no=serial,
                    antenna_type=antenna_type,
                    constructor=vendor,
                    antenna_entry_type=antenna_entry_type,
                    entry_date=entry_date,
                    item_code=item_code,
                    antenna_status="نامعلوم",
                    no_serial_category=no_serial_category,
                )
                db.add(repair)
                db.flush()
                used_category = consume_no_serial_unit(
                    db,
                    vendor=vendor,
                    antenna_type=antenna_type,
                    item_code=item_code,
                    category=no_serial_category,
                )
                repair.no_serial_category = used_category
            imported += 1
            imported_rows.append(
                {
                    "repair_no": repair.repair_no,
                    "serial": serial,
                    "vendor": vendor,
                    "antenna_type": antenna_type,
                    "item_code": item_code,
                    "entry_date": entry_date,
                    "category": used_category,
                }
            )
        except ValueError as exc:
            failed += 1
            errors.append(f"سریال {serial}: {exc}")
        except IntegrityError:
            failed += 1
            errors.append(f"سریال {serial}: تکراری است و قبلاً در سیستم ثبت شده.")
        except Exception as exc:
            failed += 1
            errors.append(f"سریال {serial}: خطای غیرمنتظره — {exc}")

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        return {
            "total": total,
            "imported": 0,
            "failed": total,
            "errors": [f"خطا در ذخیره نهایی: {exc}"],
            "imported_rows": [],
        }

    return {
        "total": total,
        "imported": imported,
        "failed": failed,
        "errors": errors[:300],
        "imported_rows": imported_rows[:200],
    }
