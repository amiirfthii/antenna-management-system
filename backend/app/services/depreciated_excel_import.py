#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import depreciated (مستهلک) inventory from Excel.

Expected columns (others are ignored):
  Vendor, Description, Type, QTY, Item Code

Each import **replaces** all depreciated stock with the Excel values (exact QTY,
not additive). Rows are keyed by vendor + Excel type + item code; the Excel
``type`` column (x-pole, 2x-pole, …) is stored as ``antenna_type`` so dashboard
totals match the spreadsheet.
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import jdatetime
import pandas as pd
from sqlalchemy.orm import Session

from app.db import models
from app.schemas.province_antenna import CATEGORY_DEPRECIATED
from app.services.province_excel_import import (
    norm,
    norm_item_code,
    norm_lower,
    parse_quantity,
)

HEADER_GROUPS: Dict[str, set[str]] = {
    "vendor": {"vendor", "وندور", "supplier vendor", "supplier_vendor"},
    "description": {"description", "desc", "دیسکریپشن"},
    "antenna_type": {"type", "antenna type", "antenna_type", "نوع", "نوع آنتن"},
    "quantity": {"qty", "quantity", "تعداد"},
    "item_code": {
        "item code",
        "item_code",
        "item cod",
        "item cod ",
        "itemcode",
        "آیتم کد",
        "آیتم‌کد",
    },
}


def _norm_header(value: Any) -> str:
    text = norm_lower(value)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _detect_header_row(raw: pd.DataFrame) -> Optional[Tuple[int, Dict[str, int]]]:
    max_scan = min(30, len(raw))
    for row_idx in range(max_scan):
        col_map: Dict[str, int] = {}
        for col_idx, cell in enumerate(raw.iloc[row_idx].tolist()):
            key = _norm_header(cell)
            if not key:
                continue
            for field, aliases in HEADER_GROUPS.items():
                if key in aliases and field not in col_map:
                    col_map[field] = col_idx
        if "item_code" in col_map and "quantity" in col_map:
            return row_idx, col_map
    return None


def _load_depreciated_sheet(content: bytes) -> Tuple[pd.DataFrame, Optional[str]]:
    xls = pd.ExcelFile(BytesIO(content))
    preferred = ["MAIN", "main", "Sheet1", "موجودی", "Depreciated"]
    sheet_order = preferred + [s for s in xls.sheet_names if s not in preferred]

    for sheet in sheet_order:
        if sheet not in xls.sheet_names:
            continue
        raw = pd.read_excel(BytesIO(content), sheet_name=sheet, header=None)
        detected = _detect_header_row(raw)
        if not detected:
            continue
        header_row, col_map = detected
        rows: List[Dict[str, Any]] = []
        for idx in range(header_row + 1, len(raw)):
            series = raw.iloc[idx]
            row = {
                field: series[col_idx] if col_idx < len(series) else None
                for field, col_idx in col_map.items()
            }
            row["_excel_row"] = int(idx) + 1
            rows.append(row)
        if not rows:
            continue
        return pd.DataFrame(rows), sheet

    return pd.DataFrame(), None


def _norm_type_key(value: Any) -> str:
    s = norm_lower(value)
    return re.sub(r"\s+", "", s.replace("-", "").replace("_", "").replace(".", ""))


def _normalize_excel_type(value: Any) -> str:
    text = norm(value)
    if not text:
        return ""
    return re.sub(r"\s+", "", text.lower())


def _item_code_variants(raw: str) -> List[str]:
    code = norm_item_code(raw)
    if not code:
        return []
    variants = [code]
    upper = code.upper()
    if upper.startswith("M") or upper.startswith("N"):
        bare = code[1:]
        if bare:
            variants.extend([bare, f"M{bare}", f"N{bare}"])
    else:
        variants.extend([f"M{code}", f"N{code}"])
    seen: set[str] = set()
    out: List[str] = []
    for item in variants:
        key = norm_lower(item)
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


class DepreciatedImportContext:
    def __init__(self, db: Session):
        self.db = db
        self.vendors = {
            norm_lower(row.company_constructor): (row.company_constructor or "").strip()
            for row in db.query(models.AntennaConstructor).all()
            if (row.company_constructor or "").strip()
        }
        self.by_code: Dict[str, List[models.ItemCodeAssignment]] = {}
        for assignment in db.query(models.ItemCodeAssignment).all():
            code = norm_item_code(assignment.item_code)
            if not code:
                continue
            for variant in _item_code_variants(code):
                self.by_code.setdefault(norm_lower(variant), []).append(assignment)

    def resolve_vendor(self, raw: str) -> Optional[str]:
        if not raw:
            return None
        return self.vendors.get(norm_lower(raw)) or norm(raw)

    def resolve_item_code(
        self,
        raw_code: str,
        raw_vendor: str = "",
        raw_type: str = "",
    ) -> Optional[str]:
        code = norm_item_code(raw_code)
        if not code:
            return None

        candidates: List[models.ItemCodeAssignment] = []
        seen_ids: set[int] = set()
        for variant in _item_code_variants(code):
            for row in self.by_code.get(norm_lower(variant), []):
                if row.id not in seen_ids:
                    seen_ids.add(row.id)
                    candidates.append(row)
        if not candidates:
            return code

        vendor = self.resolve_vendor(raw_vendor)
        excel_type = _normalize_excel_type(raw_type)
        if vendor and excel_type:
            for row in candidates:
                man = (row.manufacturer or "").strip()
                if norm_lower(man) != norm_lower(vendor) and norm_lower(man) != norm_lower(raw_vendor):
                    continue
                db_type = _norm_type_key(row.antenna_type)
                if db_type and excel_type and not _types_compatible(excel_type, db_type):
                    continue
                return norm_item_code(row.item_code) or code

        if vendor:
            for row in candidates:
                man = (row.manufacturer or "").strip()
                if norm_lower(man) == norm_lower(vendor) or norm_lower(man) == norm_lower(raw_vendor):
                    return norm_item_code(row.item_code) or code

        return norm_item_code(candidates[0].item_code) or code


def _types_compatible(excel_type: str, db_type: str) -> bool:
    """Loose match between Excel pole label and DB antenna model string."""
    ex = _norm_type_key(excel_type)
    db = _norm_type_key(db_type)
    if not ex or not db:
        return True
    if ex == db:
        return True
    if ex.endswith("pole") and db.startswith(ex.replace("pole", "")):
        return True
    if "xpole" in ex:
        nx = ex.replace("xpole", "").replace("pole", "")
        if nx.isdigit() and db.startswith(nx):
            return True
    return False


def _row_is_empty(row: pd.Series) -> bool:
    code = norm_item_code(row.get("item_code"))
    qty = parse_quantity(row.get("quantity"))
    if code and qty is not None and qty > 0:
        return False
    if code:
        return False
    if norm(row.get("vendor")) or norm(row.get("antenna_type")) or norm(row.get("description")):
        return False
    return True


def _format_row_error(row_no: int, reason: str) -> str:
    return f"ردیف {row_no}: {reason}"


def _entry_date_from_filename(filename: str | None) -> str:
    """Use Jalali date embedded in the Excel filename when present (e.g. 1405.04.20)."""
    if filename:
        match = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", filename)
        if match:
            year, month, day = match.groups()
            return f"{year}/{int(month):02d}/{int(day):02d}"
    return jdatetime.datetime.now().strftime("%Y/%m/%d")


def _aggregate_excel_rows(df: pd.DataFrame) -> Tuple[List[dict[str, Any]], List[str]]:
    grouped: Dict[Tuple[str, str, str], dict[str, Any]] = {}
    errors: List[str] = []

    for _, row in df.iterrows():
        if _row_is_empty(row):
            continue

        row_no = int(row.get("_excel_row") or 0) or 2
        raw_code = norm_item_code(row.get("item_code"))
        raw_vendor = norm(row.get("vendor"))
        raw_type = _normalize_excel_type(row.get("antenna_type"))
        quantity = parse_quantity(row.get("quantity"))

        if not raw_code:
            errors.append(_format_row_error(row_no, "آیتم کد خالی است"))
            continue
        if quantity is None or quantity <= 0:
            continue
        if not raw_vendor:
            errors.append(_format_row_error(row_no, "وندور خالی است"))
            continue
        if not raw_type:
            errors.append(_format_row_error(row_no, "نوع (Type) خالی است"))
            continue

        key = (norm_lower(raw_vendor), raw_type, norm_lower(raw_code))
        if key in grouped:
            grouped[key]["quantity"] += quantity
            grouped[key]["source_rows"].append(row_no)
        else:
            grouped[key] = {
                "vendor": raw_vendor,
                "antenna_type": raw_type,
                "item_code": raw_code,
                "quantity": quantity,
                "source_rows": [row_no],
            }

    return list(grouped.values()), errors


def import_depreciated_antennas_from_excel(
    db: Session,
    content: bytes,
    filename: str | None = None,
) -> dict[str, Any]:
    df, sheet_name = _load_depreciated_sheet(content)
    if df.empty or sheet_name is None:
        return {
            "total": 0,
            "imported": 0,
            "failed": 0,
            "errors": [
                "ستون‌های Vendor/Type/QTY/Item Code در هیچ شیت اکسل یافت نشد. "
                "لطفاً فایلی با ستون‌های Vendor، Description، Type، QTY و Item Code بارگذاری کنید."
            ],
        }

    aggregated, parse_errors = _aggregate_excel_rows(df)
    ctx = DepreciatedImportContext(db)
    imported = failed = 0
    errors: List[str] = list(parse_errors)
    entry_date = _entry_date_from_filename(filename)

    db.query(models.NoSerialAntenna).filter(
        models.NoSerialAntenna.category == CATEGORY_DEPRECIATED
    ).delete(synchronize_session=False)

    for item in aggregated:
        row_label = item["source_rows"][0]
        vendor = ctx.resolve_vendor(item["vendor"])
        if not vendor:
            failed += 1
            errors.append(_format_row_error(row_label, f"وندور «{item['vendor']}» در دیتابیس موجود نیست"))
            continue

        item_code = ctx.resolve_item_code(item["item_code"], vendor, item["antenna_type"])
        if not item_code:
            failed += 1
            errors.append(_format_row_error(row_label, f"آیتم‌کد «{item['item_code']}» نامعتبر است"))
            continue

        db.add(
            models.NoSerialAntenna(
                vendor=vendor,
                antenna_type=item["antenna_type"],
                item_code=item_code,
                category=CATEGORY_DEPRECIATED,
                province="",
                quantity=int(item["quantity"]),
                remaining_quantity=int(item["quantity"]),
                created_date=entry_date,
            )
        )
        imported += 1

    db.commit()

    total = imported + failed
    return {
        "total": total,
        "imported": imported,
        "failed": failed,
        "errors": errors,
        "sheet": sheet_name,
    }
