#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Duplicate detection for no-serial antenna records."""

from __future__ import annotations

from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.core.jalali_dates import normalize_jalali_date_string
from app.db import models


def norm_created_date(value: Optional[str]) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    normalized = normalize_jalali_date_string(text)
    return normalized if normalized is not None else text


def no_serial_row_key(
    vendor: str,
    antenna_type: str,
    item_code: str,
    category: str,
    province: str,
    quantity: int,
    created_date: str = "",
) -> Tuple[str, str, str, str, str, int, str]:
    return (
        (vendor or "").strip().lower(),
        (antenna_type or "").strip().lower(),
        (item_code or "").strip().lower(),
        (category or "").strip().lower(),
        (province or "").strip().lower(),
        int(quantity),
        norm_created_date(created_date),
    )


def find_duplicate_no_serial(
    db: Session,
    vendor: str,
    antenna_type: str,
    item_code: str,
    category: str,
    province: str,
    quantity: int,
    created_date: str = "",
    exclude_id: Optional[int] = None,
) -> Optional[models.NoSerialAntenna]:
    target = no_serial_row_key(
        vendor, antenna_type, item_code, category, province, quantity, created_date
    )
    for row in db.query(models.NoSerialAntenna).all():
        if exclude_id is not None and row.id == exclude_id:
            continue
        if no_serial_row_key(
            row.vendor,
            row.antenna_type,
            row.item_code,
            row.category,
            row.province or "",
            row.quantity,
            row.created_date or "",
        ) == target:
            return row
    return None


DUPLICATE_MESSAGE = "رکورد تکراری است"


def format_row_summary(
    vendor: str,
    antenna_type: str,
    item_code: str,
    category: str,
    province: str,
    quantity: int,
    created_date: str = "",
) -> str:
    return (
        f"وندور={vendor}، نوع={antenna_type}، کد={item_code}، "
        f"دسته={category}، استان={province or '—'}، "
        f"تعداد={quantity}، تاریخ={created_date or '—'}"
    )


def duplicate_message(match_label: str, **fields: object) -> str:
    summary = format_row_summary(
        str(fields.get("vendor", "")),
        str(fields.get("antenna_type", "")),
        str(fields.get("item_code", "")),
        str(fields.get("category", "")),
        str(fields.get("province", "")),
        int(fields.get("quantity", 0) or 0),
        str(fields.get("created_date", "") or ""),
    )
    return f"رکورد تکراری — مطابق {match_label} ({summary})"
