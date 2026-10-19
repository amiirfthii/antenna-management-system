#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import jdatetime
import pandas as pd
from sqlalchemy.orm import Session

from app.core.iran_city_province import resolve_city_to_province
from app.core.iran_provinces import IRAN_PROVINCES
from app.core.jalali_dates import normalize_jalali_date_string
from app.db import models
from app.schemas.province_antenna import CATEGORY_PROVINCE
from app.services.no_serial_antenna_utils import (
    duplicate_message,
    format_row_summary,
    no_serial_row_key,
)

COLUMN_ALIASES: Dict[str, str] = {
    "no": "row_no",
    "row_no": "row_no",
    "row": "row_no",
    "شماره": "row_no",
    "vendor": "vendor",
    "وندور": "vendor",
    "supplier vendor": "vendor",
    "supplier_vendor": "vendor",
    "antenna type": "antenna_type",
    "antenna_type": "antenna_type",
    "نوع آنتن": "antenna_type",
    "item code": "item_code",
    "item_code": "item_code",
    "item code ": "item_code",
    "item cod": "item_code",
    "item cod ": "item_code",
    "آیتم کد": "item_code",
    "آیتم‌کد": "item_code",
    "province": "province",
    "استان": "province",
    "city": "city",
    "شهر": "city",
    "type": "antenna_type",
    "نوع": "antenna_type",
    "quantity": "quantity",
    "qty": "quantity",
    "تعداد": "quantity",
    "entry_date": "entry_date",
    "تاریخ": "entry_date",
    "تاریخ ورود": "entry_date",
    "created_date": "entry_date",
}

REQUIRED_FIELDS = ("vendor", "antenna_type", "item_code", "province", "quantity")

VENDOR_ALIASES: Dict[str, str] = {
    "kathrein": "kathrein",
    "katrein": "kathrein",
    "katrin": "kathrein",
    "kathreien": "kathrein",
    "kathrien": "kathrein",
    "mobi anten": "Mobi",
}

# Log when Excel vendor spelling was a known typo alias.
VENDOR_TYPO_NORMALIZE: set[str] = {
    "katrein",
    "katrin",
    "kathreien",
    "kathrien",
}


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


def norm(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def norm_lower(value: Any) -> str:
    return norm(value).lower()


def norm_item_code(value: Any) -> str:
    s = norm(value)
    if not s:
        return ""
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    if re.fullmatch(r"\d+\.0", s):
        return s[:-2]
    return s


def parse_quantity(value: Any) -> Optional[int]:
    s = norm(value)
    if not s:
        return None
    s = s.replace(",", "")
    try:
        qty = int(float(s))
    except (ValueError, TypeError):
        return None
    return qty


def parse_entry_date(value: Any) -> Optional[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        try:
            g = value.to_pydatetime().date()
            j = jdatetime.date.fromgregorian(date=g)
            return j.strftime("%Y/%m/%d")
        except (ValueError, OverflowError):
            pass
    s = norm(value)
    if not s:
        return None
    if isinstance(value, float) and value == int(value):
        s = str(int(value))
    greg = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if greg:
        try:
            from datetime import date as date_cls

            y, m, d = (int(greg.group(1)), int(greg.group(2)), int(greg.group(3)))
            j = jdatetime.date.fromgregorian(date=date_cls(y, m, d))
            return j.strftime("%Y/%m/%d")
        except (ValueError, OverflowError):
            pass
    normalized = normalize_jalali_date_string(s)
    return normalized if normalized is not None else s


def _norm_header(value: Any) -> str:
    text = norm_lower(value)
    return re.sub(r"\s+", " ", text).strip()


def parse_date_header(value: Any) -> Optional[str]:
    """Parse Jalali date from Received-sheet column headers like 01/01/14."""
    parsed = parse_entry_date(value)
    if parsed and re.match(r"^\d{4}/\d{2}/\d{2}$", parsed):
        return parsed

    s = norm(value)
    if not s:
        return None

    match = re.match(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})$", s)
    if match:
        day, month, year_raw = match.groups()
        year = int(year_raw)
        if year < 100:
            year = 1400 + year
        return f"{year}/{month.zfill(2)}/{day.zfill(2)}"

    return parsed


def resolve_province_value(raw_province: str, raw_city: str = "") -> Tuple[str, Optional[str]]:
    """Return (province_name, error_message)."""
    province = norm(raw_province)
    city = norm(raw_city)

    if province and province in IRAN_PROVINCES:
        return province, None

    for candidate in (province, city):
        if not candidate:
            continue
        mapped = resolve_city_to_province(candidate)
        if mapped:
            return mapped, None
        if candidate in IRAN_PROVINCES:
            return candidate, None

    label = province or city or "خالی"
    return "", f"شهر/استان «{label}» شناخته نشد — نام شهر انگلیسی یا استان فارسی وارد کنید"


WIDE_HEADER_GROUPS: Dict[str, set[str]] = {
    "city": {"city", "شهر"},
    "vendor": {"vendor", "وندور", "supplier vendor", "supplier_vendor"},
    "antenna_type": {"type", "antenna type", "antenna_type", "نوع", "نوع آنتن"},
    "item_code": {
        "item code",
        "item_code",
        "item code ",
        "item cod",
        "item cod ",
        "itemcode",
        "item cod",
        "آیتم کد",
        "آیتم‌کد",
    },
    "total": {"total", "جمع", "sum"},
    "description": {"description", "desc", "دیسکریپشن"},
}


def _detect_received_header_row(raw: pd.DataFrame) -> Optional[Tuple[int, Dict[str, int], List[Tuple[int, str]]]]:
    max_scan = min(15, len(raw))
    for row_idx in range(max_scan):
        col_map: Dict[str, int] = {}
        date_cols: List[Tuple[int, str]] = []
        for col_idx, cell in enumerate(raw.iloc[row_idx].tolist()):
            key = _norm_header(cell)
            if not key:
                continue
            matched_fixed = False
            for field, aliases in WIDE_HEADER_GROUPS.items():
                if key in aliases and field not in col_map:
                    col_map[field] = col_idx
                    matched_fixed = True
                    break
            if matched_fixed:
                continue
            if key in {"no", "row", "شماره"}:
                continue
            entry_date = parse_date_header(cell)
            if entry_date:
                date_cols.append((col_idx, entry_date))

        has_location = "city" in col_map or "province" in col_map
        if has_location and "vendor" in col_map and "item_code" in col_map and date_cols:
            if "province" not in col_map and "city" in col_map:
                col_map["province"] = col_map["city"]
            return row_idx, col_map, date_cols
    return None


def _load_received_wide_format(content: bytes) -> Tuple[pd.DataFrame, Optional[str]]:
    xls = pd.ExcelFile(BytesIO(content))
    preferred = ["Received", "received", "ورودی", "ورودی ارسالی", "Sheet1"]
    sheet_order = preferred + [s for s in xls.sheet_names if s not in preferred]

    for sheet in sheet_order:
        if sheet not in xls.sheet_names:
            continue
        raw = pd.read_excel(BytesIO(content), sheet_name=sheet, header=None)
        detected = _detect_received_header_row(raw)
        if not detected:
            continue

        header_row, col_map, date_cols = detected
        rows: List[Dict[str, Any]] = []
        for idx in range(header_row + 1, len(raw)):
            series = raw.iloc[idx]
            base = {
                field: series[col_idx] if col_idx < len(series) else None
                for field, col_idx in col_map.items()
                if field not in {"total", "description"}
            }
            if not any(norm(base.get(k)) for k in ("city", "province", "vendor", "item_code")):
                continue

            excel_row = int(idx) + 1
            expanded = False
            for col_idx, entry_date in date_cols:
                qty = parse_quantity(series[col_idx] if col_idx < len(series) else None)
                if qty is None or qty <= 0:
                    continue
                row = dict(base)
                row["quantity"] = qty
                row["entry_date"] = entry_date
                row["row_no"] = excel_row
                rows.append(row)
                expanded = True

            if not expanded:
                total_qty = parse_quantity(series[col_map["total"]]) if "total" in col_map else None
                if total_qty and total_qty > 0:
                    row = dict(base)
                    row["quantity"] = total_qty
                    row["entry_date"] = jdatetime.datetime.now().strftime("%Y/%m/%d")
                    row["row_no"] = excel_row
                    rows.append(row)

        if rows:
            return pd.DataFrame(rows), sheet

    return pd.DataFrame(), None


def _prepare_standard_dataframe(content: bytes) -> pd.DataFrame:
    df = pd.read_excel(BytesIO(content))
    df = normalize_dataframe(df)
    if "city" in df.columns and "province" not in df.columns:
        df = df.rename(columns={"city": "province"})
    elif "city" in df.columns:
        empty_province = df["province"].isna() | (df["province"].astype(str).str.strip() == "")
        df.loc[empty_province, "province"] = df.loc[empty_province, "city"]
    return df


def ci_map(items: List[str]) -> Dict[str, str]:
    return {norm_lower(item): item for item in items if norm(item)}


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    rename: Dict[str, str] = {}
    for col in df.columns:
        key = norm_lower(col)
        if key in COLUMN_ALIASES:
            rename[col] = COLUMN_ALIASES[key]
    if rename:
        df = df.rename(columns=rename)
    return df


def validate_excel_columns(df: pd.DataFrame) -> Optional[str]:
    missing = [field for field in REQUIRED_FIELDS if field not in df.columns]
    if missing:
        labels = {
            "vendor": "وندور",
            "antenna_type": "نوع آنتن",
            "item_code": "آیتم کد",
            "province": "استان",
            "quantity": "تعداد",
        }
        return "ستون‌های الزامی در اکسل یافت نشد: " + "، ".join(labels[f] for f in missing)
    return None


def row_is_empty(row: pd.Series) -> bool:
    has_location = bool(norm(row.get("province")) or norm(row.get("city")))
    has_vendor = bool(norm(row.get("vendor")))
    has_type = bool(norm(row.get("antenna_type")))
    has_code = bool(norm_item_code(row.get("item_code")))
    qty = parse_quantity(row.get("quantity"))
    if qty is not None and qty > 0:
        return False
    return not (has_location and has_vendor and has_type and has_code)


class ProvinceImportContext:
    def __init__(self, db: Session):
        self.db = db
        self.vendors = ci_map(
            [row.company_constructor for row in db.query(models.AntennaConstructor).all()]
        )
        self.types = ci_map([row.antenna_type for row in db.query(models.AntennaType).all()])
        self.assignments: Dict[Tuple[str, str, str], models.ItemCodeAssignment] = {}
        self.by_code: Dict[str, List[models.ItemCodeAssignment]] = {}
        self.item_codes_lower: set[str] = set()
        self.seen_keys: set[Tuple[str, str, str, str, str, int, str]] = set()
        self.key_sources: Dict[Tuple[str, str, str, str, str, int, str], str] = {}
        for assignment in db.query(models.ItemCodeAssignment).all():
            vendor = norm(assignment.manufacturer)
            antenna_type = norm(assignment.antenna_type)
            item_code = norm_item_code(assignment.item_code)
            if not vendor or not antenna_type or not item_code:
                continue
            self.item_codes_lower.add(norm_lower(item_code))
            key = (norm_lower(vendor), norm_lower(antenna_type), norm_lower(item_code))
            self.assignments[key] = assignment
            for variant in _item_code_variants(item_code):
                self.by_code.setdefault(norm_lower(variant), []).append(assignment)
        for row in db.query(models.NoSerialAntenna).all():
            key = no_serial_row_key(
                row.vendor,
                row.antenna_type,
                row.item_code,
                row.category,
                row.province or "",
                row.quantity,
                row.created_date or "",
            )
            self.seen_keys.add(key)
            self.key_sources[key] = (
                f"DB #{row.id} — "
                + format_row_summary(
                    row.vendor,
                    row.antenna_type,
                    row.item_code,
                    row.category,
                    row.province or "",
                    row.quantity,
                    row.created_date or "",
                )
            )

    def resolve_vendor(self, raw: str) -> Optional[str]:
        key = norm_lower(raw)
        if not key:
            return None
        alias = VENDOR_ALIASES.get(key)
        if alias:
            return self.vendors.get(norm_lower(alias)) or alias
        return self.vendors.get(key)

    def resolve_type(self, raw: str) -> Optional[str]:
        return self.types.get(norm_lower(raw))

    def find_assignment(
        self, raw_vendor: str, raw_type: str, raw_code: str
    ) -> Optional[models.ItemCodeAssignment]:
        vendor = self.resolve_vendor(raw_vendor)
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
            return None

        if vendor:
            for row in candidates:
                man = norm(row.manufacturer)
                if norm_lower(man) == norm_lower(vendor):
                    return row

        raw_vendor_norm = norm_lower(raw_vendor)
        for row in candidates:
            man = norm(row.manufacturer)
            if norm_lower(man) == raw_vendor_norm:
                return row

        return candidates[0]

    def item_code_exists(self, code: str) -> bool:
        return norm_lower(code) in self.item_codes_lower

    def resolve_assignment(
        self, vendor: str, antenna_type: str, item_code: str
    ) -> Optional[models.ItemCodeAssignment]:
        key = (norm_lower(vendor), norm_lower(antenna_type), norm_lower(item_code))
        return self.assignments.get(key)

    def is_duplicate(
        self,
        vendor: str,
        antenna_type: str,
        item_code: str,
        category: str,
        province: str,
        quantity: int,
        created_date: str = "",
    ) -> bool:
        key = no_serial_row_key(
            vendor, antenna_type, item_code, category, province, quantity, created_date
        )
        return key in self.seen_keys

    def duplicate_reason(
        self,
        vendor: str,
        antenna_type: str,
        item_code: str,
        category: str,
        province: str,
        quantity: int,
        created_date: str = "",
    ) -> Optional[str]:
        key = no_serial_row_key(
            vendor, antenna_type, item_code, category, province, quantity, created_date
        )
        if key not in self.seen_keys:
            return None
        match_label = self.key_sources.get(key, "رکورد موجود")
        return duplicate_message(
            match_label,
            vendor=vendor,
            antenna_type=antenna_type,
            item_code=item_code,
            category=category,
            province=province,
            quantity=quantity,
            created_date=created_date,
        )

    def register_row(
        self,
        vendor: str,
        antenna_type: str,
        item_code: str,
        category: str,
        province: str,
        quantity: int,
        created_date: str = "",
        source_label: str = "",
    ) -> None:
        key = no_serial_row_key(
            vendor, antenna_type, item_code, category, province, quantity, created_date
        )
        self.seen_keys.add(key)
        if source_label:
            self.key_sources[key] = source_label


def validate_province_row(
    db: Session,
    vendor: str,
    antenna_type: str,
    item_code: str,
    province: str,
    quantity: int,
) -> Optional[str]:
    del db, vendor, antenna_type, item_code
    if quantity <= 0:
        return "تعداد باید بزرگ‌تر از صفر باشد"
    province = province.strip()
    if province not in IRAN_PROVINCES:
        return f"استان «{province or 'خالی'}» نامعتبر است"
    return None


def _format_row_error(row_no: int, reason: str) -> str:
    return f"ردیف {row_no}: {reason}"


def import_row(row_no: int, row: pd.Series, ctx: ProvinceImportContext) -> Tuple[str, str]:
    if row_is_empty(row):
        return "skipped", ""

    raw_vendor = norm(row.get("vendor"))
    raw_type = norm(row.get("antenna_type"))
    raw_code = norm_item_code(row.get("item_code"))
    raw_province, province_err = resolve_province_value(
        norm(row.get("province")),
        norm(row.get("city")),
    )
    quantity = parse_quantity(row.get("quantity"))

    if not raw_vendor:
        return "failed", "وندور خالی است"
    if not raw_type:
        return "failed", "نوع آنتن خالی است"
    if not raw_code:
        return "failed", "آیتم کد خالی است"
    if province_err:
        return "failed", province_err
    if quantity is None or quantity <= 0:
        return "failed", "تعداد نامعتبر است"

    vendor_key = norm_lower(raw_vendor)
    vendor = ctx.resolve_vendor(raw_vendor)
    if not vendor:
        return "failed", f"وندور «{raw_vendor}» در دیتابیس موجود نیست"

    assignment = ctx.find_assignment(raw_vendor, raw_type, raw_code)
    if not assignment:
        if not ctx.item_code_exists(raw_code):
            return "failed", f"آیتم‌کد «{raw_code}» در جدول اختصاص آیتم‌کد موجود نیست"
        return (
            "failed",
            f"آیتم‌کد «{raw_code}» برای وندور «{vendor}» در جدول اختصاص آیتم‌کد یافت نشد",
        )

    canonical_code = norm_item_code(assignment.item_code) or raw_code
    antenna_type = norm(raw_type) or norm(assignment.antenna_type)
    if not antenna_type:
        return "failed", "نوع آنتن خالی است"

    province_error = validate_province_row(
        ctx.db, vendor, antenna_type, canonical_code, raw_province, quantity
    )
    if province_error:
        return "failed", province_error

    matched_province = next((p for p in IRAN_PROVINCES if p == raw_province), raw_province)
    entry_date = parse_entry_date(row.get("entry_date")) or jdatetime.datetime.now().strftime("%Y/%m/%d")

    dup_reason = ctx.duplicate_reason(
        vendor,
        antenna_type,
        canonical_code,
        CATEGORY_PROVINCE,
        matched_province,
        quantity,
        entry_date,
    )
    if dup_reason:
        return "failed", dup_reason

    ctx.db.add(
        models.NoSerialAntenna(
            vendor=vendor,
            antenna_type=antenna_type,
            item_code=canonical_code,
            category=CATEGORY_PROVINCE,
            province=matched_province,
            quantity=quantity,
            remaining_quantity=quantity,
            created_date=entry_date,
        )
    )
    ctx.register_row(
        vendor,
        antenna_type,
        canonical_code,
        CATEGORY_PROVINCE,
        matched_province,
        quantity,
        entry_date,
        source_label=(
            f"ردیف {row_no} اکسل — "
            + format_row_summary(
                vendor,
                antenna_type,
                canonical_code,
                CATEGORY_PROVINCE,
                matched_province,
                quantity,
                entry_date,
            )
        ),
    )
    return "imported", ""


def import_province_antennas_from_excel(db: Session, content: bytes) -> dict[str, Any]:
    df, sheet_name = _load_received_wide_format(content)
    replaced = False
    if not df.empty:
        db.query(models.NoSerialAntenna).filter(
            models.NoSerialAntenna.category == CATEGORY_PROVINCE
        ).delete(synchronize_session=False)
        db.commit()
        replaced = True
    else:
        df = _prepare_standard_dataframe(content)
        col_error = validate_excel_columns(df)
        if col_error:
            return {
                "total": 0,
                "imported": 0,
                "failed": 0,
                "errors": [col_error],
            }
    if df.empty:
        df = _prepare_standard_dataframe(content)
    if df.empty:
        return {
            "total": 0,
            "imported": 0,
            "failed": 0,
            "errors": ["شیت Received یا فرمت استاندارد ورودی استان در فایل یافت نشد"],
        }

    col_error = validate_excel_columns(df)
    if col_error:
        return {
            "total": 0,
            "imported": 0,
            "failed": 0,
            "errors": [f"شیت «{sheet_name}»: {col_error}" if sheet_name else col_error],
        }

    ctx = ProvinceImportContext(db)
    imported = failed = skipped = 0
    errors: List[str] = []
    skip_notes: List[str] = []

    batch = 500
    for idx, row in df.iterrows():
        if "row_no" in df.columns and pd.notna(row.get("row_no")):
            try:
                row_no = int(float(row.get("row_no")))
            except (TypeError, ValueError):
                row_no = int(idx) + 2
        else:
            row_no = int(idx) + 2

        status, reason = import_row(row_no, row, ctx)
        if status == "imported":
            imported += 1
        elif status == "failed":
            failed += 1
            prefix = f"ردیف {row_no}"
            if row.get("entry_date"):
                prefix += f" ({row.get('entry_date')})"
            errors.append(f"{prefix}: {reason}")
        else:
            skipped += 1
            if reason:
                skip_notes.append(f"ردیف {row_no}: {reason}")

        if (idx + 1) % batch == 0:
            db.commit()

    db.commit()

    total = imported + failed
    result: dict[str, Any] = {
        "total": total,
        "imported": imported,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
    }
    if skip_notes:
        result["errors"] = skip_notes + errors
    if replaced:
        result["replaced"] = True
        result["sheet"] = sheet_name
    return result
