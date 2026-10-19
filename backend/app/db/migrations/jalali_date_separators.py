#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""One-time migration: normalize stored Jalali date strings to YYYY/MM/DD."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.jalali_dates import normalize_jalali_date_string
from app.db import models

DATE_COLUMNS: list[tuple[str, list[str]]] = [
    ("repairs", ["entry_date", "exit_date", "antenna_admin_check_date"]),
    ("repairSteps", ["start_date", "end_date"]),
    ("supplyFragmentEntry", ["fragment_entry_date"]),
    ("repairItemsReport", ["repair_date"]),
    ("itemCodeAssignments", ["created_date"]),
    ("deliveredAntennas", ["entry_date"]),
    ("inventory_history", ["operation_date"]),
]

TABLE_MODELS: dict[str, type] = {
    "repairs": models.Repair,
    "repairSteps": models.RepairStep,
    "supplyFragmentEntry": models.SupplyFragmentEntry,
    "repairItemsReport": models.RepairItemReport,
    "itemCodeAssignments": models.ItemCodeAssignment,
    "deliveredAntennas": models.DeliveredAntenna,
    "inventory_history": models.InventoryHistory,
}


def _quote_ident(name: str, dialect: str) -> str:
    if dialect.startswith("mysql"):
        return f"`{name}`"
    return f'"{name}"'


def _normalize_rows(session: Session, table: str, columns: list[str]) -> int:
    model = TABLE_MODELS.get(table)
    if model is None:
        return 0

    updated = 0
    for row in session.query(model).yield_per(500):
        changed = False
        for column in columns:
            if not hasattr(row, column):
                continue
            value = getattr(row, column)
            if not value:
                continue
            normalized = normalize_jalali_date_string(value)
            if normalized and normalized != value:
                setattr(row, column, normalized)
                changed = True
        if changed:
            updated += 1
    return updated


def migrate_jalali_date_separators(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    dialect = engine.url.drivername
    sql_updated = 0

    with engine.begin() as conn:
        for table, columns in DATE_COLUMNS:
            if table not in tables:
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            table_q = _quote_ident(table, dialect)
            for column in columns:
                if column not in existing:
                    continue
                col_q = _quote_ident(column, dialect)
                stmt = text(
                    f"UPDATE {table_q} SET {col_q} = REPLACE({col_q}, '.', '/') "
                    f"WHERE {col_q} LIKE '%.%'"
                )
                result = conn.execute(stmt)
                sql_updated += result.rowcount or 0

    orm_updated = 0
    with Session(engine) as session:
        for table, columns in DATE_COLUMNS:
            if table not in tables:
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            valid_columns = [col for col in columns if col in existing]
            if not valid_columns:
                continue
            orm_updated += _normalize_rows(session, table, valid_columns)
        if orm_updated:
            session.commit()

    total = sql_updated + orm_updated
    if total:
        print(
            f"Migration: normalized {total} stored date value(s) "
            f"({sql_updated} dot→slash SQL, {orm_updated} ORM zero-pad/format)"
        )
