#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build گزارش کلی Excel from repairItemsReport (same filters as repair-items tab)."""

from __future__ import annotations

from io import BytesIO
from typing import Dict, List, Optional, Tuple

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.db import models

FULL_HEADERS = [
    "No",
    "start_date",
    "end_date",
    "Supplier Vendor",
    " Antenna type",
    "antenna_serial_no",
    "Item code ",
    "item_name",
    "people",
    "personal_id",
    "status",
    "قطعه",
]


def _people_name(report: models.RepairItemReport) -> str:
    first = (report.first_name or "").strip()
    last = (report.last_name or "").strip()
    return f"{first} {last}".strip()


def _load_steps(
    db: Session, reports: List[models.RepairItemReport]
) -> Dict[Tuple[int, str], models.RepairStep]:
    keys = {
        (r.repair_no, r.item_name)
        for r in reports
        if r.repair_no and r.item_name
    }
    if not keys:
        return {}
    repair_nos = {k[0] for k in keys}
    item_names = {k[1] for k in keys}
    steps: Dict[Tuple[int, str], models.RepairStep] = {}
    for step in (
        db.query(models.RepairStep)
        .filter(
            models.RepairStep.repair_no.in_(repair_nos),
            models.RepairStep.repair_item_name.in_(item_names),
        )
        .all()
    ):
        steps[(step.repair_no, step.repair_item_name)] = step
    return steps


def _load_repairs(
    db: Session, reports: List[models.RepairItemReport]
) -> Dict[int, models.Repair]:
    repair_nos = {r.repair_no for r in reports if r.repair_no}
    if not repair_nos:
        return {}
    return {
        r.repair_no: r
        for r in db.query(models.Repair)
        .filter(models.Repair.repair_no.in_(repair_nos))
        .all()
    }


def build_full_report_rows(
    db: Session, reports: List[models.RepairItemReport]
) -> List[List]:
    steps = _load_steps(db, reports)
    repairs = _load_repairs(db, reports)
    rows: List[List] = []
    for report in reports:
        step = steps.get((report.repair_no, report.item_name)) if report.repair_no else None
        repair = repairs.get(report.repair_no) if report.repair_no else None
        vendor = (report.manufacturer or (repair.constructor if repair else "") or "").strip()
        atype = (repair.antenna_type if repair else "") or ""
        item_code = (repair.item_code if repair else "") or ""
        start_date = (step.start_date if step else "") or ""
        end_date = (step.end_date if step else "") or ""
        if not end_date and report.repair_date:
            end_date = report.repair_date
        status = (report.status or report.final_status or "").strip()
        part = (report.fragment_name or "").strip()
        rows.append(
            [
                report.repair_no or "",
                start_date,
                end_date,
                vendor,
                atype,
                report.antenna_serial_no or "",
                item_code,
                report.item_name or "",
                _people_name(report),
                report.personal_id or "",
                status,
                part,
            ]
        )
    return rows


def build_full_report_workbook(
    db: Session, reports: List[models.RepairItemReport]
) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
    ws.append(FULL_HEADERS)
    for row in build_full_report_rows(db, reports):
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
