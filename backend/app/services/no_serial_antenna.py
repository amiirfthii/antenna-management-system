#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from app.core.antenna_type_bucket import classify_antenna_x_bucket
from app.core.jalali_dates import normalize_jalali_date_string
from app.db import models
from app.schemas.province_antenna import CATEGORY_DEPRECIATED, CATEGORY_PROVINCE


def _norm_code(value: str) -> str:
    s = (value or "").strip().lower()
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    # tolerate optional leading M (M1000… vs 1000…)
    if s.startswith("m") and s[1:].isdigit():
        return s[1:]
    return s


def remaining_of(row) -> int:
    """Remaining stock. Falls back to original quantity if not set."""
    raw = getattr(row, "remaining_quantity", None)
    if raw is None:
        return max(0, int(getattr(row, "quantity", 0) or 0))
    return max(0, int(raw))


def is_tdd_label(*parts: str) -> bool:
    return any("tdd" in (part or "").lower() for part in parts)


def _is_tdd_stock_row(row: models.NoSerialAntenna) -> bool:
    """TDD inventory is stored as vendor=TDD and/or type containing TDD."""
    return is_tdd_label(row.vendor or "", row.antenna_type or "")


def _date_key(value: Optional[str]) -> str:
    normalized = normalize_jalali_date_string(value) if value else None
    if not normalized:
        return ""
    return str(normalized).strip().split()[0]


def _existed_by(row: models.NoSerialAntenna, as_of_date: Optional[str]) -> bool:
    """Stock cannot be consumed by a serial registered before that stock existed."""
    if not as_of_date:
        return True
    repair_key = _date_key(as_of_date)
    stock_key = _date_key(
        getattr(row, "created_date", None) or getattr(row, "entry_date", None) or ""
    )
    if not repair_key or not stock_key:
        return True
    return stock_key <= repair_key


def _fifo_key(row: models.NoSerialAntenna) -> int:
    return int(getattr(row, "id", 0) or 0)


def _pick_by_item_code(
    candidates: list[models.NoSerialAntenna],
    item_code: str,
    allow_item_code_fallback: bool,
) -> Optional[models.NoSerialAntenna]:
    if not candidates:
        return None
    ordered = sorted(candidates, key=_fifo_key)
    want_code = _norm_code(item_code)
    for candidate in ordered:
        if (candidate.item_code or "").strip() == item_code:
            return candidate
    for candidate in ordered:
        if _norm_code(candidate.item_code or "") == want_code:
            return candidate
    if allow_item_code_fallback:
        return ordered[0]
    return None


def _vendor_key(value: str) -> str:
    return (value or "").strip().lower()


def _select_stock_row(
    stock_rows: list[models.NoSerialAntenna],
    *,
    vendor: str,
    antenna_type: str,
    item_code: str,
    allow_item_code_fallback: bool,
    tdd_pool: bool = False,
    as_of_date: Optional[str] = None,
) -> Optional[models.NoSerialAntenna]:
    """Pick a stock row. Item-code is the key; antenna type labels may differ.

    Province Excel often stores types as buckets (e.g. 5x-pole) while the
    new-entry form uses the exact model (e.g. 5X-4.3-10-ER). Those are the
    same pool: consume oldest remaining first, and never take stock that was
    entered after the serial's registration date.
    """
    stock_rows = [row for row in stock_rows if _existed_by(row, as_of_date)]
    if tdd_pool:
        candidates = [row for row in stock_rows if _is_tdd_stock_row(row)]
        return _pick_by_item_code(candidates, item_code, allow_item_code_fallback=True)

    want_vendor = _vendor_key(vendor)
    want_type = (antenna_type or "").strip().lower()
    want_bucket = classify_antenna_x_bucket(antenna_type)

    same_vendor = [
        row for row in stock_rows if _vendor_key(row.vendor or "") == want_vendor
    ]
    exact_or_bucket: list[models.NoSerialAntenna] = []
    for row in same_vendor:
        row_type = (row.antenna_type or "").strip().lower()
        if row_type == want_type:
            exact_or_bucket.append(row)
            continue
        if want_bucket != "سایر" and classify_antenna_x_bucket(row.antenna_type or "") == want_bucket:
            exact_or_bucket.append(row)
    picked = _pick_by_item_code(
        exact_or_bucket, item_code, allow_item_code_fallback=False
    )
    if picked:
        return picked

    # Same vendor + item code, even if the stored type string differs.
    picked = _pick_by_item_code(
        same_vendor, item_code, allow_item_code_fallback=False
    )
    if picked:
        return picked

    # Item code in this category, regardless of vendor/type spelling.
    picked = _pick_by_item_code(
        stock_rows, item_code, allow_item_code_fallback=False
    )
    if picked:
        return picked

    if allow_item_code_fallback:
        return _pick_by_item_code(
            exact_or_bucket or same_vendor or stock_rows,
            item_code,
            allow_item_code_fallback=True,
        )
    return None


def _find_stock_row(
    db: Session,
    *,
    vendor: str,
    antenna_type: str,
    item_code: str,
    category: str,
    allow_item_code_fallback: bool,
    tdd_pool: bool = False,
) -> Optional[models.NoSerialAntenna]:
    stock_rows = (
        db.query(models.NoSerialAntenna)
        .filter(models.NoSerialAntenna.category == category)
        .order_by(models.NoSerialAntenna.id.asc())
        .all()
    )
    stock_rows = [row for row in stock_rows if remaining_of(row) > 0]
    return _select_stock_row(
        stock_rows,
        vendor=vendor,
        antenna_type=antenna_type,
        item_code=item_code,
        allow_item_code_fallback=allow_item_code_fallback,
        tdd_pool=tdd_pool,
    )


def refresh_remaining_from_repairs(db: Session) -> None:
    """Optional rebuild of remaining from historical serials.

    Live remaining is not recalculated this way: Excel/manual entry sets
    remaining = quantity, and each new serial decrements it.
    """
    rows = (
        db.query(models.NoSerialAntenna)
        .order_by(models.NoSerialAntenna.id.asc())
        .all()
    )
    for row in rows:
        row.remaining_quantity = max(0, int(row.quantity or 0))

    if not hasattr(models.Repair, "no_serial_category"):
        db.flush()
        return

    repairs = (
        db.query(models.Repair)
        .filter(
            models.Repair.item_code.isnot(None),
            models.Repair.item_code != "",
            models.Repair.no_serial_category.in_(
                [CATEGORY_PROVINCE, CATEGORY_DEPRECIATED]
            ),
        )
        .all()
    )
    repairs.sort(
        key=lambda r: (
            _date_key(getattr(r, "entry_date", None) or "") or "9999/99/99",
            int(getattr(r, "repair_no", 0) or 0),
        )
    )
    by_cat: dict[str, list[models.NoSerialAntenna]] = {
        CATEGORY_PROVINCE: [],
        CATEGORY_DEPRECIATED: [],
    }
    for row in rows:
        cat = (row.category or "").strip()
        if cat in by_cat:
            by_cat[cat].append(row)

    for repair in repairs:
        cat = (repair.no_serial_category or "").strip()
        if cat not in by_cat:
            continue
        available = [row for row in by_cat[cat] if remaining_of(row) > 0]
        picked = _select_stock_row(
            available,
            vendor=repair.constructor or "",
            antenna_type=repair.antenna_type or "",
            item_code=repair.item_code or "",
            allow_item_code_fallback=False,
            tdd_pool=is_tdd_label(repair.constructor or "", repair.antenna_type or ""),
            as_of_date=getattr(repair, "entry_date", None) or "",
        )
        if picked is None:
            continue
        picked.remaining_quantity = remaining_of(picked) - 1

    db.flush()


def consume_no_serial_unit(
    db: Session,
    *,
    vendor: str,
    antenna_type: str,
    item_code: str,
    category: str,
    allow_item_code_fallback: bool = False,
    fallback_categories: Optional[Sequence[str]] = None,
    tdd_pool: bool = False,
) -> str:
    """Decrement remaining inventory by 1. Original quantity stays unchanged.

    For 5X/8X/TDD imports, pass fallback_categories=[مستهلک] so leftover
    units are taken from depreciated stock when province is exhausted.

    For TDD, pass tdd_pool=True to deduct from any TDD inventory row
    (ignore exact antenna type / vendor mismatch).
    """
    vendor = (vendor or "").strip()
    antenna_type = (antenna_type or "").strip()
    item_code = (item_code or "").strip()
    category = (category or "").strip()
    tdd_pool = bool(tdd_pool or is_tdd_label(vendor, antenna_type))

    categories: list[str] = [category]
    for extra in fallback_categories or ():
        extra = (extra or "").strip()
        if extra and extra not in categories:
            categories.append(extra)

    for cat in categories:
        if cat not in (CATEGORY_PROVINCE, CATEGORY_DEPRECIATED):
            raise ValueError("دسته نامعتبر است")

    for cat in categories:
        row = _find_stock_row(
            db,
            vendor=vendor,
            antenna_type=antenna_type,
            item_code=item_code,
            category=cat,
            allow_item_code_fallback=allow_item_code_fallback,
            tdd_pool=tdd_pool,
        )
        if row is not None:
            row.remaining_quantity = remaining_of(row) - 1
            db.flush()
            return cat

    raise ValueError(_missing_stock_message(db, vendor, antenna_type, item_code, categories, tdd_pool))


def _missing_stock_message(
    db: Session,
    vendor: str,
    antenna_type: str,
    item_code: str,
    categories: list[str],
    tdd_pool: bool,
) -> str:
    """Explain why this item-code cannot be taken from the no-serial pool."""
    tried = " / ".join(categories)
    code = item_code or "نامشخص"
    want_code = _norm_code(item_code)

    rows = db.query(models.NoSerialAntenna).all()
    same_code = [
        row
        for row in rows
        if _norm_code(row.item_code or "") == want_code
        or ((row.item_code or "").strip() == item_code and item_code)
    ]
    if tdd_pool:
        same_code = [row for row in same_code if _is_tdd_stock_row(row)]

    in_cats = [row for row in same_code if (row.category or "").strip() in categories]
    qty_in_cats = sum(remaining_of(row) for row in in_cats)

    if not same_code:
        if tdd_pool:
            return (
                f"آیتم‌کد «{code}» در دسته ({tried}) در مجموعه TDD وجود ندارد. "
                f"مقدار این آیتم‌کد صفر است و سریال ثبت نشد."
            )
        return (
            f"آیتم‌کد «{code}» در دسته ({tried}) در مجموعه وجود ندارد. "
            f"مقدار این آیتم‌کد صفر است و سریال ثبت نشد."
        )

    if not in_cats:
        other = sorted({(row.category or "").strip() for row in same_code if (row.category or "").strip()})
        other_txt = " / ".join(other) if other else "—"
        return (
            f"آیتم‌کد «{code}» در دسته مورد نظر ({tried}) وجود ندارد. "
            f"این آیتم‌کد فقط در دسته ({other_txt}) ثبت شده است و سریال ثبت نشد."
        )

    if qty_in_cats <= 0:
        return (
            f"مقدار آیتم‌کد «{code}» در دسته ({tried}) صفر است. "
            f"این آیتم‌کد در مجموعه موجودی ندارد و سریال ثبت نشد."
        )

    if tdd_pool:
        return (
            f"موجودی TDD برای آیتم‌کد «{code}» در دسته ({tried}) یافت نشد یا تمام شده است. "
            f"سریال ثبت نشد."
        )
    return (
        f"آیتم‌کد «{code}» در دسته ({tried}) برای وندور «{vendor}» "
        f"و نوع «{antenna_type}» موجودی ندارد. سریال ثبت نشد."
    )
