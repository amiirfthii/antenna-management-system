#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Normalize Jalali date strings to YYYY/MM/DD (slash separators)."""

from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Query
from sqlalchemy.sql.elements import ColumnElement

_JALALI_DATE_TIME = re.compile(
    r"^(\d{4})[./](\d{1,2})[./](\d{1,2})(?:\s+(\d{1,2}:\d{2}(?::\d{2})?))?$"
)
_PERSIAN_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)


def to_latin_digits(value: str) -> str:
    return value.translate(_PERSIAN_DIGITS)


def normalize_jalali_date_string(value: Any) -> Optional[str]:
    """Convert dot-separated Jalali dates to slash format with zero-padded month/day."""
    if value is None:
        return None
    s = to_latin_digits(str(value).strip())
    if not s:
        return s

    match = _JALALI_DATE_TIME.match(s)
    if match:
        year, month, day, time_part = match.groups()
        normalized = f"{year}/{month.zfill(2)}/{day.zfill(2)}"
        if time_part:
            normalized = f"{normalized} {time_part}"
        return normalized

    if re.match(r"^\d{4}\.", s):
        date_part, _, remainder = s.partition(" ")
        parts = date_part.replace(".", "/").split("/")
        if len(parts) == 3:
            date_part = f"{parts[0]}/{parts[1].zfill(2)}/{parts[2].zfill(2)}"
        else:
            date_part = date_part.replace(".", "/")
        return f"{date_part} {remainder}".strip() if remainder else date_part

    return s


def jalali_end_date_upper_bound(value: Optional[str]) -> Optional[str]:
    """Extend date-only end filters to include records with time on that day."""
    if not value:
        return value
    s = str(value).strip()
    if len(s) <= 10 and " " not in s:
        return f"{s} 23:59:59"
    return s


def normalized_jalali_date_sql(column: ColumnElement) -> ColumnElement:
    """SQL expression: legacy dot separators become slashes before compare."""
    return func.replace(column, ".", "/")


def apply_jalali_date_range_filter(
    query: Query,
    column: ColumnElement,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Query:
    """Filter VARCHAR Jalali dates, tolerating legacy '.' stored values."""
    expr = normalized_jalali_date_sql(column)

    if start_date:
        start_date = normalize_jalali_date_string(start_date)
    if end_date:
        end_date = normalize_jalali_date_string(end_date)
        end_date = jalali_end_date_upper_bound(end_date)

    if start_date and end_date:
        return query.filter(expr >= start_date, expr <= end_date)
    if start_date:
        return query.filter(expr >= start_date)
    if end_date:
        return query.filter(expr <= end_date)
    return query
