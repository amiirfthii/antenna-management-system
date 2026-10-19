#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bulk utility for correcting electric-tilt consumption in repair item reports.
Selects rows by fragment/part (900 or 1800 MHz tilt), not by repair item name.
Does NOT alter the normal repair submission flow (submit-items).
"""

import re
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.db import models

DEFAULT_ARSENAL_NAME = "نو"

TILT_QUANTITY_RULES: Dict[str, Dict[str, int]] = {
    "M100013287": {"1800": 2, "900": 1},
    "M100011073": {"1800": 1, "900": 1},
    "M100015236": {"1800": 1, "900": 1},
    "M100010412": {"1800": 2, "900": 1},
    "M100013127": {"900": 1},
    "M100018747": {"900": 1},
    "M100012045": {"900": 1},
}

INVENTORY_PART_MAP: Dict[str, Dict[str, str]] = {
    "M100011073": {"900": "TIM0082.07", "1800": "TIM0082.50"},
    "M100015236": {"900": "TIM0082.07", "1800": "TIM0082.50"},
    "M100010412": {"900": "TIM0082.02", "1800": "TIM0082.51"},
    "M100013287": {"900": "TIM0082.08", "1800": "TIM0082.52"},
    "M100018747": {"900": "TIM0082.07", "1800": "TIM0082.50"},
    "M100012045": {"900": "TIM0082.07", "1800": "TIM0082.50"},
}

PART_BAND_HINTS: Dict[str, str] = {
    "TIM0082.07": "900",
    "TIM0082.02": "900",
    "TIM0082.08": "900",
    "TIM0082.50": "1800",
    "TIM0082.51": "1800",
    "TIM0082.52": "1800",
}

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def _normalize_text(value: str) -> str:
    text = (value or "").strip().translate(_PERSIAN_DIGITS)
    text = text.replace("\u200c", "").replace(" ", "").replace("‌", "")
    return text.lower()


def _fragment_tilt_band(fragment_name: str, fragment_part_no: str = "") -> Optional[str]:
    raw = (fragment_name or "").strip()
    part = (fragment_part_no or "").strip()
    name = _normalize_text(raw)
    raw_lower = raw.lower()

    if part in PART_BAND_HINTS:
        return PART_BAND_HINTS[part]

    if "1800" in name or "1800" in raw_lower or "۱۸۰۰" in raw:
        return "1800"
    if "900" in name or "900" in raw_lower or "۹۰۰" in raw:
        return "900"

    if "3x-h" in name or "3x-h" in raw_lower:
        if "1800" in name or "1800" in raw_lower:
            return "1800"
        if "900" in name or "900" in raw_lower:
            return "900"
    if "2x-k" in name or "2x-k" in raw_lower:
        if "1800" in name or "1800" in raw_lower:
            return "1800"
        if "900" in name or "900" in raw_lower:
            return "900"
    if "4x-k" in name or "4x-k" in raw_lower:
        if "1800" in name or "1800" in raw_lower:
            return "1800"
        if "900" in name or "900" in raw_lower:
            return "900"

    if "نصبتیلتالکتریکال1800" in name or "الکتریکال1800" in name:
        return "1800"
    if "نصبتیلتالکتریکال900" in name or "الکتریکال900" in name:
        return "900"

    return None


def _should_process_tilt_report(report: models.RepairItemReport) -> bool:
    """Include report when fragment/part shows electric tilt 900/1800 — ignore item_name."""
    fragment_name = report.fragment_name or ""
    fragment_part_no = (report.fragment_part_no or "").strip()

    if _fragment_tilt_band(fragment_name, fragment_part_no):
        return True

    if fragment_part_no in PART_BAND_HINTS:
        return True

    name = _normalize_text(fragment_name)
    raw_lower = fragment_name.lower()

    if "تیلت" in fragment_name or "tilt" in raw_lower:
        if (
            "900" in name
            or "900" in raw_lower
            or "۱۸۰۰" in fragment_name
            or "1800" in name
            or "1800" in raw_lower
            or "الکتریک" in name
            or "electric" in raw_lower
        ):
            return True

    return False


def _infer_bands_for_repair(
    reports: List[models.RepairItemReport],
    item_code: str,
) -> Dict[int, str]:
    rules = TILT_QUANTITY_RULES.get(item_code, {})
    assigned: Dict[int, str] = {}
    unknown: List[models.RepairItemReport] = []

    for report in reports:
        band = _fragment_tilt_band(report.fragment_name or "", report.fragment_part_no or "")
        if band:
            assigned[report.id] = band
        else:
            unknown.append(report)

    if not unknown:
        return assigned

    needed = [band for band in ("900", "1800") if band in rules]
    unknown.sort(key=lambda r: r.id)

    if len(unknown) == 1 and len(needed) == 1:
        assigned[unknown[0].id] = needed[0]
        return assigned

    if len(unknown) == 2 and "900" in needed and "1800" in needed:
        assigned[unknown[0].id] = "900"
        assigned[unknown[1].id] = "1800"
        return assigned

    return assigned


def _build_band_map(
    reports: List[models.RepairItemReport],
    repairs_by_no: Dict[int, models.Repair],
) -> Dict[int, str]:
    by_repair: Dict[int, List[models.RepairItemReport]] = defaultdict(list)
    for report in reports:
        if report.repair_no:
            by_repair[report.repair_no].append(report)

    band_map: Dict[int, str] = {}
    for repair_no, group in by_repair.items():
        repair = repairs_by_no.get(repair_no)
        item_code = (repair.item_code or "").strip() if repair else ""
        if not item_code:
            continue
        inferred = _infer_bands_for_repair(group, item_code)
        band_map.update(inferred)
    return band_map


def _lookup_arsenal(
    db: Session,
    part_no: str,
    arsenal_name: str = DEFAULT_ARSENAL_NAME,
) -> Optional[models.ArsenalTable]:
    return db.query(models.ArsenalTable).filter(
        models.ArsenalTable.fragment_part_no == part_no,
        models.ArsenalTable.arsenal_name == arsenal_name,
    ).first()


def _available_qty(db: Session, part_no: str, arsenal_name: str) -> Optional[int]:
    """موجودی فعلی قطعه در انبار؛ None یعنی قطعه/انبار تعریف نشده."""
    arsenal = _lookup_arsenal(db, part_no, arsenal_name)
    if not arsenal:
        return None
    return int(arsenal.fragment_qty or 0)


def _deduct_inventory(db: Session, part_no: str, arsenal_name: str, qty: int) -> bool:
    """کسر از انبار به‌صورت واقعی؛ اگر موجودی کافی نبود، هیچ تغییری نمی‌دهد
    و False برمی‌گرداند (دیگر موجودی را به‌صورت ساختگی افزایش نمی‌دهیم)."""
    if qty <= 0:
        return False
    arsenal = _lookup_arsenal(db, part_no, arsenal_name)
    if not arsenal:
        return False
    if (arsenal.fragment_qty or 0) < qty:
        return False
    arsenal.fragment_qty -= qty
    return True


def _restore_inventory(db: Session, part_no: str, arsenal_name: str, qty: int) -> bool:
    if qty <= 0 or not part_no or not arsenal_name:
        return False
    arsenal = _lookup_arsenal(db, part_no, arsenal_name)
    if not arsenal:
        return False
    arsenal.fragment_qty += qty
    return True


def _usage_key(repair_no: int, item_name: str, part_no: str, arsenal_name: str) -> Tuple[int, str, str, str]:
    return (repair_no, item_name, part_no, arsenal_name)


def _get_usage_qty(
    db: Session,
    repair_no: int,
    item_name: str,
    part_no: str,
    arsenal_name: str,
    registry: Dict[Tuple[int, str, str, str], models.UserSupplyUsage],
) -> int:
    key = _usage_key(repair_no, item_name, part_no, arsenal_name)
    if key in registry:
        return registry[key].repair_fragment_qty or 0
    usage = db.query(models.UserSupplyUsage).filter(
        models.UserSupplyUsage.repair_no == repair_no,
        models.UserSupplyUsage.repair_item_name == item_name,
        models.UserSupplyUsage.fragment_part_no == part_no,
        models.UserSupplyUsage.arsenal_name == arsenal_name,
    ).first()
    return (usage.repair_fragment_qty or 0) if usage else 0


def _get_or_create_usage(
    db: Session,
    repair_no: int,
    item_name: str,
    part_no: str,
    arsenal_name: str,
    registry: Dict[Tuple[int, str, str, str], models.UserSupplyUsage],
) -> models.UserSupplyUsage:
    key = _usage_key(repair_no, item_name, part_no, arsenal_name)
    if key in registry:
        return registry[key]

    usage = db.query(models.UserSupplyUsage).filter(
        models.UserSupplyUsage.repair_no == repair_no,
        models.UserSupplyUsage.repair_item_name == item_name,
        models.UserSupplyUsage.fragment_part_no == part_no,
        models.UserSupplyUsage.arsenal_name == arsenal_name,
    ).first()

    if not usage:
        usage = models.UserSupplyUsage(
            repair_no=repair_no,
            repair_item_name=item_name,
            fragment_part_no=part_no,
            arsenal_name=arsenal_name,
            repair_fragment_qty=0,
        )
        db.add(usage)

    registry[key] = usage
    return usage


def _adjust_usage_qty(
    db: Session,
    repair_no: int,
    item_name: str,
    part_no: str,
    arsenal_name: str,
    delta: int,
    registry: Dict[Tuple[int, str, str, str], models.UserSupplyUsage],
) -> None:
    if delta == 0 or not repair_no or not item_name or not part_no or not arsenal_name:
        return

    key = _usage_key(repair_no, item_name, part_no, arsenal_name)

    if delta > 0:
        usage = _get_or_create_usage(db, repair_no, item_name, part_no, arsenal_name, registry)
        usage.repair_fragment_qty = (usage.repair_fragment_qty or 0) + delta
        return

    usage = registry.get(key)
    if usage is None:
        usage = db.query(models.UserSupplyUsage).filter(
            models.UserSupplyUsage.repair_no == repair_no,
            models.UserSupplyUsage.repair_item_name == item_name,
            models.UserSupplyUsage.fragment_part_no == part_no,
            models.UserSupplyUsage.arsenal_name == arsenal_name,
        ).first()
        if usage:
            registry[key] = usage

    if not usage:
        return

    new_qty = (usage.repair_fragment_qty or 0) + delta
    if new_qty <= 0:
        db.delete(usage)
        registry.pop(key, None)
    else:
        usage.repair_fragment_qty = new_qty


def _resolve_targets(
    item_code: str,
    band: str,
) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    qty_rules = TILT_QUANTITY_RULES.get(item_code)
    if not qty_rules:
        return None, None, f"آیتم‌کد {item_code} در قوانین تیلت تعریف نشده"

    target_qty = qty_rules.get(band)
    if target_qty is None:
        return None, None, f"برای آیتم‌کد {item_code} و قطعه {band} قانون تعداد تعریف نشده"

    part_map = INVENTORY_PART_MAP.get(item_code)
    if not part_map:
        return None, None, f"قطعه انبار برای آیتم‌کد {item_code} تعریف نشده"

    target_part = part_map.get(band)
    if not target_part:
        return None, None, f"قطعه انبار برای آیتم‌کد {item_code} و باند {band} تعریف نشده"

    return target_qty, target_part, None


def _skipped_record(
    report: models.RepairItemReport,
    repair: Optional[models.Repair],
    reason: str,
    item_code: str = "",
) -> Dict[str, object]:
    return {
        "id": report.id,
        "repair_no": report.repair_no,
        "antenna_serial_no": report.antenna_serial_no or (repair.antenna_serial_no if repair else None),
        "antenna_type": repair.antenna_type if repair else None,
        "manufacturer": report.manufacturer or (repair.constructor if repair else None),
        "item_code": item_code or None,
        "fragment_name": report.fragment_name,
        "reason": reason,
    }


def _clone_report_for_band(source: models.RepairItemReport) -> models.RepairItemReport:
    return models.RepairItemReport(
        repair_no=source.repair_no,
        antenna_serial_no=source.antenna_serial_no,
        manufacturer=source.manufacturer,
        personal_id=source.personal_id,
        first_name=source.first_name,
        last_name=source.last_name,
        item_name=source.item_name,
        status=source.status,
        final_status=source.final_status or "در انتظار",
        repair_date=source.repair_date,
    )


def _apply_band_to_report(
    db: Session,
    report: models.RepairItemReport,
    item_code: str,
    band: str,
    usage_registry: Dict[Tuple[int, str, str, str], models.UserSupplyUsage],
) -> Tuple[bool, bool, Optional[str]]:
    """Update one report row and sync inventory.

    Returns (updated, inventory_changed, reason). اگر reason پر باشد یعنی
    کاری انجام نشد و دلیلش مشخص است (قانون/قطعه تعریف نشده یا موجودی کافی نیست).
    """
    target_qty, target_part, reason = _resolve_targets(item_code, band)
    if reason:
        return False, False, reason

    target_arsenal = _lookup_arsenal(db, target_part, DEFAULT_ARSENAL_NAME)
    if not target_arsenal:
        return False, False, (
            f"قطعه {target_part} در انبار «{DEFAULT_ARSENAL_NAME}» تعریف نشده"
        )

    old_qty = report.used_quantity or 0
    old_part = (report.fragment_part_no or "").strip()
    old_arsenal = (report.arsenal_name or DEFAULT_ARSENAL_NAME).strip()
    inventory_changed = False

    usage_qty = 0
    if report.repair_no and report.item_name:
        usage_qty = _get_usage_qty(
            db, report.repair_no, report.item_name,
            target_part, DEFAULT_ARSENAL_NAME, usage_registry,
        )

    fields_ok = (
        old_qty == target_qty
        and old_part == target_part
        and old_arsenal == DEFAULT_ARSENAL_NAME
    )
    if fields_ok and usage_qty >= target_qty:
        return False, False, None

    if fields_ok and usage_qty < target_qty:
        missing = target_qty - usage_qty
        avail = _available_qty(db, target_part, DEFAULT_ARSENAL_NAME)
        if avail is not None and avail < missing:
            return False, False, (
                f"موجودی انبار «{DEFAULT_ARSENAL_NAME}» برای قطعه {target_part} "
                f"کافی نیست (موجودی: {avail}، نیاز: {missing})"
            )
        if _deduct_inventory(db, target_part, DEFAULT_ARSENAL_NAME, missing):
            inventory_changed = True
        if report.repair_no and report.item_name:
            _adjust_usage_qty(
                db, report.repair_no, report.item_name,
                target_part, DEFAULT_ARSENAL_NAME, missing, usage_registry,
            )
        report.fragment_name = target_arsenal.fragment_name
        return True, inventory_changed, None

    # از این نقطه به بعد در نهایت target_qty از انبار کسر می‌شود؛ ابتدا موجودی را بررسی کن.
    avail = _available_qty(db, target_part, DEFAULT_ARSENAL_NAME)
    net_need = target_qty
    if old_part == target_part and old_arsenal == DEFAULT_ARSENAL_NAME:
        net_need = max(0, target_qty - old_qty)
    if avail is not None and avail < net_need:
        return False, False, (
            f"موجودی انبار «{DEFAULT_ARSENAL_NAME}» برای قطعه {target_part} "
            f"کافی نیست (موجودی: {avail}، نیاز: {net_need})"
        )

    if old_part and old_qty > 0 and (old_part != target_part or old_arsenal != DEFAULT_ARSENAL_NAME):
        if _restore_inventory(db, old_part, old_arsenal, old_qty):
            inventory_changed = True
        if report.repair_no and report.item_name:
            _adjust_usage_qty(
                db, report.repair_no, report.item_name,
                old_part, old_arsenal, -old_qty, usage_registry,
            )
        if _deduct_inventory(db, target_part, DEFAULT_ARSENAL_NAME, target_qty):
            inventory_changed = True
        if report.repair_no and report.item_name:
            _adjust_usage_qty(
                db, report.repair_no, report.item_name,
                target_part, DEFAULT_ARSENAL_NAME, target_qty, usage_registry,
            )
    elif old_part == target_part and old_arsenal == DEFAULT_ARSENAL_NAME and old_qty != target_qty:
        delta = target_qty - old_qty
        if delta > 0:
            if _deduct_inventory(db, target_part, DEFAULT_ARSENAL_NAME, delta):
                inventory_changed = True
        elif delta < 0:
            if _restore_inventory(db, target_part, DEFAULT_ARSENAL_NAME, -delta):
                inventory_changed = True
        if report.repair_no and report.item_name:
            _adjust_usage_qty(
                db, report.repair_no, report.item_name,
                target_part, DEFAULT_ARSENAL_NAME, delta, usage_registry,
            )
    else:
        if _deduct_inventory(db, target_part, DEFAULT_ARSENAL_NAME, target_qty):
            inventory_changed = True
        if report.repair_no and report.item_name:
            _adjust_usage_qty(
                db, report.repair_no, report.item_name,
                target_part, DEFAULT_ARSENAL_NAME, target_qty, usage_registry,
            )

    report.fragment_part_no = target_part
    report.fragment_name = target_arsenal.fragment_name
    report.arsenal_name = DEFAULT_ARSENAL_NAME
    report.used_quantity = target_qty

    return True, inventory_changed, None


def _apply_dual_band_for_repair(
    db: Session,
    trigger_report: models.RepairItemReport,
    item_code: str,
    usage_registry: Dict[Tuple[int, str, str, str], models.UserSupplyUsage],
    processed_ids: Set[int],
) -> Tuple[int, int, List[Tuple[models.RepairItemReport, str]]]:
    """M100010412-style: one import row → both 900 and 1800 parts consumed."""
    repair_no = trigger_report.repair_no
    if not repair_no:
        return 0, 0, []

    rules = TILT_QUANTITY_RULES.get(item_code, {})
    if "900" not in rules or "1800" not in rules:
        return 0, 0, []

    siblings = [
        s
        for s in db.query(models.RepairItemReport)
        .filter(models.RepairItemReport.repair_no == repair_no)
        .order_by(models.RepairItemReport.id)
        .all()
        if _should_process_tilt_report(s)
    ]

    if not siblings:
        return 0, 0, []

    if any(_fragment_tilt_band(s.fragment_name or "", s.fragment_part_no or "") for s in siblings):
        return 0, 0, []

    if any(s.id in processed_ids for s in siblings):
        return 0, 0, []

    updated = 0
    inv = 0
    reasons: List[Tuple[models.RepairItemReport, str]] = []
    report_for_900 = siblings[0]
    report_for_1800 = siblings[1] if len(siblings) >= 2 else None

    ok, changed, reason = _apply_band_to_report(db, report_for_900, item_code, "900", usage_registry)
    if ok:
        updated += 1
        processed_ids.add(report_for_900.id)
    elif reason:
        reasons.append((report_for_900, reason))
    if changed:
        inv += 1

    if report_for_1800 is None:
        report_for_1800 = _clone_report_for_band(trigger_report)
        db.add(report_for_1800)
        db.flush()

    ok, changed, reason = _apply_band_to_report(db, report_for_1800, item_code, "1800", usage_registry)
    if ok:
        updated += 1
        processed_ids.add(report_for_1800.id)
    elif reason:
        reasons.append((report_for_1800, reason))
    if changed:
        inv += 1

    return updated, inv, reasons


def _sync_reports_with_parts(
    db: Session,
    usage_registry: Dict[Tuple[int, str, str, str], models.UserSupplyUsage],
) -> Tuple[int, int]:
    """Deduct inventory for reports that already have part_no + used_quantity."""
    reports = db.query(models.RepairItemReport).filter(
        models.RepairItemReport.fragment_part_no.isnot(None),
        models.RepairItemReport.fragment_part_no != "",
        models.RepairItemReport.arsenal_name.isnot(None),
        models.RepairItemReport.used_quantity.isnot(None),
        models.RepairItemReport.used_quantity > 0,
    ).all()
    reports = [r for r in reports if _should_process_tilt_report(r)]

    updated = 0
    inv = 0
    for report in reports:
        part = (report.fragment_part_no or "").strip()
        arsenal = (report.arsenal_name or DEFAULT_ARSENAL_NAME).strip()
        qty = report.used_quantity or 0
        if not report.repair_no or not report.item_name or not part:
            continue

        usage_qty = _get_usage_qty(
            db, report.repair_no, report.item_name, part, arsenal, usage_registry,
        )
        if usage_qty >= qty:
            continue

        missing = qty - usage_qty
        if _deduct_inventory(db, part, arsenal, missing):
            inv += 1
        _adjust_usage_qty(
            db, report.repair_no, report.item_name, part, arsenal, missing, usage_registry,
        )
        updated += 1

    return updated, inv


def apply_tilt_electric_quantities(db: Session) -> Dict[str, object]:
    updated = 0
    skipped = 0
    unchanged = 0
    inventory_adjusted = 0
    skip_reasons: Counter = Counter()
    skipped_records: List[Dict[str, object]] = []
    usage_registry: Dict[Tuple[int, str, str, str], models.UserSupplyUsage] = {}
    processed_ids: Set[int] = set()
    dual_repair_done: Set[int] = set()

    all_reports = db.query(models.RepairItemReport).all()
    reports = [r for r in all_reports if _should_process_tilt_report(r)]

    repair_nos = {r.repair_no for r in reports if r.repair_no}
    repairs_by_no: Dict[int, models.Repair] = {}
    if repair_nos:
        for repair in db.query(models.Repair).filter(
            models.Repair.repair_no.in_(repair_nos)
        ).all():
            repairs_by_no[repair.repair_no] = repair

    band_map = _build_band_map(reports, repairs_by_no)

    for report in reports:
        if report.id in processed_ids:
            continue

        repair = repairs_by_no.get(report.repair_no) if report.repair_no else None
        item_code = (repair.item_code or "").strip() if repair else ""

        if not item_code:
            reason = "آیتم‌کد تعمیر یافت نشد"
            skipped += 1
            skip_reasons[reason] += 1
            skipped_records.append(_skipped_record(report, repair, reason, item_code))
            continue

        band = band_map.get(report.id)
        if not band:
            band = _fragment_tilt_band(report.fragment_name or "", report.fragment_part_no or "")

        if not band:
            rules = TILT_QUANTITY_RULES.get(item_code, {})
            if "900" in rules and "1800" in rules and report.repair_no not in dual_repair_done:
                cnt, inv, dual_reasons = _apply_dual_band_for_repair(
                    db, report, item_code, usage_registry, processed_ids,
                )
                if cnt > 0:
                    dual_repair_done.add(report.repair_no)
                    updated += cnt
                    inventory_adjusted += inv
                    for rep_r, reason_r in dual_reasons:
                        skipped += 1
                        skip_reasons[reason_r] += 1
                        skipped_records.append(
                            _skipped_record(rep_r, repair, reason_r, item_code)
                        )
                    continue

            reason = "نوع قطعه (1800/900) در نام قطعه شناسایی نشد"
            skipped += 1
            skip_reasons[reason] += 1
            skipped_records.append(_skipped_record(report, repair, reason, item_code))
            continue

        ok, changed, reason = _apply_band_to_report(db, report, item_code, band, usage_registry)
        if ok:
            updated += 1
            processed_ids.add(report.id)
            if changed:
                inventory_adjusted += 1
        elif reason:
            skipped += 1
            skip_reasons[reason] += 1
            skipped_records.append(_skipped_record(report, repair, reason, item_code))
            processed_ids.add(report.id)
        else:
            unchanged += 1
            processed_ids.add(report.id)

    sync_updated, sync_inv = _sync_reports_with_parts(db, usage_registry)
    updated += sync_updated
    inventory_adjusted += sync_inv

    db.commit()

    reasons_list: List[Dict[str, object]] = [
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
