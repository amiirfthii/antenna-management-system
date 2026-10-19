#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Set no_serial_category=استان for repairs with entry_date >= 1405/01/01."""

from sqlalchemy.engine import Engine

from app.core.jalali_dates import normalize_jalali_date_string
from app.db import models
from app.db.database import SessionLocal
from app.schemas.province_antenna import CATEGORY_PROVINCE

CUTOFF = "1405/01/01"


def _date_key(value: object) -> str:
    raw = normalize_jalali_date_string(value) or ""
    return raw[:10]


def is_province_entry_date(value: object) -> bool:
    """True for 1405/01/01 and every later entry date."""
    key = _date_key(value)
    return len(key) >= 10 and key >= CUTOFF


def migrate_repair_category_from_1405(engine: Engine) -> None:
    del engine
    db = SessionLocal()
    try:
        updated = 0
        for row in db.query(models.Repair).all():
            if not is_province_entry_date(row.entry_date):
                continue
            current = (row.no_serial_category or "").strip()
            if current == CATEGORY_PROVINCE:
                continue
            row.no_serial_category = CATEGORY_PROVINCE
            updated += 1
        if updated:
            db.commit()
            print(f"Backfilled no_serial_category=province for {updated} repairs since {CUTOFF}")
        else:
            print("Repair category backfill: nothing to update")
    finally:
        db.close()
