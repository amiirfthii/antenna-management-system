#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""SQLite migration: allow تجهیزات warehouse type in arsenalTable."""

from sqlalchemy import text
from sqlalchemy.engine import Engine


def migrate_arsenal_equipment_type(engine: Engine) -> None:
    if engine.url.drivername != "sqlite":
        return

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='arsenalTable'")
        ).fetchone()
        if not row or not row[0]:
            return
        if "تجهیزات" in row[0]:
            return

    print("Migrating: updating arsenalTable to allow equipment warehouse type...")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(
            text(
                """
                CREATE TABLE arsenalTable_new (
                    fragment_part_no VARCHAR(100) NOT NULL,
                    arsenal_name VARCHAR(50) NOT NULL,
                    fragment_name VARCHAR(191) NOT NULL,
                    fragment_qty INTEGER NOT NULL,
                    PRIMARY KEY (fragment_part_no, arsenal_name),
                    CHECK (arsenal_name IN ('نو', 'سالویج', 'تجهیزات'))
                )
                """
            )
        )
        conn.execute(text("INSERT INTO arsenalTable_new SELECT * FROM arsenalTable"))
        conn.execute(text("DROP TABLE arsenalTable"))
        conn.execute(text("ALTER TABLE arsenalTable_new RENAME TO arsenalTable"))
        conn.execute(text("PRAGMA foreign_keys=ON"))
    print("Migration completed: arsenalTable supports equipment type")
