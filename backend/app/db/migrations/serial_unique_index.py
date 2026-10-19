#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""SQLite migration: enforce serial-number uniqueness at the database level.

یکتایی سریال آنتن تا امروز فقط در لایه‌ی برنامه کنترل می‌شد. این مmigration یک
ایندکس UNIQUE روی «سریال نرمال‌شده» (بدون حساسیت به بزرگی/کوچکی حروف و فاصله‌ی
اطراف) می‌سازد تا هیچ مسیری (ثبت دستی، ایمپورت اکسل، یا کدهای آینده) نتواند سریال
تکراری وارد جدول repairs کند. سریال‌های خالی/NULL از این قید مستثنا هستند.
"""

from sqlalchemy import text
from sqlalchemy.engine import Engine

INDEX_NAME = "uq_repairs_serial_ci"
# سریال به‌صورت نرمال‌شده (lower + trim) یکتا می‌شود؛ ردیف‌های با سریال خالی نادیده گرفته می‌شوند.
CREATE_SQL = (
    f"CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME} "
    "ON repairs (LOWER(TRIM(antenna_serial_no))) "
    "WHERE antenna_serial_no IS NOT NULL AND TRIM(antenna_serial_no) <> ''"
)

FIND_DUPLICATES_SQL = (
    "SELECT LOWER(TRIM(antenna_serial_no)) AS k, COUNT(*) AS c "
    "FROM repairs "
    "WHERE antenna_serial_no IS NOT NULL AND TRIM(antenna_serial_no) <> '' "
    "GROUP BY k HAVING c > 1 ORDER BY c DESC"
)


def migrate_serial_unique_index(engine: Engine) -> None:
    if engine.url.drivername != "sqlite":
        return

    with engine.connect() as conn:
        existing = {
            row[1]
            for row in conn.execute(text("PRAGMA index_list(repairs)")).fetchall()
        }
        if INDEX_NAME in existing:
            return

        duplicates = conn.execute(text(FIND_DUPLICATES_SQL)).fetchall()

    if duplicates:
        # اگر داده‌ی تکراری از قبل وجود داشته باشد، ایندکس UNIQUE ساخته نمی‌شود تا برنامه
        # بالا بیاید؛ لایه‌ی برنامه همچنان از ورود سریال تکراری جلوگیری می‌کند. ادمین باید
        # ابتدا این تکراری‌ها را برطرف کند تا قید دیتابیس فعال شود.
        # پیام روی کنسول ASCII نگه داشته می‌شود تا روی کنسول ویندوز (cp1252) خطا ندهد.
        preview = ", ".join(
            f"{row[0]!r} (x{row[1]})".encode("ascii", "replace").decode("ascii")
            for row in duplicates[:20]
        )
        print(
            "Serial uniqueness migration skipped: existing duplicate serials in "
            f"'repairs' block the UNIQUE index. Fix these first: {preview}"
        )
        return

    print("Migrating: adding UNIQUE index on repairs.antenna_serial_no...")
    with engine.begin() as conn:
        conn.execute(text(CREATE_SQL))
    print("Migration completed: serial-number UNIQUE index created")
