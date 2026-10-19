#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Central serial-number normalization and duplicate checks for repairs."""

from __future__ import annotations

import re
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from app.db import models


def normalize_serial(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        return text[:-2]
    return text


def serial_key(value: Any) -> str:
    return normalize_serial(value).lower()


def find_repair_by_serial(
    db: Session,
    serial: Any,
    *,
    exclude_repair_no: Optional[int] = None,
) -> Optional[models.Repair]:
    normalized = normalize_serial(serial)
    if not normalized:
        return None

    query = db.query(models.Repair).filter(models.Repair.antenna_serial_no == normalized)
    if exclude_repair_no is not None:
        query = query.filter(models.Repair.repair_no != exclude_repair_no)
    exact = query.first()
    if exact:
        return exact

    target = serial_key(normalized)
    for repair in db.query(models.Repair).all():
        if exclude_repair_no is not None and repair.repair_no == exclude_repair_no:
            continue
        if serial_key(repair.antenna_serial_no) == target:
            return repair
    return None


def find_all_repairs_by_serial(db: Session, serial: Any) -> List[models.Repair]:
    normalized = normalize_serial(serial)
    if not normalized:
        return []

    target = serial_key(normalized)
    matches: List[models.Repair] = []
    seen: set[int] = set()
    for repair in db.query(models.Repair).all():
        if repair.repair_no in seen:
            continue
        if repair.antenna_serial_no == normalized or serial_key(repair.antenna_serial_no) == target:
            matches.append(repair)
            seen.add(repair.repair_no)
    matches.sort(key=lambda row: row.repair_no or 0)
    return matches


def duplicate_serial_message(existing: models.Repair, *, prefix: str = "") -> str:
    lead = f"{prefix}: " if prefix else ""
    return (
        f"{lead}سریال {existing.antenna_serial_no} قبلاً ثبت شده "
        f"(تعمیر {existing.repair_no}، وندور {existing.constructor or 'نامشخص'})"
    )


def assert_serial_unique_for_create(
    db: Session,
    serial: Any,
    *,
    allow_re_registration: bool = False,
    prefix: str = "",
) -> Optional[str]:
    existing = find_repair_by_serial(db, serial)
    if not existing:
        return None
    if allow_re_registration:
        return None
    return duplicate_serial_message(existing, prefix=prefix)


def assert_serial_unique_for_update(
    db: Session,
    serial: Any,
    *,
    repair_no: int,
    prefix: str = "",
) -> Optional[str]:
    existing = find_repair_by_serial(db, serial, exclude_repair_no=repair_no)
    if not existing:
        return None
    return duplicate_serial_message(existing, prefix=prefix)
