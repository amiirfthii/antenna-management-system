#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
from typing import List

import jdatetime
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user, get_current_user
from app.api.endpoints.item_code_assignments import lookup_item_code
from app.core.iran_provinces import IRAN_PROVINCES
from app.core.jalali_dates import normalize_jalali_date_string
from app.db import models
from app.db.database import get_db
from app.schemas.province_antenna import (
    CATEGORY_DEPRECIATED,
    CATEGORY_PROVINCE,
    NoSerialAntenna,
    NoSerialAntennaCreate,
    NoSerialAntennaImportResult,
    NoSerialAntennaMeta,
    NoSerialAntennaUpdate,
)
from app.services.no_serial_antenna import remaining_of
from app.services.no_serial_antenna_utils import duplicate_message, find_duplicate_no_serial
from app.services.depreciated_excel_import import import_depreciated_antennas_from_excel
from app.services.province_excel_import import (
    import_province_antennas_from_excel,
    validate_province_row,
)

router = APIRouter()


def _canonical_vendor_map(db: Session) -> dict[str, str]:
    return {
        (row.company_constructor or "").strip().lower(): (row.company_constructor or "").strip()
        for row in db.query(models.AntennaConstructor).all()
        if (row.company_constructor or "").strip()
    }


def _canonical_type_map(db: Session) -> dict[str, str]:
    return {
        (row.antenna_type or "").strip().lower(): (row.antenna_type or "").strip()
        for row in db.query(models.AntennaType).all()
        if (row.antenna_type or "").strip()
    }


def _build_meta(db: Session) -> NoSerialAntennaMeta:
    vendors = [
        row.company_constructor
        for row in db.query(models.AntennaConstructor)
        .order_by(models.AntennaConstructor.company_constructor)
        .all()
    ]
    antenna_types = [
        row.antenna_type
        for row in db.query(models.AntennaType)
        .order_by(models.AntennaType.antenna_type)
        .all()
    ]
    vendor_map = _canonical_vendor_map(db)
    type_map = _canonical_type_map(db)
    item_codes = []
    seen_codes: set[tuple[str, str, str]] = set()
    for row in db.query(models.ItemCodeAssignment).order_by(
        models.ItemCodeAssignment.manufacturer,
        models.ItemCodeAssignment.antenna_type,
        models.ItemCodeAssignment.item_code,
    ).all():
        manufacturer = (row.manufacturer or "").strip()
        antenna_type = (row.antenna_type or "").strip()
        item_code = (row.item_code or "").strip()
        if not manufacturer or not antenna_type or not item_code:
            continue
        vendor = vendor_map.get(manufacturer.lower(), manufacturer)
        canonical_type = type_map.get(antenna_type.lower(), antenna_type)
        dedupe_key = (vendor.lower(), canonical_type.lower(), item_code.lower())
        if dedupe_key in seen_codes:
            continue
        seen_codes.add(dedupe_key)
        item_codes.append(
            {
                "vendor": vendor,
                "antenna_type": canonical_type,
                "item_code": item_code,
                "tilt_type": (row.tilt_type or "").strip() or None,
            }
        )
    return NoSerialAntennaMeta(
        vendors=vendors,
        antenna_types=antenna_types,
        provinces=IRAN_PROVINCES,
        item_codes=item_codes,
    )


async def _validate_item_code(
    db: Session,
    current_user: models.User,
    vendor: str,
    antenna_type: str,
    item_code: str,
) -> str:
    expected_code = await lookup_item_code(
        manufacturer=vendor,
        antenna_type=antenna_type,
        db=db,
        current_user=current_user,
    )
    item_code = item_code.strip()
    if not expected_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="آیتم کد برای این وندور و نوع آنتن در دیتابیس تعریف نشده است",
        )
    if item_code.lower() != expected_code.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"آیتم کد باید {expected_code} باشد",
        )
    return item_code


@router.get("/meta", response_model=NoSerialAntennaMeta)
async def no_serial_antenna_meta(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> NoSerialAntennaMeta:
    return _build_meta(db)


@router.get("/", response_model=List[NoSerialAntenna])
async def list_no_serial_antennas(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> List[models.NoSerialAntenna]:
    return (
        db.query(models.NoSerialAntenna)
        .order_by(models.NoSerialAntenna.id.desc())
        .all()
    )


@router.post("/", response_model=NoSerialAntenna, status_code=status.HTTP_201_CREATED)
async def create_no_serial_antenna(
    payload: NoSerialAntennaCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
) -> models.NoSerialAntenna:
    item_code = await _validate_item_code(
        db, current_user, payload.vendor, payload.antenna_type, payload.item_code
    )

    category = payload.category or CATEGORY_PROVINCE
    province = (payload.province or "").strip()

    if category == CATEGORY_PROVINCE:
        error = validate_province_row(
            db,
            payload.vendor,
            payload.antenna_type,
            item_code,
            province,
            payload.quantity,
        )
        if error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
        matched_province = next(
            (p for p in IRAN_PROVINCES if p == province),
            province,
        )
        province = matched_province
    elif category == CATEGORY_DEPRECIATED:
        if payload.quantity <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="تعداد باید بزرگ‌تر از صفر باشد",
            )
        province = ""
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="دسته نامعتبر است",
        )

    entry_date = normalize_jalali_date_string(payload.entry_date) if payload.entry_date else None
    if not entry_date:
        entry_date = jdatetime.datetime.now().strftime("%Y/%m/%d")

    existing = find_duplicate_no_serial(
        db,
        payload.vendor.strip(),
        payload.antenna_type.strip(),
        item_code,
        category,
        province,
        payload.quantity,
        entry_date,
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=duplicate_message(
                f"DB #{existing.id}",
                vendor=existing.vendor,
                antenna_type=existing.antenna_type,
                item_code=existing.item_code,
                category=existing.category,
                province=existing.province or "",
                quantity=existing.quantity,
                created_date=existing.created_date or "",
            ),
        )

    row = models.NoSerialAntenna(
        vendor=payload.vendor.strip(),
        antenna_type=payload.antenna_type.strip(),
        item_code=item_code,
        category=category,
        province=province,
        quantity=payload.quantity,
        remaining_quantity=payload.quantity,
        created_date=entry_date,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{row_id}", response_model=NoSerialAntenna)
async def update_no_serial_antenna(
    row_id: int,
    payload: NoSerialAntennaUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
) -> models.NoSerialAntenna:
    row = db.query(models.NoSerialAntenna).filter(models.NoSerialAntenna.id == row_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="رکورد یافت نشد")

    data = payload.model_dump(exclude_unset=True)
    vendor = data.get("vendor", row.vendor)
    antenna_type = data.get("antenna_type", row.antenna_type)
    item_code = data.get("item_code", row.item_code)
    category = data.get("category", row.category)
    province = data.get("province", row.province)
    quantity = data.get("quantity", row.quantity)

    if "item_code" in data or "vendor" in data or "antenna_type" in data:
        item_code = await _validate_item_code(db, current_user, vendor, antenna_type, item_code)

    if category == CATEGORY_PROVINCE:
        error = validate_province_row(db, vendor, antenna_type, item_code, province or "", quantity)
        if error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
        province = next((p for p in IRAN_PROVINCES if p == (province or "").strip()), (province or "").strip())
    elif category == CATEGORY_DEPRECIATED:
        province = ""
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="دسته نامعتبر است")

    if "entry_date" in data and data["entry_date"]:
        row.created_date = normalize_jalali_date_string(data["entry_date"])

    entry_date = row.created_date or ""

    existing = find_duplicate_no_serial(
        db,
        vendor.strip(),
        antenna_type.strip(),
        item_code,
        category,
        province or "",
        quantity,
        entry_date,
        exclude_id=row_id,
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=duplicate_message(
                f"DB #{existing.id}",
                vendor=existing.vendor,
                antenna_type=existing.antenna_type,
                item_code=existing.item_code,
                category=existing.category,
                province=existing.province or "",
                quantity=existing.quantity,
                created_date=existing.created_date or "",
            ),
        )

    row.vendor = vendor.strip()
    row.antenna_type = antenna_type.strip()
    row.item_code = item_code
    row.category = category
    row.province = province
    old_qty = int(row.quantity or 0)
    row.quantity = quantity
    if quantity != old_qty:
        row.remaining_quantity = max(
            0, min(int(quantity), remaining_of(row) + (int(quantity) - old_qty))
        )
    elif row.remaining_quantity is None:
        row.remaining_quantity = quantity
    db.commit()
    db.refresh(row)
    return row


@router.delete("/all")
async def delete_all_no_serial_antennas(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
) -> dict:
    deleted = db.query(models.NoSerialAntenna).delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}


@router.delete("/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_no_serial_antenna(
    row_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
) -> None:
    row = db.query(models.NoSerialAntenna).filter(models.NoSerialAntenna.id == row_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="رکورد یافت نشد")
    db.delete(row)
    db.commit()


@router.post("/import-excel", response_model=NoSerialAntennaImportResult)
async def import_no_serial_antennas_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
) -> NoSerialAntennaImportResult:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="فایل انتخاب نشده است")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".xlsx", ".xls"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="فرمت فایل باید xlsx یا xls باشد",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="فایل خالی است")

    try:
        result = import_province_antennas_from_excel(db, content)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"خطا در خواندن فایل اکسل: {exc}",
        ) from exc

    return NoSerialAntennaImportResult(**result)


@router.post("/import-depreciated-excel", response_model=NoSerialAntennaImportResult)
async def import_depreciated_antennas_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
) -> NoSerialAntennaImportResult:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="فایل انتخاب نشده است")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".xlsx", ".xls"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="فرمت فایل باید xlsx یا xls باشد",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="فایل خالی است")

    try:
        result = import_depreciated_antennas_from_excel(db, content, file.filename)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"خطا در خواندن فایل اکسل: {exc}",
        ) from exc

    return NoSerialAntennaImportResult(**result)

