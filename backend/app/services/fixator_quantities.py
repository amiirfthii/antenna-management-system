#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bulk utility for fixator (فیکساتور) quantities in repair item reports.
Maps antenna type + vendor + band (900/1800) to warehouse parts and deducts inventory.
"""

from collections import Counter
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db import models
from app.services.tilt_electric_quantities import (
    DEFAULT_ARSENAL_NAME,
    _adjust_usage_qty,
    _available_qty,
    _deduct_inventory,
    _get_usage_qty,
    _lookup_arsenal,
    _normalize_text,
    _restore_inventory,
    _skipped_record,
)

ALL_FIXATOR_PARTS = {
    "2X-K-900",
    "2X-K-1800",
    "2X-14/17-K-900",
    "2X-14/17-K-1800",
    "3X-H-900",
    "3X-H-1800-B",
    "3X-H-1800-S",
    "3X-K-900",
    "3X-K-1800-B",
    "3X-K-1800-S",
}


def _norm_type(antenna_type: str) -> str:
    return (antenna_type or "").strip().upper().replace(" ", "")


def _is_2x_14_17(antenna_type: str) -> bool:
    t = _norm_type(antenna_type)
    return "2X-14/17" in t or "2X14/17" in t.replace("-", "")


def _is_2x_generic(antenna_type: str) -> bool:
    t = _norm_type(antenna_type)
    return "2X" in t and not _is_2x_14_17(antenna_type)


def _is_3x(antenna_type: str) -> bool:
    return "3X" in _norm_type(antenna_type)


def _vendor_family(vendor: str) -> Optional[str]:
    v = (vendor or "").strip().lower()
    if "huawei" in v or "هوا" in v:
        return "huawei"
    if "kathrein" in v or "kathrain" in v or "کاتر" in v:
        return "kathrein"
    return None


def _fragment_fixator_band(fragment_name: str) -> Optional[str]:
    raw = (fragment_name or "").strip()
    if not raw:
        return None
    name = _normalize_text(raw)
    raw_lower = raw.lower()
    if "فیکساتور" not in raw and "fixator" not in raw_lower:
        return None
    if "1800" in name or "1800" in raw_lower or "۱۸۰۰" in raw:
        return "1800"
    if "900" in name or "900" in raw_lower or "۹۰۰" in raw:
        return "900"
    return None


def _should_process_fixator_report(report: models.RepairItemReport) -> bool:
    return _fragment_fixator_band(report.fragment_name or "") is not None


def _companion_part(part_no: str) -> Optional[str]:
    if part_no.endswith("-B"):
        return f"{part_no[:-2]}-S"
    if part_no.endswith("-S"):
        return f"{part_no[:-2]}-B"
    return None


def _resolve_fixator_plan(
    antenna_type: Optional[str],
    vendor: Optional[str],
    band: str,
) -> Tuple[List[Tuple[str, int]], int, Optional[str]]:
    if not antenna_type:
        return [], 0, "نوع آنتن یافت نشد"

    if _is_2x_14_17(antenna_type):
        if band == "900":
            return [("2X-14/17-K-900", 1)], 1, None
        if band == "1800":
            return [("2X-14/17-K-1800", 1)], 1, None
        return [], 0, "باند فیکساتور (900/1800) نامعتبر است"

    if _is_2x_generic(antenna_type):
        if band == "900":
            return [("2X-K-900", 1)], 1, None
        if band == "1800":
            return [("2X-K-1800", 1)], 1, None
        return [], 0, "باند فیکساتور (900/1800) نامعتبر است"

    if _is_3x(antenna_type):
        family = _vendor_family(vendor or "")
        if not family:
            return [], 0, "وندور 3X باید Huawei یا Kathrein باشد"
        if family == "huawei":
            if band == "900":
                return [("3X-H-900", 1)], 1, None
            if band == "1800":
                return [("3X-H-1800-B", 1), ("3X-H-1800-S", 1)], 2, None
        else:
            if band == "900":
                return [("3X-K-900", 1)], 1, None
            if band == "1800":
                return [("3X-K-1800-B", 1), ("3X-K-1800-S", 1)], 2, None
        return [], 0, "باند فیکساتور (900/1800) نامعتبر است"

    return [], 0, "نوع آنتن برای فیکساتور پشتیبانی نمی‌شود (2X / 2X-14/17 / 3X)"


def _parts_already_synced(
    db: Session,
    report: models.RepairItemReport,
    parts: List[Tuple[str, int]],
    total_qty: int,
    usage_registry: Dict,
) -> bool:
    if not report.repair_no or not report.item_name:
        return False

    primary_part = parts[0][0]
    if (report.fragment_part_no or "").strip() != primary_part:
        return False
    if (report.used_quantity or 0) != total_qty:
        return False
    if (report.arsenal_name or DEFAULT_ARSENAL_NAME).strip() != DEFAULT_ARSENAL_NAME:
        return False

    for part_no, qty in parts:
        usage_qty = _get_usage_qty(
            db,
            report.repair_no,
            report.item_name,
            part_no,
            DEFAULT_ARSENAL_NAME,
            usage_registry,
        )
        if usage_qty < qty:
            return False
    return True


def _restore_report_consumption(
    db: Session,
    report: models.RepairItemReport,
    usage_registry: Dict,
) -> bool:
    if not report.repair_no or not report.item_name:
        return False

    old_part = (report.fragment_part_no or "").strip()
    old_qty = report.used_quantity or 0
    old_arsenal = (report.arsenal_name or DEFAULT_ARSENAL_NAME).strip()
    if not old_part or old_qty <= 0 or old_part not in ALL_FIXATOR_PARTS:
        return False

    changed = False
    if old_qty == 2:
        companion = _companion_part(old_part)
        if companion:
            if _restore_inventory(db, old_part, old_arsenal, 1):
                changed = True
            _adjust_usage_qty(
                db, report.repair_no, report.item_name,
                old_part, old_arsenal, -1, usage_registry,
            )
            if _restore_inventory(db, companion, old_arsenal, 1):
                changed = True
            _adjust_usage_qty(
                db, report.repair_no, report.item_name,
                companion, old_arsenal, -1, usage_registry,
            )
            return changed

    if _restore_inventory(db, old_part, old_arsenal, old_qty):
        changed = True
    _adjust_usage_qty(
        db, report.repair_no, report.item_name,
        old_part, old_arsenal, -old_qty, usage_registry,
    )
    return changed


def _apply_fixator_to_report(
    db: Session,
    report: models.RepairItemReport,
    antenna_type: Optional[str],
    vendor: Optional[str],
    usage_registry: Dict,
) -> Tuple[bool, bool, Optional[str]]:
    band = _fragment_fixator_band(report.fragment_name or "")
    if not band:
        return False, False, "باند فیکساتور (900/1800) در قطعه شناسایی نشد"

    parts, total_qty, reason = _resolve_fixator_plan(antenna_type, vendor, band)
    if reason:
        return False, False, reason

    for part_no, _qty in parts:
        if not _lookup_arsenal(db, part_no, DEFAULT_ARSENAL_NAME):
            return False, False, f"قطعه {part_no} در انبار «{DEFAULT_ARSENAL_NAME}» یافت نشد"

    if _parts_already_synced(db, report, parts, total_qty, usage_registry):
        return False, False, None

    for part_no, qty in parts:
        avail = _available_qty(db, part_no, DEFAULT_ARSENAL_NAME)
        if avail is not None and avail < qty:
            return False, False, (
                f"موجودی انبار «{DEFAULT_ARSENAL_NAME}» برای قطعه {part_no} "
                f"کافی نیست (موجودی: {avail}، نیاز: {qty})"
            )

    inventory_changed = _restore_report_consumption(db, report, usage_registry)

    primary_part = parts[0][0]
    primary_arsenal = _lookup_arsenal(db, primary_part, DEFAULT_ARSENAL_NAME)
    if not primary_arsenal:
        return False, inventory_changed, f"قطعه {primary_part} در انبار یافت نشد"

    for part_no, qty in parts:
        if _deduct_inventory(db, part_no, DEFAULT_ARSENAL_NAME, qty):
            inventory_changed = True
        if report.repair_no and report.item_name:
            _adjust_usage_qty(
                db,
                report.repair_no,
                report.item_name,
                part_no,
                DEFAULT_ARSENAL_NAME,
                qty,
                usage_registry,
            )

    report.fragment_part_no = primary_part
    report.fragment_name = primary_arsenal.fragment_name
    report.arsenal_name = DEFAULT_ARSENAL_NAME
    report.used_quantity = total_qty
    return True, inventory_changed, None


def apply_fixator_quantities(db: Session) -> Dict[str, object]:
    updated = 0
    skipped = 0
    unchanged = 0
    inventory_adjusted = 0
    skip_reasons: Counter = Counter()
    skipped_records: List[Dict[str, object]] = []
    usage_registry: Dict = {}

    reports = [
        r for r in db.query(models.RepairItemReport).all()
        if _should_process_fixator_report(r)
    ]

    repair_nos = {r.repair_no for r in reports if r.repair_no}
    repairs_by_no: Dict[int, models.Repair] = {}
    if repair_nos:
        for repair in db.query(models.Repair).filter(
            models.Repair.repair_no.in_(repair_nos)
        ).all():
            repairs_by_no[repair.repair_no] = repair

    for report in reports:
        repair = repairs_by_no.get(report.repair_no) if report.repair_no else None
        antenna_type = repair.antenna_type if repair else None
        vendor = (repair.constructor if repair else None) or report.manufacturer

        ok, inv_changed, reason = _apply_fixator_to_report(
            db, report, antenna_type, vendor, usage_registry,
        )
        if reason:
            skipped += 1
            skip_reasons[reason] += 1
            skipped_records.append(
                _skipped_record(report, repair, reason, item_code=(repair.item_code if repair else None))
            )
            continue
        if ok:
            updated += 1
            if inv_changed:
                inventory_adjusted += 1
        else:
            unchanged += 1

    db.commit()

    reasons_list = [
        {"reason": reason, "count": count}
        for reason, count in skip_reasons.most_common()
    ]

    return {
        "updated": updated,
        "skipped": skipped,
        "unchanged": unchanged,
        "inventory_adjusted": inventory_adjusted,
        "skip_reasons": reasons_list,
        "skipped_records": skipped_records,
    }
