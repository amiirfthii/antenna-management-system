#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""SQLite migration: add no_serial_category (استان/مستهلک source) to repairs."""

from sqlalchemy import text
from sqlalchemy.engine import Engine


def migrate_repair_source_category(engine: Engine) -> None:
    if engine.url.drivername != "sqlite":
        return

    with engine.connect() as conn:
        cols = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(repairs)")).fetchall()
        }
        if "no_serial_category" in cols:
            return

    print("Migrating: adding no_serial_category to repairs...")
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE repairs ADD COLUMN no_serial_category VARCHAR(100)")
        )
    print("Migration completed: no_serial_category column added")
