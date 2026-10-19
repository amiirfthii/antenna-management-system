#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""SQLite migration: provinceAntennas → noSerialAntennas + category column."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

CATEGORY_PROVINCE = "استان"
TABLE_OLD = "provinceAntennas"
TABLE_NEW = "noSerialAntennas"


def migrate_no_serial_antenna(engine: Engine) -> None:
    if engine.url.drivername != "sqlite":
        return

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if TABLE_OLD in tables and TABLE_NEW not in tables:
        print(f"Migrating: renaming {TABLE_OLD} to {TABLE_NEW}...")
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE "{TABLE_OLD}" RENAME TO "{TABLE_NEW}"'))
        print("Table rename completed")
        inspector = inspect(engine)
        tables = inspector.get_table_names()

    if TABLE_NEW not in tables:
        return

    columns = {col["name"] for col in inspector.get_columns(TABLE_NEW)}
    if "category" not in columns:
        print("Migrating: adding category column to noSerialAntennas...")
        with engine.begin() as conn:
            conn.execute(
                text(
                    f'ALTER TABLE "{TABLE_NEW}" ADD COLUMN category VARCHAR(50) '
                    f"DEFAULT '{CATEGORY_PROVINCE}'"
                )
            )
            conn.execute(
                text(
                    f'UPDATE "{TABLE_NEW}" SET category = :cat '
                    "WHERE category IS NULL OR TRIM(category) = ''"
                ),
                {"cat": CATEGORY_PROVINCE},
            )
        print("Category column added")

    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns(TABLE_NEW)}
    if "remaining_quantity" not in columns:
        print("Migrating: adding remaining_quantity to noSerialAntennas...")
        with engine.begin() as conn:
            conn.execute(
                text(
                    f'ALTER TABLE "{TABLE_NEW}" ADD COLUMN remaining_quantity INTEGER'
                )
            )
            conn.execute(
                text(
                    f'UPDATE "{TABLE_NEW}" SET remaining_quantity = quantity '
                    "WHERE remaining_quantity IS NULL"
                )
            )
        print("remaining_quantity column added")
