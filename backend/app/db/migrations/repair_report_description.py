#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""SQLite migration: add item_description to repairItemsReport."""

from sqlalchemy import text
from sqlalchemy.engine import Engine


def migrate_repair_report_description(engine: Engine) -> None:
    if engine.url.drivername != "sqlite":
        return

    with engine.connect() as conn:
        cols = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(repairItemsReport)")).fetchall()
        }
        if "item_description" in cols:
            return

    print("Migrating: adding item_description to repairItemsReport...")
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE repairItemsReport ADD COLUMN item_description VARCHAR(500)")
        )
    print("Migration completed: item_description column added")
