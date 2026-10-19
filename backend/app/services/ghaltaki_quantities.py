#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bulk utility for correcting ghaltaki (نصب غلطکی نو) used_quantity in repair item reports.
Quantity is derived from electric-tilt bands (900/1800) on the same antenna repair.
"""

from collections import Counter, defaultdict
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.db import models
from app.services.tilt_electric_quantities import (
    _build_band_map,
    _fragment_tilt_band,
    _normalize_text,
    _should_process_tilt_report,
    _skipped_record,
)


def _should_process_ghaltaki_report(report: models.RepairItemReport) -> bool:
    fragment = (report.fragment_name or "").strip()
    if not fragment:
        return False
    name = _normalize_text(fragment)
    if "نصبغلطکینو" in name:
        return True
    if "غلطکی" in fragment and "نو" in fragment:
        return True
    return False


def _collect_tilt_bands(
    siblings: List[models.RepairItemReport],
    repairs_by_no: Dict[int, models.Repair],
) -> Set[str]:
    tilt_reports = [r for r in siblings if _should_process_tilt_report(r)]
    if not tilt_reports:
        return set()

    band_map = _build_band_map(tilt_reports, repairs_by_no)
    bands: Set[str] = set()
    for report in tilt_reports:
        band = band_map.get(report.id) or _fragment_tilt_band(
            report.fragment_name or "",
            report.fragment_part_no or "",
        )
        if band in ("900", "1800"):
            bands.add(band)
    return bands


def _target_quantity(bands: Set[str]) -> Optional[int]:
    if not bands:
        return None
    if bands <= {"900", "1800"}:
        return len(bands)
    return None


def apply_ghaltaki_quantities(db: Session) -> Dict[str, object]:
    updated = 0
    skipped = 0
    unchanged = 0
    skip_reasons: Counter = Counter()
    skipped_records: List[Dict[str, object]] = []

    all_reports = db.query(models.RepairItemReport).all()
    ghaltaki_reports = [r for r in all_reports if _should_process_ghaltaki_report(r)]

    repair_nos = {r.repair_no for r in all_reports if r.repair_no}
    repairs_by_no: Dict[int, models.Repair] = {}
    if repair_nos:
        for repair in db.query(models.Repair).filter(
            models.Repair.repair_no.in_(repair_nos)
        ).all():
            repairs_by_no[repair.repair_no] = repair

    by_repair: Dict[int, List[models.RepairItemReport]] = defaultdict(list)
    by_serial: Dict[str, List[models.RepairItemReport]] = defaultdict(list)
    for report in all_reports:
        if report.repair_no:
            by_repair[report.repair_no].append(report)
        serial = (report.antenna_serial_no or "").strip()
        if serial:
            by_serial[serial].append(report)

    for report in ghaltaki_reports:
        repair = repairs_by_no.get(report.repair_no) if report.repair_no else None

        if report.repair_no and report.repair_no in by_repair:
            siblings = by_repair[report.repair_no]
        else:
            serial = (report.antenna_serial_no or "").strip()
            if not serial:
                reason = "شماره سریال آنتن یافت نشد"
                skipped += 1
                skip_reasons[reason] += 1
                skipped_records.append(_skipped_record(report, repair, reason))
                continue
            siblings = by_serial.get(serial, [])

        bands = _collect_tilt_bands(siblings, repairs_by_no)
        target_qty = _target_quantity(bands)

        if target_qty is None:
            reason = "تیلت الکتریکال 900/1800 برای این آنتن یافت نشد"
            skipped += 1
            skip_reasons[reason] += 1
            skipped_records.append(_skipped_record(report, repair, reason))
            continue

        current_qty = report.used_quantity or 0
        if current_qty == target_qty:
            unchanged += 1
            continue

        report.used_quantity = target_qty
        updated += 1

    db.commit()

    reasons_list: List[Dict[str, object]] = [
        {"reason": reason, "count": count}
        for reason, count in skip_reasons.most_common()
    ]

    return {
        "updated": updated,
        "skipped": skipped,
        "unchanged": unchanged,
        "inventory_adjusted": 0,
        "skip_reasons": reasons_list,
        "skipped_records": skipped_records,
    }
