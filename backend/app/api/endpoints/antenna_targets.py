#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Employer target (تارگت کارفرما) per antenna X class."""

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user, get_current_user
from app.db import models
from app.db.database import get_db

router = APIRouter()


@router.get("/")
async def list_antenna_targets(
    response: Response,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Dict[str, int]:
    """Return a map of {bucket_code: target_qty}."""
    response.headers["Cache-Control"] = "no-store"
    return {
        (t.bucket_code or "").strip(): int(t.target_qty or 0)
        for t in db.query(models.AntennaTarget).all()
        if (t.bucket_code or "").strip()
    }


@router.put("/")
async def set_antenna_targets(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Upsert employer targets. Body: {"targets": {"2X": 100, "3X": 50, ...}}."""
    targets = payload.get("targets") or {}
    if not isinstance(targets, dict):
        targets = {}

    for raw_code, raw_qty in targets.items():
        code = (str(raw_code) or "").strip()
        if not code:
            continue
        try:
            qty = int(raw_qty or 0)
        except (TypeError, ValueError):
            qty = 0
        qty = max(0, qty)

        row = (
            db.query(models.AntennaTarget)
            .filter(models.AntennaTarget.bucket_code == code)
            .first()
        )
        if row:
            row.target_qty = qty
        else:
            db.add(models.AntennaTarget(bucket_code=code, target_qty=qty))

    db.commit()
    return {"ok": True, "count": len(targets)}
