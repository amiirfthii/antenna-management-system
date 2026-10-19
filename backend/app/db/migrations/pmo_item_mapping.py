#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""SQLite migration: create pmoItemMapping table."""

from sqlalchemy import text
from sqlalchemy.engine import Engine


def migrate_pmo_item_mapping(engine: Engine) -> None:
    if engine.url.drivername != "sqlite":
        return

    with engine.connect() as conn:
        exists = conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='pmoItemMapping'"
            )
        ).fetchone()
        if exists:
            return

    print("Migrating: creating pmoItemMapping table...")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE pmoItemMapping (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vendor VARCHAR(100) NOT NULL DEFAULT '',
                    antenna_type VARCHAR(100) NOT NULL DEFAULT '',
                    item_code VARCHAR(100) NOT NULL,
                    pmo_row_type VARCHAR(100) NOT NULL DEFAULT '',
                    updated_date VARCHAR(100)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX idx_pmo_item_mapping_triple
                ON pmoItemMapping (vendor, antenna_type, item_code)
                """
            )
        )
    print("Migration completed: pmoItemMapping table created")
