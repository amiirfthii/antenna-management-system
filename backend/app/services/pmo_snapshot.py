#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Persistent PMO/dashboard numbers, independent from live repairs."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

import jdatetime
from sqlalchemy.orm import Session

from app.db import models

PMO_NUMERIC_FIELDS = ("dep", "p1", "p2", "tot", "sap", "wait")

PMO_TO_X_BUCKET = {
    "x-pole": "X-Pole",
    "v-pole": "V-Pole",
    "2x-pole": "2X",
    "3x-pole": "3X",
    "4x-pole": "4X",
    "5x-pole": "5X",
    "8x-pole": "8X",
    "8x-irani": "8X",
    "TDD": "TDD",
}


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _now() -> str:
    return jdatetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")


def _empty_row(row_type: str) -> Dict[str, Any]:
    row: Dict[str, Any] = {"type": row_type}
    for field in PMO_NUMERIC_FIELDS:
        row[field] = 0
    return row


def _normalize_rows(rows: Iterable[Dict[str, Any]], row_order: List[str]) -> List[Dict[str, Any]]:
    by_type: Dict[str, Dict[str, Any]] = {}
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        row_type = (str(raw.get("type") or "")).strip()
        if row_type not in row_order:
            continue
        by_type[row_type] = {
            "type": row_type,
            **{field: _safe_int(raw.get(field)) for field in PMO_NUMERIC_FIELDS},
        }
    return [by_type.get(name, _empty_row(name)) for name in row_order]


def snapshot_has_rows(db: Session) -> bool:
    if not hasattr(models, "PmoSnapshot"):
        return False
    return db.query(models.PmoSnapshot.id).first() is not None


def load_snapshot(db: Session, row_order: List[str]) -> List[Dict[str, Any]]:
    if not hasattr(models, "PmoSnapshot"):
        return [_empty_row(name) for name in row_order]
    found: Dict[str, Dict[str, Any]] = {}
    for record in db.query(models.PmoSnapshot).all():
        name = (record.row_type or "").strip()
        if not name:
            continue
        found[name] = {
            "type": name,
            "dep": _safe_int(record.dep),
            "p1": _safe_int(record.p1),
            "p2": _safe_int(record.p2),
            "tot": _safe_int(record.tot),
            "sap": _safe_int(record.sap),
            "wait": _safe_int(record.wait),
        }
    return [found.get(name, _empty_row(name)) for name in row_order]


def save_snapshot(db: Session, rows: Iterable[Dict[str, Any]], row_order: List[str]) -> List[Dict[str, Any]]:
    normalized = _normalize_rows(rows, row_order)
    existing = {
        (record.row_type or "").strip(): record
        for record in db.query(models.PmoSnapshot).all()
    }
    now = _now()
    for row in normalized:
        record = existing.get(row["type"])
        if record is None:
            db.add(
                models.PmoSnapshot(
                    row_type=row["type"],
                    dep=row["dep"],
                    p1=row["p1"],
                    p2=row["p2"],
                    tot=row["tot"],
                    sap=row["sap"],
                    wait=row["wait"],
                    updated_date=now,
                )
            )
        else:
            record.dep = row["dep"]
            record.p1 = row["p1"]
            record.p2 = row["p2"]
            record.tot = row["tot"]
            record.sap = row["sap"]
            record.wait = row["wait"]
            record.updated_date = now
    db.commit()
    return normalized


def seed_if_empty(
    db: Session,
    live_rows: Iterable[Dict[str, Any]],
    row_order: List[str],
) -> List[Dict[str, Any]]:
    """First run only: copy current live PMO numbers, then freeze."""
    if snapshot_has_rows(db):
        return load_snapshot(db, row_order)
    return save_snapshot(db, live_rows, row_order)


def bars_from_snapshot(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, int]] = {}
    for row in rows:
        bucket = PMO_TO_X_BUCKET.get((row.get("type") or "").strip())
        if not bucket:
            continue
        slot = grouped.setdefault(
            bucket,
            {"approved": 0, "exited": 0, "province_in": 0, "in_center": 0},
        )
        wait = _safe_int(row.get("wait"))
        sap = _safe_int(row.get("sap"))
        p1 = _safe_int(row.get("p1"))
        dep = _safe_int(row.get("dep"))
        tot = _safe_int(row.get("tot")) or (wait + sap)
        slot["approved"] += tot
        slot["exited"] += sap
        slot["province_in"] += p1
        slot["in_center"] += wait + p1 + dep

    bars: List[Dict[str, Any]] = []
    for code, slot in grouped.items():
        if slot["approved"] + slot["exited"] + slot["province_in"] <= 0:
            continue
        bars.append(
            {
                "code": code,
                "label": code,
                "approved": slot["approved"],
                "exited": slot["exited"],
                "province_in": slot["province_in"],
                "in_center": slot["in_center"],
                "total": slot["approved"] + slot["exited"] + slot["province_in"],
                "source": "pmo_snapshot",
            }
        )
    return bars


def center_inventory_from_snapshot(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, int]] = {}
    for row in rows:
        bucket = PMO_TO_X_BUCKET.get((row.get("type") or "").strip())
        if not bucket:
            continue
        slot = grouped.setdefault(bucket, {"province_in": 0, "depreciated_in": 0})
        slot["province_in"] += _safe_int(row.get("p1"))
        slot["depreciated_in"] += _safe_int(row.get("dep"))

    bars: List[Dict[str, Any]] = []
    for code, slot in grouped.items():
        if slot["province_in"] + slot["depreciated_in"] <= 0:
            continue
        bars.append(
            {
                "code": code,
                "label": code,
                "province_in": slot["province_in"],
                "depreciated_in": slot["depreciated_in"],
                "total": slot["province_in"] + slot["depreciated_in"],
                "source": "pmo_snapshot",
            }
        )
    return bars


def snapshot_card_totals(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    province = sum(_safe_int(row.get("p1")) for row in rows)
    depreciated = sum(_safe_int(row.get("dep")) for row in rows)
    waiting = sum(_safe_int(row.get("wait")) for row in rows)
    return {
        "province_incoming_total": province,
        "center_antennas": province + depreciated + waiting,
    }
