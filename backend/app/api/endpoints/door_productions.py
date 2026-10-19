#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Optional

import jdatetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_admin_user, get_current_user
from app.core.admin_notifications import notify_admins_new_record
from app.core.arsenal import ARSENAL_EQUIPMENT, REPAIR_ARSENAL_TYPES
from app.core.jalali_dates import apply_jalali_date_range_filter
from app.db import models
from app.db.database import get_db
from app.schemas.door_production import DoorProduction, DoorProductionCreate, DoorProductionUpdate

router = APIRouter()


def _lookup_item_code(db: Session, vendor: str, antenna_type: str) -> Optional[str]:
    vendor_key = vendor.strip().lower()
    type_key = antenna_type.strip().lower()
    for row in db.query(models.ItemCodeAssignment).all():
        if (
            row.manufacturer
            and row.antenna_type
            and row.manufacturer.strip().lower() == vendor_key
            and row.antenna_type.strip().lower() == type_key
        ):
            return row.item_code
    return None


def _deduct_part(
    db: Session,
    *,
    part_no: str,
    arsenal_name: str,
    quantity: int,
    personal_id: int,
    operation_date: str,
) -> models.ArsenalTable:
    if arsenal_name == ARSENAL_EQUIPMENT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="قطعات انبار تجهیزات در ساخت درب قابل استفاده نیستند",
        )
    if arsenal_name not in REPAIR_ARSENAL_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"نوع انبار نامعتبر: {arsenal_name}",
        )

    item = (
        db.query(models.ArsenalTable)
        .filter(
            models.ArsenalTable.fragment_part_no == part_no,
            models.ArsenalTable.arsenal_name == arsenal_name,
        )
        .first()
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"قطعه {part_no} در انبار یافت نشد",
        )
    if item.fragment_qty < quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"موجودی کافی برای {item.fragment_name or part_no} نیست",
        )

    item.fragment_qty -= quantity
    db.add(
        models.InventoryHistory(
            part_no=part_no,
            operation_type="برداشت",
            quantity=quantity,
            personal_id=str(personal_id),
            operation_date=operation_date,
        )
    )
    return item


def _restore_part(
    db: Session,
    *,
    part_no: str,
    arsenal_name: str,
    quantity: int,
    personal_id: int,
    operation_date: str,
) -> None:
    if quantity <= 0:
        return
    item = (
        db.query(models.ArsenalTable)
        .filter(
            models.ArsenalTable.fragment_part_no == part_no,
            models.ArsenalTable.arsenal_name == arsenal_name,
        )
        .first()
    )
    if not item:
        return
    item.fragment_qty += quantity
    db.add(
        models.InventoryHistory(
            part_no=part_no,
            operation_type="بازگشت",
            quantity=quantity,
            personal_id=str(personal_id),
            operation_date=operation_date,
        )
    )


def _apply_parts_to_record(
    db: Session,
    *,
    row: models.DoorProduction,
    parts: list,
    personal_id: int,
    operation_date: str,
) -> None:
    for part in parts:
        arsenal = _deduct_part(
            db,
            part_no=part.fragment_part_no.strip(),
            arsenal_name=part.arsenal_name.strip(),
            quantity=part.quantity,
            personal_id=personal_id,
            operation_date=operation_date,
        )
        db.add(
            models.DoorProductionPart(
                door_production_id=row.id,
                fragment_part_no=part.fragment_part_no.strip(),
                fragment_name=(part.fragment_name or arsenal.fragment_name or "").strip() or None,
                arsenal_name=part.arsenal_name.strip(),
                quantity=part.quantity,
            )
        )


@router.get("/lookup-item-code")
async def lookup_item_code_for_door(
    vendor: str = Query(..., min_length=1),
    antenna_type: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> dict:
    code = _lookup_item_code(db, vendor, antenna_type)
    return {"item_code": code}


@router.get("/", response_model=List[DoorProduction])
async def list_door_productions(
    vendor: Optional[str] = Query(None),
    antenna_type: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(300, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
) -> List[DoorProduction]:
    query = db.query(models.DoorProduction).options(joinedload(models.DoorProduction.parts))
    if vendor and vendor.strip():
        query = query.filter(models.DoorProduction.vendor.like(f"%{vendor.strip()}%"))
    if antenna_type and antenna_type.strip():
        query = query.filter(models.DoorProduction.antenna_type.like(f"%{antenna_type.strip()}%"))
    query = apply_jalali_date_range_filter(query, models.DoorProduction.created_date, start_date, end_date)
    rows = (
        query.order_by(models.DoorProduction.created_date.desc(), models.DoorProduction.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return rows


@router.post("/", response_model=DoorProduction, status_code=status.HTTP_201_CREATED)
async def create_door_production(
    payload: DoorProductionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> DoorProduction:
    vendor = payload.vendor.strip()
    antenna_type = payload.antenna_type.strip()
    if not vendor or not antenna_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="وندور و نوع آنتن الزامی است")

    item_code = (payload.item_code or "").strip() or _lookup_item_code(db, vendor, antenna_type)
    created_date = jdatetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    row = models.DoorProduction(
        vendor=vendor,
        antenna_type=antenna_type,
        item_code=item_code or None,
        quantity=payload.quantity,
        description=(payload.description or "").strip(),
        personal_id=current_user.personal_id,
        user_first_name=current_user.user_first_name,
        user_last_name=current_user.user_last_name,
        created_date=created_date,
    )
    db.add(row)
    db.flush()

    _apply_parts_to_record(
        db,
        row=row,
        parts=payload.parts,
        personal_id=current_user.personal_id,
        operation_date=created_date,
    )

    db.commit()
    db.refresh(row)
    await notify_admins_new_record(
        db,
        actor=current_user,
        section="door",
        record_id=row.id,
        title=f"{row.vendor} - {row.antenna_type}",
    )
    return row


@router.get("/{record_id}", response_model=DoorProduction)
async def get_door_production(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
) -> DoorProduction:
    row = (
        db.query(models.DoorProduction)
        .options(joinedload(models.DoorProduction.parts))
        .filter(models.DoorProduction.id == record_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="رکورد یافت نشد")
    return row


@router.put("/{record_id}", response_model=DoorProduction)
async def update_door_production(
    record_id: int,
    payload: DoorProductionUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
) -> DoorProduction:
    row = (
        db.query(models.DoorProduction)
        .options(joinedload(models.DoorProduction.parts))
        .filter(models.DoorProduction.id == record_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="رکورد یافت نشد")

    vendor = payload.vendor.strip()
    antenna_type = payload.antenna_type.strip()
    if not vendor or not antenna_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="وندور و نوع آنتن الزامی است")

    op_date = jdatetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    for old_part in list(row.parts):
        _restore_part(
            db,
            part_no=old_part.fragment_part_no,
            arsenal_name=old_part.arsenal_name,
            quantity=old_part.quantity or 0,
            personal_id=current_user.personal_id,
            operation_date=op_date,
        )
    db.query(models.DoorProductionPart).filter(
        models.DoorProductionPart.door_production_id == record_id
    ).delete(synchronize_session=False)

    row.vendor = vendor
    row.antenna_type = antenna_type
    row.item_code = (payload.item_code or "").strip() or _lookup_item_code(db, vendor, antenna_type)
    row.quantity = payload.quantity
    row.description = (payload.description or "").strip()
    db.flush()

    _apply_parts_to_record(
        db,
        row=row,
        parts=payload.parts,
        personal_id=current_user.personal_id,
        operation_date=op_date,
    )

    db.commit()
    db.refresh(row)
    return row


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_door_production(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
) -> None:
    row = (
        db.query(models.DoorProduction)
        .options(joinedload(models.DoorProduction.parts))
        .filter(models.DoorProduction.id == record_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="رکورد یافت نشد")

    op_date = jdatetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    for part in row.parts:
        _restore_part(
            db,
            part_no=part.fragment_part_no,
            arsenal_name=part.arsenal_name,
            quantity=part.quantity or 0,
            personal_id=current_user.personal_id,
            operation_date=op_date,
        )

    db.delete(row)
    db.commit()
