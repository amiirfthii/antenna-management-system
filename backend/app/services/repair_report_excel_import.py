#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import repair-item reports from the official Excel template
(گزارش از 1405 …) — Settings → پشتیبان‌گیری / بارگذاری.
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.jalali_dates import normalize_jalali_date_string
from app.db import models
from app.services.serial_uniqueness import (
    find_repair_by_serial,
    normalize_serial,
    serial_key,
)

REQUIRED_COLUMNS = [
    "start_date",
    "Supplier Vendor",
    " Antenna type",
    "antenna_serial_no",
    "Item code ",
    "item_name",
    "personal_id",
    "status",
]

# Excel header → display name stored in fragment_name (قطعه)
SPECIAL_QTY_COLUMNS: List[Tuple[str, str]] = [
    ("Electrical tilt", "تیلت الکتریکال"),
    ("Fixator", "فیکساتور"),
    ("Roller", "رولر"),
    ("RET", "رت"),
    ("Bracket Removal", "براکت"),
    ("Connector", "کانکتور"),
    ("Radom door", "رادوم درب"),
]

ALLOWED_ITEM_STATUSES = {
    "در حال انجام",
    "انجام نشده",
    "انجام شده",
    "فالتی",
}


def norm(s: Any) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    return str(s).strip()


def norm_lower(s: Any) -> str:
    return norm(s).lower()


def norm_person_name(s: Any) -> str:
    t = norm(s).replace("ي", "ی").replace("ك", "ک")
    t = re.sub(r"\s+", " ", t)
    return t.casefold()


def norm_serial(v: Any) -> str:
    return normalize_serial(v)


def parse_personal_id(v: Any) -> Optional[int]:
    s = norm(v)
    if not s or s in ("`", "-", "nan"):
        return None
    s = s.replace(",", "")
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def parse_date(v: Any) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    # Excel may yield datetime/date cells
    if hasattr(v, "strftime") and not isinstance(v, str):
        try:
            # Prefer Jalali-looking string if already formatted; else keep ISO-ish
            s = str(v).strip()
            # If it's a real datetime from Excel serial, leave as YYYY-MM-DD for normalize attempt
            if hasattr(v, "year") and getattr(v, "year", 0) > 1700:
                s = f"{v.year:04d}-{v.month:02d}-{v.day:02d}"
            normalized = normalize_jalali_date_string(s)
            return normalized if normalized is not None else s
        except Exception:
            pass
    s = norm(v)
    if not s:
        return ""
    if isinstance(v, float) and v == int(v):
        s = str(int(v))
    normalized = normalize_jalali_date_string(s)
    return normalized if normalized is not None else s


def parse_qty(v: Any) -> Optional[int]:
    """Return int quantity when cell has a numeric value; else None."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = norm(v).replace(",", "")
    if not s or s in ("-", "nan", "None"):
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def ci_map(items: List[str]) -> Dict[str, str]:
    return {norm_lower(x): x for x in items}


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.dropna(axis=1, how="all")
    rename: Dict[str, str] = {}
    canonical = {
        "no": "No",
        "start_date": "start_date",
        "end_date": "end_date",
        "supplier vendor": "Supplier Vendor",
        "supplier_vendor": "Supplier Vendor",
        "antenna type": " Antenna type",
        "antenna_type": " Antenna type",
        "antenna_serial_no": "antenna_serial_no",
        "item code": "Item code ",
        "item_code": "Item code ",
        "item_name": "item_name",
        "people": "people",
        "personal_id": "personal_id",
        "status": "status",
        "قطعه": "قطعه",
        "part": "قطعه",
        "parts": "قطعه",
        "electrical tilt": "Electrical tilt",
        "fixator": "Fixator",
        "roller": "Roller",
        "ret": "RET",
        "connector": "Connector",
        "radom door": "Radom door",
        "bracket removal": "Bracket Removal",
        "bracket": "Bracket Removal",
        "entery_date": "entery_date",
        "entry_date": "entery_date",
        "exit_date": "exit_date",
        "antenna_status": "antenna_status",
        "comment": "comment",
        "comments": "comment",
    }
    for col in df.columns:
        key = norm_lower(col)
        if key in canonical:
            rename[col] = canonical[key]
    if rename:
        df = df.rename(columns=rename)
    return df


def validate_excel_columns(df: pd.DataFrame) -> Optional[str]:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        labels = ", ".join(m.strip() for m in missing)
        return (
            "فرمت اکسل نامعتبر است — ستون‌های الزامی یافت نشد: "
            + labels
            + " (باید دقیقاً مطابق قالب «گزارش از 1405» باشد)"
        )
    return None


class ImportContext:
    def __init__(self, db: Session):
        self.db = db
        self.vendors = ci_map(
            [r.company_constructor for r in db.query(models.AntennaConstructor).all()]
        )
        self.types = ci_map([r.antenna_type for r in db.query(models.AntennaType).all()])
        self.items = ci_map([r.repair_item_name for r in db.query(models.RepairItem).all()])
        self.users = {u.personal_id: u for u in db.query(models.User).all()}
        self.assignments: Dict[Tuple[str, str, str], models.ItemCodeAssignment] = {}
        for a in db.query(models.ItemCodeAssignment).all():
            key = (
                norm_lower(a.manufacturer),
                norm_lower(a.antenna_type),
                norm_lower(a.item_code),
            )
            self.assignments[key] = a
        self.repair_cache: Dict[str, models.Repair] = {}
        self.step_cache: Dict[Tuple[int, str], models.RepairStep] = {}
        self.seen_row_sigs: Dict[str, int] = {}
        for repair in db.query(models.Repair).all():
            key = serial_key(repair.antenna_serial_no)
            if not key:
                continue
            current = self.repair_cache.get(key)
            if not current or (repair.repair_no or 0) < (current.repair_no or 0):
                self.repair_cache[key] = repair
        for s in db.query(models.RepairStep).all():
            sk = (s.repair_no, norm_lower(s.repair_item_name))
            if sk not in self.step_cache:
                self.step_cache[sk] = s

    def resolve_vendor(self, raw: str) -> Optional[str]:
        return self.vendors.get(norm_lower(raw))

    def resolve_type(self, raw: str) -> Optional[str]:
        return self.types.get(norm_lower(raw))

    def resolve_item(self, raw: str) -> Optional[str]:
        return self.items.get(norm_lower(raw))

    def resolve_assignment(self, vendor: str, atype: str, code: str) -> bool:
        key = (norm_lower(vendor), norm_lower(atype), norm_lower(code))
        return key in self.assignments

    def get_or_create_repair(
        self,
        serial: str,
        vendor: str,
        atype: str,
        item_code: str,
        entry_date: str,
    ) -> Tuple[models.Repair, Optional[str]]:
        serial = norm_serial(serial)
        key = serial_key(serial)
        if key in self.repair_cache:
            repair = self.repair_cache[key]
            changed = False
            if not repair.antenna_type and atype:
                repair.antenna_type = atype
                changed = True
            if not repair.item_code and item_code:
                repair.item_code = item_code
                changed = True
            if entry_date and (not repair.entry_date or repair.entry_date != entry_date):
                repair.entry_date = entry_date
                changed = True
            if changed:
                self.db.flush()
            if norm_lower(repair.constructor or "") != norm_lower(vendor):
                return (
                    repair,
                    (
                        f"سریال {serial} قبلاً با وندور «{repair.constructor or 'نامشخص'}» "
                        f"ثبت شده (تعمیر {repair.repair_no}) — گزارش به همان رکورد متصل شد"
                    ),
                )
            return repair, None

        existing = find_repair_by_serial(self.db, serial)
        if existing:
            self.repair_cache[key] = existing
            if entry_date and not existing.entry_date:
                existing.entry_date = entry_date
                self.db.flush()
            if norm_lower(existing.constructor or "") != norm_lower(vendor):
                return (
                    existing,
                    (
                        f"سریال {serial} قبلاً در سیستم با وندور «{existing.constructor or 'نامشخص'}» "
                        f"ثبت شده (تعمیر {existing.repair_no}) — گزارش به همان رکورد متصل شد"
                    ),
                )
            return existing, None

        repair = models.Repair(
            antenna_serial_no=serial,
            antenna_type=atype,
            antenna_entry_type="ورودی_تعمیر",
            constructor=vendor,
            entry_date=entry_date or None,
            item_code=item_code or None,
            antenna_status="نامعلوم",
        )
        self.db.add(repair)
        self.db.flush()
        self.repair_cache[key] = repair
        return repair, None

    def apply_antenna_status(self, repair: models.Repair, exit_date: str) -> None:
        """exit_date → وضعیت خروج + تاریخ خروج؛ بدون exit_date پیش‌فرض نامعلوم (خروج قبلی حفظ می‌شود)."""
        if exit_date:
            repair.exit_date = exit_date
            repair.antenna_status = "خروج"
            self.db.flush()
            return
        if (repair.antenna_status or "") != "خروج":
            repair.antenna_status = "نامعلوم"
            self.db.flush()

    def get_step(self, repair_no: int, item_name: str) -> Optional[models.RepairStep]:
        cached = self.step_cache.get((repair_no, norm_lower(item_name)))
        if cached:
            return cached
        step = (
            self.db.query(models.RepairStep)
            .filter(
                models.RepairStep.repair_no == repair_no,
                models.RepairStep.repair_item_name == item_name,
            )
            .first()
        )
        if step:
            self.step_cache[(repair_no, norm_lower(item_name))] = step
        return step

    def is_full_duplicate(
        self,
        repair: models.Repair,
        data: dict,
        fragment_name: Optional[str],
        used_quantity: Optional[int],
    ) -> bool:
        if norm_lower(repair.antenna_type or "") != norm_lower(data["atype"]):
            return False
        if norm_lower(repair.item_code or "") != norm_lower(data["item_code"]):
            return False

        frag = fragment_name or ""
        q = self.db.query(models.RepairItemReport).filter(
            models.RepairItemReport.repair_no == repair.repair_no,
            models.RepairItemReport.item_name == data["item_name"],
            models.RepairItemReport.personal_id == data["personal_id"],
            models.RepairItemReport.status == data["status"],
            models.RepairItemReport.antenna_serial_no == data["serial"],
            models.RepairItemReport.manufacturer == data["vendor"],
            models.RepairItemReport.first_name == data["first_name"],
            models.RepairItemReport.last_name == data["last_name"],
            models.RepairItemReport.repair_date == data["repair_date"],
        )
        if frag:
            q = q.filter(models.RepairItemReport.fragment_name == frag)
        else:
            q = q.filter(
                or_(
                    models.RepairItemReport.fragment_name.is_(None),
                    models.RepairItemReport.fragment_name == "",
                )
            )
        if used_quantity is None:
            q = q.filter(
                or_(
                    models.RepairItemReport.used_quantity.is_(None),
                )
            )
        else:
            q = q.filter(models.RepairItemReport.used_quantity == used_quantity)

        if not q.first():
            return False

        step = self.get_step(repair.repair_no, data["item_name"])
        if not step:
            return norm(data["start_date"]) == "" and norm(data["end_date"]) == ""

        if norm(step.start_date) != norm(data["start_date"]):
            return False

        end_excel = norm(data["end_date"])
        end_db = norm(step.end_date or "")
        if end_excel:
            return end_db == end_excel
        return not end_db or end_db == norm(data["start_date"])


def split_parts(parts_text: str) -> List[str]:
    if parts_text:
        chunks = [p.strip() for p in re.split(r"[-–—]", parts_text) if p.strip()]
        if chunks:
            return chunks
    return []


def collect_fragments(row: pd.Series) -> List[Tuple[Optional[str], Optional[int]]]:
    """Return list of (fragment_name, used_quantity) for separate report rows."""
    frags: List[Tuple[Optional[str], Optional[int]]] = []

    for chunk in split_parts(norm(row.get("قطعه"))):
        frags.append((chunk, None))

    for col, label in SPECIAL_QTY_COLUMNS:
        qty = parse_qty(row.get(col))
        if qty is not None:
            frags.append((label, qty))

    if not frags:
        frags.append((None, None))
    return frags


def validate_row(row: pd.Series, ctx: ImportContext) -> Tuple[Optional[dict], str]:
    reasons = []

    serial = norm_serial(row.get("antenna_serial_no"))
    vendor_raw = norm(row.get("Supplier Vendor"))
    atype_raw = norm(row.get(" Antenna type"))
    item_code = norm(row.get("Item code "))
    item_name_raw = norm(row.get("item_name"))
    start_date = parse_date(row.get("start_date"))
    end_date = parse_date(row.get("end_date"))
    entry_date = parse_date(row.get("entery_date")) or start_date
    exit_date = parse_date(row.get("exit_date"))
    personal_id = parse_personal_id(row.get("personal_id"))
    status = norm(row.get("status"))
    people = norm(row.get("people"))
    comment = norm(row.get("comment"))

    if not serial:
        reasons.append("شماره سریال آنتن خالی است")
    if not vendor_raw:
        reasons.append("Supplier Vendor خالی است")
    if not atype_raw:
        reasons.append("Antenna type خالی است")
    if not item_code:
        reasons.append("Item code خالی است")
    if not item_name_raw:
        reasons.append("item_name (نام آیتم تعمیری) خالی است")
    if not personal_id:
        reasons.append("personal_id نامعتبر یا خالی است")
    if not status:
        reasons.append("status خالی است")
    if not start_date:
        reasons.append("start_date خالی است")

    if reasons:
        return None, "؛ ".join(reasons)

    if status not in ALLOWED_ITEM_STATUSES:
        allowed = "، ".join(sorted(ALLOWED_ITEM_STATUSES))
        return None, f"وضعیت تعمیر «{status}» معتبر نیست (مجاز: {allowed})"

    vendor = ctx.resolve_vendor(vendor_raw)
    if not vendor:
        return None, f"وندور «{vendor_raw}» در جدول وندورها موجود نیست"

    atype = ctx.resolve_type(atype_raw)
    if not atype:
        return None, f"نوع آنتن «{atype_raw}» در دیتابیس موجود نیست"

    item_name = ctx.resolve_item(item_name_raw)
    if not item_name:
        return None, f"آیتم تعمیری «{item_name_raw}» در جدول repairItems موجود نیست"

    if not ctx.resolve_assignment(vendor, atype, item_code):
        return None, (
            f"آیتم‌کد «{item_code}» برای وندور «{vendor}» و نوع آنتن «{atype}» "
            f"در itemCodeAssignments یافت نشد (باید با دیتابیس سینک باشد)"
        )

    user = ctx.users.get(personal_id)
    if not user:
        return None, f"شماره پرسنلی {personal_id} در جدول کاربران موجود نیست"

    if people:
        full = f"{user.user_first_name or ''} {user.user_last_name or ''}".strip()
        if norm_person_name(people) != norm_person_name(full):
            return None, (
                f"نام «{people}» با کاربر شماره پرسنلی {personal_id} "
                f"(«{full}») در دیتابیس یکسان نیست"
            )

    repair_date = end_date or start_date
    fragments = collect_fragments(row)

    return {
        "serial": serial,
        "vendor": vendor,
        "atype": atype,
        "item_code": item_code,
        "item_name": item_name,
        "start_date": start_date,
        "end_date": end_date,
        "entry_date": entry_date,
        "exit_date": exit_date,
        "personal_id": personal_id,
        "first_name": user.user_first_name,
        "last_name": user.user_last_name,
        "status": status,
        "fragments": fragments,
        "repair_date": repair_date,
        "comment": comment or None,
    }, ""


def _report_signature(
    data: dict, fragment_name: Optional[str], used_quantity: Optional[int]
) -> str:
    return "\u0001".join(
        [
            serial_key(data["serial"]),
            norm_lower(data["item_name"]),
            str(data["personal_id"]),
            norm_lower(data["status"]),
            norm_lower(data["vendor"]),
            norm(data["repair_date"]),
            norm_lower(fragment_name or ""),
            "" if used_quantity is None else str(used_quantity),
            norm(data["start_date"]),
            norm(data["end_date"]),
            norm(data.get("comment") or ""),
        ]
    )


def _duplicate_reason(row_no: int, dup_rows: set, dup_in_db: bool) -> str:
    parts: List[str] = []
    if dup_rows:
        rows_txt = "، ".join(str(r) for r in sorted(dup_rows))
        parts.append(f"عیناً با ردیف {rows_txt} همین فایل اکسل یکسان است (همان ردیف وارد شد)")
    if dup_in_db:
        parts.append("این رکورد قبلاً در سیستم ثبت شده بود")
    detail = "؛ ".join(parts) if parts else "همهٔ ستون‌ها تکراری بودند"
    return f"رکورد تکراری ردیف {row_no} وارد نشد — {detail}"


def import_row(row_no: int, row: pd.Series, ctx: ImportContext) -> Tuple[str, str]:
    data, reason = validate_row(row, ctx)
    if not data:
        return "failed", reason

    repair, serial_note = ctx.get_or_create_repair(
        data["serial"],
        data["vendor"],
        data["atype"],
        data["item_code"],
        data["entry_date"],
    )
    ctx.apply_antenna_status(repair, data["exit_date"])

    fragments: List[Tuple[Optional[str], Optional[int]]] = data["fragments"]

    fresh: List[Tuple[Optional[str], Optional[int]]] = []
    dup_rows: set = set()
    dup_in_db = False
    for fragment_name, used_quantity in fragments:
        sig = _report_signature(data, fragment_name, used_quantity)
        prev_row = ctx.seen_row_sigs.get(sig)
        if prev_row is not None:
            dup_rows.add(prev_row)
            continue
        if ctx.is_full_duplicate(repair, data, fragment_name, used_quantity):
            dup_in_db = True
            continue
        fresh.append((fragment_name, used_quantity))

    if not fresh:
        return "skipped", _duplicate_reason(row_no, dup_rows, dup_in_db)

    step = ctx.get_step(repair.repair_no, data["item_name"])
    if not step:
        step = models.RepairStep(
            repair_no=repair.repair_no,
            repair_item_name=data["item_name"],
            item_status=data["status"],
            personal_id=data["personal_id"],
            start_date=data["start_date"],
            end_date=data["end_date"] or None,
            item_code=data["item_code"],
        )
        ctx.db.add(step)
        ctx.db.flush()
        ctx.step_cache[(repair.repair_no, norm_lower(data["item_name"]))] = step
    else:
        step.item_status = data["status"]
        step.personal_id = data["personal_id"]
        step.start_date = data["start_date"]
        if data["end_date"]:
            step.end_date = data["end_date"]
        step.item_code = data["item_code"]

    imported = 0
    for fragment_name, used_quantity in fresh:
        ctx.db.add(
            models.RepairItemReport(
                repair_no=repair.repair_no,
                antenna_serial_no=data["serial"],
                manufacturer=data["vendor"],
                personal_id=data["personal_id"],
                first_name=data["first_name"],
                last_name=data["last_name"],
                item_name=data["item_name"],
                fragment_name=fragment_name,
                fragment_part_no=None,
                arsenal_name=None,
                used_quantity=used_quantity,
                status=data["status"],
                final_status="در انتظار",
                repair_date=data["repair_date"],
                item_description=data.get("comment"),
            )
        )
        ctx.seen_row_sigs[_report_signature(data, fragment_name, used_quantity)] = row_no
        imported += 1

    notes: List[str] = []
    if serial_note:
        notes.append(serial_note)
    if dup_rows or dup_in_db:
        skipped_bits: List[str] = []
        if dup_rows:
            rows_txt = "، ".join(str(r) for r in sorted(dup_rows))
            skipped_bits.append(f"تکراری با ردیف {rows_txt}")
        if dup_in_db:
            skipped_bits.append("تکراری با رکورد موجود در سیستم")
        notes.append(
            f"{imported} قطعهٔ جدید وارد شد؛ بخشی از قطعات نادیده گرفته شد ("
            + "؛ ".join(skipped_bits)
            + ")"
        )

    return "imported", "؛ ".join(notes)


def import_repair_reports_from_excel(db: Session, file_bytes: bytes) -> dict:
    df = pd.read_excel(BytesIO(file_bytes))
    df = normalize_dataframe(df)

    col_error = validate_excel_columns(df)
    if col_error:
        return {
            "total": 0,
            "imported": 0,
            "failed": 0,
            "skipped": 0,
            "issues": [{"row_no": 0, "reason": col_error, "result": "failed"}],
        }

    # Drop completely empty data rows
    df = df.dropna(how="all")

    ctx = ImportContext(db)
    imported = failed = skipped = 0
    issues: List[dict] = []

    batch = 500
    for idx, row in df.iterrows():
        # Skip rows without serial
        if not norm(row.get("antenna_serial_no")):
            continue
        row_no = (
            int(row["No"])
            if "No" in df.columns and pd.notna(row.get("No"))
            else int(idx) + 1
        )
        status, reason = import_row(row_no, row, ctx)
        if status == "imported":
            imported += 1
            if reason:
                issues.append({"row_no": row_no, "reason": reason, "result": "warning"})
        elif status == "failed":
            failed += 1
            issues.append({"row_no": row_no, "reason": reason, "result": "failed"})
        else:
            skipped += 1
            issues.append({"row_no": row_no, "reason": reason, "result": "skipped"})

        if (imported + failed + skipped) % batch == 0:
            db.commit()

    db.commit()

    return {
        "total": imported + failed + skipped,
        "imported": imported,
        "failed": failed,
        "skipped": skipped,
        "issues": issues,
    }
