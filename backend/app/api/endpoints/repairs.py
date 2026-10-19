#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Optional
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status, Query
from sqlalchemy.orm import Session
import jdatetime

from app.db.database import get_db
from app.db import models
from app.schemas.repair import (
    Repair, RepairCreate, RepairUpdate, RepairStep, RepairStepCreate, RepairStepUpdate,
    SubmitRepairItemsRequest, SubmitRepairItemsResponse, RepairQueueGroup,
    SerialExcelImportResult,
    SerialRangeImportRequest,
    BulkSubmitRepairItemsRequest,
    BulkSubmitRepairItemsResponse,
    BulkDeleteRepairItemsRequest,
    BulkDeleteRepairItemsResponse,
    PackagingExcelApplyResult,
)
from app.api.deps import get_current_user, get_current_admin_user
from app.core.permissions import assert_repair_access, assert_repair_update_access, is_admin_or_owner, user_owns_repair, REPAIR_QUEUE_STATUSES
from app.core.arsenal import ARSENAL_EQUIPMENT, REPAIR_ARSENAL_TYPES
from app.core.jalali_dates import apply_jalali_date_range_filter, normalize_jalali_date_string

router = APIRouter()


def _restore_arsenal_quantity(
    db: Session,
    part_no: str,
    arsenal_name: str,
    qty: int,
) -> int:
    if qty <= 0:
        return 0
    arsenal = db.query(models.ArsenalTable).filter(
        models.ArsenalTable.fragment_part_no == part_no,
        models.ArsenalTable.arsenal_name == arsenal_name,
    ).first()
    if not arsenal:
        return 0
    arsenal.fragment_qty += qty
    return qty


def _restore_inventory_from_supply_usages(db: Session) -> int:
    total = 0
    for usage in db.query(models.UserSupplyUsage).all():
        total += _restore_arsenal_quantity(
            db,
            usage.fragment_part_no,
            usage.arsenal_name,
            usage.repair_fragment_qty or 0,
        )
    return total


def _reconcile_inventory_from_entries(db: Session) -> int:
    """Set stock back to total received quantity when all repair data is gone."""
    if db.query(models.Repair).count() > 0:
        return 0
    if db.query(models.RepairItemReport).count() > 0:
        return 0
    if db.query(models.UserSupplyUsage).count() > 0:
        return 0

    from sqlalchemy import func

    entry_totals = (
        db.query(
            models.SupplyFragmentEntry.fragment_part_no,
            models.SupplyFragmentEntry.arsenal_name,
            func.coalesce(func.sum(models.SupplyFragmentEntry.fragment_entry_qty), 0),
        )
        .group_by(
            models.SupplyFragmentEntry.fragment_part_no,
            models.SupplyFragmentEntry.arsenal_name,
        )
        .all()
    )

    restored = 0
    for part_no, arsenal_name, target in entry_totals:
        if not part_no or not arsenal_name:
            continue
        item = db.query(models.ArsenalTable).filter(
            models.ArsenalTable.fragment_part_no == part_no,
            models.ArsenalTable.arsenal_name == arsenal_name,
        ).first()
        if not item:
            continue
        target_qty = int(target)
        if item.fragment_qty < target_qty:
            delta = target_qty - item.fragment_qty
            item.fragment_qty = target_qty
            restored += delta
    return restored


def _restore_inventory_from_orphaned_withdrawals(
    db: Session,
    personal_id: str,
) -> int:
    """Return consumed parts to stock when repair data was purged without restoring inventory."""
    return _reconcile_inventory_from_entries(db)


def _sync_repair_related_records(db: Session, repair: models.Repair, update_data: dict):
    repair_no = repair.repair_no

    if "item_code" in update_data:
        db.query(models.RepairStep).filter(
            models.RepairStep.repair_no == repair_no
        ).update({"item_code": update_data["item_code"]}, synchronize_session=False)

    report_updates = {}
    if "constructor" in update_data:
        report_updates["manufacturer"] = update_data["constructor"]
    if "antenna_serial_no" in update_data:
        report_updates["antenna_serial_no"] = update_data["antenna_serial_no"]
    if report_updates:
        db.query(models.RepairItemReport).filter(
            models.RepairItemReport.repair_no == repair_no
        ).update(report_updates, synchronize_session=False)

    delivered_updates = {}
    if "constructor" in update_data:
        delivered_updates["manufacturer"] = update_data["constructor"]
    if "antenna_type" in update_data:
        delivered_updates["antenna_type"] = update_data["antenna_type"]
    if "item_code" in update_data:
        delivered_updates["item_code"] = update_data["item_code"] or ""
    if "antenna_serial_no" in update_data:
        delivered_updates["antenna_serial_no"] = update_data["antenna_serial_no"]
    if delivered_updates:
        db.query(models.DeliveredAntenna).filter(
            models.DeliveredAntenna.repair_no == str(repair_no)
        ).update(delivered_updates, synchronize_session=False)


@router.get("/", response_model=List[Repair])
async def get_repairs(
    skip: int = 0,
    limit: Optional[int] = None,  # None = Ø¨Ø¯ÙˆÙ† Ù…Ø­Ø¯ÙˆØ¯ÛŒØª
    status_filter: Optional[List[str]] = Query(None),
    entry_type: Optional[str] = None,
    vendor: Optional[str] = None,
    vendors: Optional[List[str]] = Query(None),
    serial_no: Optional[str] = None,
    antenna_type: Optional[str] = None,
    antenna_types: Optional[List[str]] = Query(None),
    item_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get all repairs with optional filters - returns all records if limit is not specified"""
    query = db.query(models.Repair)

    if status_filter:
        query = query.filter(models.Repair.antenna_status.in_(status_filter))

    if entry_type:
        query = query.filter(models.Repair.antenna_entry_type == entry_type)

    if vendor:
        query = query.filter(models.Repair.constructor.like(f"%{vendor}%"))

    if vendors:
        query = query.filter(models.Repair.constructor.in_(vendors))

    if serial_no:
        query = query.filter(models.Repair.antenna_serial_no.like(f"%{serial_no}%"))

    if antenna_type:
        query = query.filter(models.Repair.antenna_type.like(f"%{antenna_type}%"))

    if antenna_types:
        query = query.filter(models.Repair.antenna_type.in_(antenna_types))

    if item_code:
        query = query.filter(models.Repair.item_code.like(f"%{item_code}%"))

    query = apply_jalali_date_range_filter(
        query,
        models.Repair.entry_date,
        start_date,
        end_date,
    )

    query = query.order_by(models.Repair.repair_no.desc())
    
    if skip > 0:
        query = query.offset(skip)
    
    if limit is not None:
        query = query.limit(limit)
    
    repairs = query.all()
    return repairs


@router.get("/queue-summary", response_model=List[RepairQueueGroup])
async def get_repair_queue_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Antennas waiting in repair queue, grouped by vendor and antenna type."""
    rows = (
        db.query(
            models.Repair.constructor,
            models.Repair.antenna_type,
            func.count(models.Repair.repair_no).label("cnt"),
        )
        .filter(
            models.Repair.antenna_entry_type == "ÙˆØ±ÙˆØ¯ÛŒ_ØªØ¹Ù…ÛŒØ±",
            models.Repair.antenna_status.in_(list(REPAIR_QUEUE_STATUSES)),
            or_(models.Repair.exit_date.is_(None), models.Repair.exit_date == ""),
        )
        .group_by(models.Repair.constructor, models.Repair.antenna_type)
        .order_by(func.count(models.Repair.repair_no).desc())
        .all()
    )

    return [
        RepairQueueGroup(
            vendor=(row.constructor or "-").strip() or "-",
            antenna_type=(row.antenna_type or "-").strip() or "-",
            count=int(row.cnt or 0),
        )
        for row in rows
    ]


@router.get("/check-duplicate/{serial_no}", response_model=Optional[Repair])
async def check_duplicate_serial(
    serial_no: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Check if serial number already exists"""
    from app.services.serial_uniqueness import find_repair_by_serial

    return find_repair_by_serial(db, serial_no)


@router.post("/import-serial-excel", response_model=SerialExcelImportResult)
async def import_serial_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
) -> SerialExcelImportResult:
    """Bulk-import serial antennas from column-oriented Excel and consume no-serial stock."""
    del current_user
    filename = (file.filename or "").lower()
    if not filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ÙÙ‚Ø· ÙØ§ÛŒÙ„â€ŒÙ‡Ø§ÛŒ Ø§Ú©Ø³Ù„ (.xlsx / .xls) Ù…Ø¬Ø§Ø² Ù‡Ø³ØªÙ†Ø¯",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ÙØ§ÛŒÙ„ Ø®Ø§Ù„ÛŒ Ø§Ø³Øª",
        )

    from app.services.serial_excel_import import import_serials_from_excel

    result = import_serials_from_excel(db, content)
    return SerialExcelImportResult(**result)


@router.post("/import-serial-range", response_model=SerialExcelImportResult)
async def import_serial_range_endpoint(
    body: SerialRangeImportRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
) -> SerialExcelImportResult:
    """Import contiguous numeric serials; keep valid rows and report failed ones."""
    del current_user
    from app.services.serial_range_import import import_serial_range

    result = import_serial_range(
        db,
        serial_from=body.serial_from,
        serial_to=body.serial_to,
        vendor=body.constructor,
        antenna_type=body.antenna_type,
        antenna_entry_type=body.antenna_entry_type,
        item_code=body.item_code,
        no_serial_category=body.no_serial_category,
        entry_date=body.entry_date,
    )
    return SerialExcelImportResult(**result)


@router.post("/apply-packaging-excel", response_model=PackagingExcelApplyResult)
async def apply_packaging_excel_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
) -> PackagingExcelApplyResult:
    """Mark Excel serials as ØªØ§ÛŒÛŒØ¯; mark all other antennas as Ø®Ø±ÙˆØ¬."""
    del current_user
    filename = (file.filename or "").lower()
    if not filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ÙÙ‚Ø· ÙØ§ÛŒÙ„â€ŒÙ‡Ø§ÛŒ Ø§Ú©Ø³Ù„ (.xlsx / .xls) Ù…Ø¬Ø§Ø² Ù‡Ø³ØªÙ†Ø¯",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ÙØ§ÛŒÙ„ Ø®Ø§Ù„ÛŒ Ø§Ø³Øª",
        )

    from app.services.packaging_excel_apply import apply_packaging_excel

    result = apply_packaging_excel(db, content)
    return PackagingExcelApplyResult(**result)


@router.post("/bulk-submit-items", response_model=BulkSubmitRepairItemsResponse)
async def bulk_submit_repair_items(
    payload: BulkSubmitRepairItemsRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> BulkSubmitRepairItemsResponse:
    """Submit the same repair items to many antennas ."""
    from app.core.repair_permissions import can_impersonate_repair_actor

    if not can_impersonate_repair_actor(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ø«Ø¨Øª Ú¯Ø±ÙˆÙ‡ÛŒ ÙÙ‚Ø· Ø¨Ø±Ø§ÛŒ Ø§Ø¯Ù…ÛŒÙ† Ù…Ø¬Ø§Ø² Ø§Ø³Øª",
        )

    repair_nos = []
    seen: set[int] = set()
    for no in payload.repair_nos or []:
        try:
            n = int(no)
        except (TypeError, ValueError):
            continue
        if n in seen:
            continue
        seen.add(n)
        repair_nos.append(n)

    if not repair_nos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ù‡ÛŒÚ† Ø´Ù…Ø§Ø±Ù‡ ØªØ¹Ù…ÛŒØ±ÛŒ Ø§Ù†ØªØ®Ø§Ø¨ Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª",
        )
    if len(repair_nos) > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ø­Ø¯Ø§Ú©Ø«Ø± Û²Û°Û° Ø¢Ù†ØªÙ† Ø¯Ø± ÛŒÚ© Ø«Ø¨Øª Ú¯Ø±ÙˆÙ‡ÛŒ Ù…Ø¬Ø§Ø² Ø§Ø³Øª",
        )
    if not payload.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No repair items to submit",
        )

    actor = _resolve_acting_user(db, current_user, payload.acting_personal_id)
    total = succeeded = failed = reports_created = 0
    errors: list[str] = []

    for repair_no in repair_nos:
        total += 1
        try:
            created = _submit_repair_items_for_repair(
                db,
                repair_no=repair_no,
                payload=SubmitRepairItemsRequest(
                    item_status=payload.item_status,
                    items=payload.items,
                    end_date=payload.end_date,
                ),
                actor=actor,
                access_user=current_user,
                commit=False,
            )
            succeeded += 1
            reports_created += created
        except HTTPException as exc:
            failed += 1
            detail = exc.detail
            if not isinstance(detail, str):
                detail = str(detail)
            errors.append(f"ØªØ¹Ù…ÛŒØ± {repair_no}: {detail}")
        except Exception as exc:
            failed += 1
            errors.append(f"ØªØ¹Ù…ÛŒØ± {repair_no}: {exc}")

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ø®Ø·Ø§ Ø¯Ø± Ø°Ø®ÛŒØ±Ù‡ Ù†Ù‡Ø§ÛŒÛŒ Ø«Ø¨Øª Ú¯Ø±ÙˆÙ‡ÛŒ: {exc}",
        ) from exc

    return BulkSubmitRepairItemsResponse(
        message="Bulk repair items submitted",
        total=total,
        succeeded=succeeded,
        failed=failed,
        reports_created=reports_created,
        errors=errors[:100],
    )


@router.post("/bulk-delete-items", response_model=BulkDeleteRepairItemsResponse)
async def bulk_delete_repair_items(
    payload: BulkDeleteRepairItemsRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> BulkDeleteRepairItemsResponse:
    """Delete the same repair item from many antennas ."""
    from app.core.repair_permissions import can_impersonate_repair_actor

    if not can_impersonate_repair_actor(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ø­Ø°Ù Ú¯Ø±ÙˆÙ‡ÛŒ ÙÙ‚Ø· Ø¨Ø±Ø§ÛŒ Ø§Ø¯Ù…ÛŒÙ† Ù…Ø¬Ø§Ø² Ø§Ø³Øª",
        )

    item_name = (payload.item_name or "").strip()
    if not item_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ù†Ø§Ù… Ø¢ÛŒØªÙ… ØªØ¹Ù…ÛŒØ± Ù…Ø´Ø®Øµ Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª",
        )

    repair_nos = []
    seen: set[int] = set()
    for no in payload.repair_nos or []:
        try:
            n = int(no)
        except (TypeError, ValueError):
            continue
        if n in seen:
            continue
        seen.add(n)
        repair_nos.append(n)

    if not repair_nos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ù‡ÛŒÚ† Ø´Ù…Ø§Ø±Ù‡ ØªØ¹Ù…ÛŒØ±ÛŒ Ø§Ù†ØªØ®Ø§Ø¨ Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª",
        )
    if len(repair_nos) > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ø­Ø¯Ø§Ú©Ø«Ø± Û²Û°Û° Ø¢Ù†ØªÙ† Ø¯Ø± ÛŒÚ© Ø­Ø°Ù Ú¯Ø±ÙˆÙ‡ÛŒ Ù…Ø¬Ø§Ø² Ø§Ø³Øª",
        )

    total = succeeded = failed = deleted_reports = 0
    errors: list[str] = []

    for repair_no in repair_nos:
        total += 1
        try:
            deleted_reports += _delete_repair_item_for_repair(
                db,
                repair_no=repair_no,
                item_name=item_name,
                access_user=current_user,
                commit=False,
            )
            succeeded += 1
        except HTTPException as exc:
            failed += 1
            detail = exc.detail
            if not isinstance(detail, str):
                detail = str(detail)
            errors.append(f"ØªØ¹Ù…ÛŒØ± {repair_no}: {detail}")
        except Exception as exc:
            failed += 1
            errors.append(f"ØªØ¹Ù…ÛŒØ± {repair_no}: {exc}")

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ø®Ø·Ø§ Ø¯Ø± Ø°Ø®ÛŒØ±Ù‡ Ù†Ù‡Ø§ÛŒÛŒ Ø­Ø°Ù Ú¯Ø±ÙˆÙ‡ÛŒ: {exc}",
        ) from exc

    return BulkDeleteRepairItemsResponse(
        message="Bulk repair items deleted",
        total=total,
        succeeded=succeeded,
        failed=failed,
        deleted_reports=deleted_reports,
        errors=errors[:100],
    )


@router.get("/{repair_no}", response_model=Repair)
async def get_repair(
    repair_no: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get repair by repair number"""
    repair = db.query(models.Repair).filter(
        models.Repair.repair_no == repair_no
    ).first()

    if not repair:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repair not found"
        )

    assert_repair_access(db, current_user, repair_no, allow_queue=True)

    return repair


@router.post("/", response_model=Repair, status_code=status.HTTP_201_CREATED)
async def create_repair(
    repair_in: RepairCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Create new repair record"""
    from app.services.no_serial_antenna import consume_no_serial_unit
    from app.services.serial_uniqueness import (
        assert_serial_unique_for_create,
        normalize_serial,
    )

    payload = repair_in.model_dump()
    allow_re_registration = bool(payload.pop("allow_duplicate_re_registration", False))
    no_serial_category = (payload.pop("no_serial_category", None) or "").strip() or None
    payload["antenna_serial_no"] = normalize_serial(payload.get("antenna_serial_no"))

    duplicate_error = assert_serial_unique_for_create(
        db,
        payload["antenna_serial_no"],
        allow_re_registration=allow_re_registration,
    )
    if duplicate_error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=duplicate_error,
        )

    item_code = (repair_in.item_code or "").strip()
    if not item_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ø¢ÛŒØªÙ…â€ŒÚ©Ø¯ Ø±Ø§ Ø§Ù†ØªØ®Ø§Ø¨ Ú©Ù†ÛŒØ¯. Ø¨Ø¯ÙˆÙ† Ø¢ÛŒØªÙ…â€ŒÚ©Ø¯ Ø³Ø±ÛŒØ§Ù„ Ø«Ø¨Øª Ù†Ù…ÛŒâ€ŒØ´ÙˆØ¯.",
        )
    if not no_serial_category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ø¯Ø³ØªÙ‡ (Ø§Ø³ØªØ§Ù† ÛŒØ§ Ù…Ø³ØªÙ‡Ù„Ú©) Ø±Ø§ Ø§Ù†ØªØ®Ø§Ø¨ Ú©Ù†ÛŒØ¯. Ø¨Ø¯ÙˆÙ† Ø¯Ø³ØªÙ‡ Ø³Ø±ÛŒØ§Ù„ Ø«Ø¨Øª Ù†Ù…ÛŒâ€ŒØ´ÙˆØ¯.",
        )

    db_repair = models.Repair(**payload)
    # Ù…Ù†Ø´Ø£ Ø¢Ù†ØªÙ† Ø³Ø±ÛŒØ§Ù„â€ŒØ¯Ø§Ø± Ø±Ø§ Ø¨Ø±Ø§ÛŒ Ø¢Ù…Ø§Ø± Ù…ÙˆØ¬ÙˆØ¯ÛŒ Ø¯Ø± Ù…Ø±Ú©Ø² Ø°Ø®ÛŒØ±Ù‡ Ù…ÛŒâ€ŒÚ©Ù†ÛŒÙ…
    db_repair.no_serial_category = no_serial_category
    db.add(db_repair)

    try:
        consume_no_serial_unit(
            db,
            vendor=repair_in.constructor or "",
            antenna_type=repair_in.antenna_type or "",
            item_code=item_code,
            category=no_serial_category,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Ø³Ø±ÛŒØ§Ù„ {payload['antenna_serial_no']} ØªÚ©Ø±Ø§Ø±ÛŒ Ø§Ø³Øª Ùˆ Ù‚Ø¨Ù„Ø§Ù‹ Ø¯Ø± Ø³ÛŒØ³ØªÙ… Ø«Ø¨Øª Ø´Ø¯Ù‡"
            ),
        ) from exc
    db.refresh(db_repair)

    return db_repair


@router.put("/{repair_no}", response_model=Repair)
async def update_repair(
    repair_no: int,
    repair_in: RepairUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Update repair record"""
    repair = db.query(models.Repair).filter(
        models.Repair.repair_no == repair_no
    ).first()

    if not repair:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repair not found"
        )

    assert_repair_update_access(db, current_user, repair_no, repair_in.model_dump(exclude_unset=True))

    # Update fields
    update_data = repair_in.model_dump(exclude_unset=True)

    if "antenna_serial_no" in update_data:
        from app.services.serial_uniqueness import (
            assert_serial_unique_for_update,
            normalize_serial,
        )

        update_data["antenna_serial_no"] = normalize_serial(update_data["antenna_serial_no"])
        duplicate_error = assert_serial_unique_for_update(
            db,
            update_data["antenna_serial_no"],
            repair_no=repair_no,
        )
        if duplicate_error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=duplicate_error,
            )

    if not is_admin_or_owner(current_user):
        update_data.pop("antenna_admin_check_date", None)
        update_data.pop("exit_date", None)
        if "antenna_status" in update_data and update_data["antenna_status"] != "Ø¯Ø±_Ø§Ù†ØªØ¸Ø§Ø±_ØªØ§ÛŒÛŒØ¯":
            update_data.pop("antenna_status", None)

    # If status is being changed to 'Ø®Ø±ÙˆØ¬', set exit_date
    if "antenna_status" in update_data and update_data["antenna_status"] == "Ø®Ø±ÙˆØ¬":
        update_data["exit_date"] = jdatetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')

    for field, value in update_data.items():
        setattr(repair, field, value)

    sync_fields = {"constructor", "antenna_type", "item_code", "antenna_serial_no"}
    if sync_fields & set(update_data.keys()):
        _sync_repair_related_records(db, repair, update_data)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Ø³Ø±ÛŒØ§Ù„ {repair.antenna_serial_no} ØªÚ©Ø±Ø§Ø±ÛŒ Ø§Ø³Øª Ùˆ Ù‚Ø¨Ù„Ø§Ù‹ Ø¯Ø± Ø³ÛŒØ³ØªÙ… Ø«Ø¨Øª Ø´Ø¯Ù‡"
            ),
        ) from exc
    db.refresh(repair)

    return repair


@router.delete("/purge-all")
async def purge_all_repairs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
):
    """Delete all repairs and related records (admin only)."""
    restored_quantity = _restore_inventory_from_supply_usages(db)
    deleted_usage = db.query(models.UserSupplyUsage).delete(synchronize_session=False)
    deleted_reports = db.query(models.RepairItemReport).delete(synchronize_session=False)
    deleted_steps = db.query(models.RepairStep).delete(synchronize_session=False)
    deleted_delivered = db.query(models.DeliveredAntenna).delete(synchronize_session=False)
    deleted_repairs = db.query(models.Repair).delete(synchronize_session=False)
    orphaned_restored = _restore_inventory_from_orphaned_withdrawals(
        db,
        str(current_user.personal_id),
    )
    db.commit()
    return {
        "deleted_repairs": deleted_repairs,
        "deleted_reports": deleted_reports,
        "deleted_steps": deleted_steps,
        "deleted_usage": deleted_usage,
        "deleted_delivered": deleted_delivered,
        "restored_quantity": restored_quantity + orphaned_restored,
    }


@router.post("/restore-inventory-after-purge")
async def restore_inventory_after_purge(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
):
    """Return consumed parts to warehouse stock after repair data was already purged."""
    restored_from_usage = _restore_inventory_from_supply_usages(db)
    db.query(models.UserSupplyUsage).delete(synchronize_session=False)
    restored_from_history = _restore_inventory_from_orphaned_withdrawals(
        db,
        str(current_user.personal_id),
    )
    db.commit()
    total = restored_from_usage + restored_from_history
    if total == 0:
        return {
            "restored_quantity": 0,
            "message": "Ù…ÙˆØ±Ø¯ÛŒ Ø¨Ø±Ø§ÛŒ Ø¨Ø§Ø²Ú¯Ø±Ø¯Ø§Ù†Ø¯Ù† Ø¨Ù‡ Ù…ÙˆØ¬ÙˆØ¯ÛŒ ÛŒØ§ÙØª Ù†Ø´Ø¯",
        }
    return {
        "restored_quantity": total,
        "message": f"{total} Ù‚Ø·Ø¹Ù‡ Ø¨Ù‡ Ù…ÙˆØ¬ÙˆØ¯ÛŒ Ø§Ù†Ø¨Ø§Ø± Ø¨Ø§Ø²Ú¯Ø±Ø¯Ø§Ù†Ø¯Ù‡ Ø´Ø¯",
    }


@router.delete("/{repair_no}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repair(
    repair_no: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Delete repair record"""
    repair = db.query(models.Repair).filter(
        models.Repair.repair_no == repair_no
    ).first()

    if not repair:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repair not found"
        )

    db.delete(repair)
    db.commit()

    return None


# Repair Steps Endpoints

@router.get("/{repair_no}/steps", response_model=List[RepairStep])
async def get_repair_steps(
    repair_no: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get all steps for a repair"""
    assert_repair_access(db, current_user, repair_no, allow_queue=True)

    steps = db.query(models.RepairStep).filter(
        models.RepairStep.repair_no == repair_no
    ).all()

    changed = False
    kept = []
    for step in steps:
        if step.item_status == "Ø§Ù†Ø¬Ø§Ù… Ø´Ø¯Ù‡":
            report_count = db.query(models.RepairItemReport).filter(
                models.RepairItemReport.repair_no == repair_no,
                models.RepairItemReport.item_name == step.repair_item_name,
            ).count()
            if report_count == 0:
                for usage in db.query(models.UserSupplyUsage).filter(
                    models.UserSupplyUsage.repair_no == repair_no,
                    models.UserSupplyUsage.repair_item_name == step.repair_item_name,
                ).all():
                    db.delete(usage)
                db.delete(step)
                changed = True
                continue
        kept.append(step)

    if changed:
        db.commit()

    return kept


@router.post("/{repair_no}/steps", response_model=RepairStep, status_code=status.HTTP_201_CREATED)
async def create_repair_step(
    repair_no: int,
    step_in: RepairStepCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Create new repair step"""
    # Verify repair exists
    repair = db.query(models.Repair).filter(
        models.Repair.repair_no == repair_no
    ).first()

    if not repair:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repair not found"
        )

    # Check if step already exists
    existing_step = db.query(models.RepairStep).filter(
        models.RepairStep.repair_no == repair_no,
        models.RepairStep.repair_item_name == step_in.repair_item_name
    ).first()

    if existing_step:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repair step already exists"
        )

    # Set start_date from repair entry_date
    db_step = models.RepairStep(
        **step_in.model_dump(),
        start_date=repair.entry_date
    )

    db.add(db_step)
    db.commit()
    db.refresh(db_step)

    return db_step


@router.delete("/{repair_no}/steps/{item_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repair_step(
    repair_no: int,
    item_name: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Delete repair step, related reports, and restore inventory."""
    item_name = (item_name or "").strip()
    if not item_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ù†Ø§Ù… Ø¢ÛŒØªÙ… ØªØ¹Ù…ÛŒØ± Ù…Ø´Ø®Øµ Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª",
        )

    _delete_repair_item_for_repair(
        db,
        repair_no=repair_no,
        item_name=item_name,
        access_user=current_user,
        commit=True,
    )
    return None


@router.put("/{repair_no}/steps/{item_name}", response_model=RepairStep)
async def update_repair_step(
    repair_no: int,
    item_name: str,
    step_in: RepairStepUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Update repair step"""
    step = db.query(models.RepairStep).filter(
        models.RepairStep.repair_no == repair_no,
        models.RepairStep.repair_item_name == item_name
    ).first()

    if not step:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repair step not found"
        )

    # Update fields
    update_data = step_in.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(step, field, value)

    db.commit()
    db.refresh(step)

    return step


@router.post("/{repair_no}/submit-items", response_model=SubmitRepairItemsResponse)
async def submit_repair_items(
    repair_no: int,
    payload: SubmitRepairItemsRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Save repair items, update steps, deduct inventory, and create reports."""
    actor = _resolve_acting_user(db, current_user, payload.acting_personal_id)
    reports_created = _submit_repair_items_for_repair(
        db,
        repair_no=repair_no,
        payload=payload,
        actor=actor,
        access_user=current_user,
        commit=True,
    )
    return SubmitRepairItemsResponse(
        message="Repair items submitted successfully",
        reports_created=reports_created,
    )


def _delete_repair_item_for_repair(
    db: Session,
    *,
    repair_no: int,
    item_name: str,
    access_user: models.User,
    commit: bool,
) -> int:
    """Remove all reports/usages for an item on one repair and delete its step."""
    from app.api.endpoints.repair_item_reports import _cleanup_after_report_delete

    assert_repair_access(db, access_user, repair_no, allow_queue=True)

    reports = db.query(models.RepairItemReport).filter(
        models.RepairItemReport.repair_no == repair_no,
        models.RepairItemReport.item_name == item_name,
    ).all()

    deleted_reports = 0
    for report in list(reports):
        _cleanup_after_report_delete(db, report)
        deleted_reports += 1

    step = db.query(models.RepairStep).filter(
        models.RepairStep.repair_no == repair_no,
        models.RepairStep.repair_item_name == item_name,
    ).first()
    if step:
        for usage in db.query(models.UserSupplyUsage).filter(
            models.UserSupplyUsage.repair_no == repair_no,
            models.UserSupplyUsage.repair_item_name == item_name,
        ).all():
            arsenal = db.query(models.ArsenalTable).filter(
                models.ArsenalTable.fragment_part_no == usage.fragment_part_no,
                models.ArsenalTable.arsenal_name == usage.arsenal_name,
            ).first()
            if arsenal and usage.repair_fragment_qty:
                arsenal.fragment_qty += usage.repair_fragment_qty
            db.delete(usage)
        db.delete(step)

    if commit:
        db.commit()
    else:
        db.flush()

    return deleted_reports


def _resolve_acting_user(
    db: Session,
    current_user: models.User,
    acting_personal_id: int | None,
) -> models.User:
    from app.core.repair_permissions import can_impersonate_repair_actor

    if not acting_personal_id or int(acting_personal_id) == int(current_user.personal_id):
        return current_user
    if not can_impersonate_repair_actor(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ø§Ø¬Ø§Ø²Ù‡ Ø«Ø¨Øª Ø¨Ù‡ Ù†Ø§Ù… Ú©Ø§Ø±Ø¨Ø± Ø¯ÛŒÚ¯Ø± Ø±Ø§ Ù†Ø¯Ø§Ø±ÛŒØ¯",
        )
    actor = db.query(models.User).filter(
        models.User.personal_id == int(acting_personal_id)
    ).first()
    if not actor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ú©Ø§Ø±Ø¨Ø± Ø§Ù†ØªØ®Ø§Ø¨â€ŒØ´Ø¯Ù‡ ÛŒØ§ÙØª Ù†Ø´Ø¯",
        )
    if not actor.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ú©Ø§Ø±Ø¨Ø± Ø§Ù†ØªØ®Ø§Ø¨â€ŒØ´Ø¯Ù‡ ØºÛŒØ±ÙØ¹Ø§Ù„ Ø§Ø³Øª",
        )
    return actor


def _submit_repair_items_for_repair(
    db: Session,
    *,
    repair_no: int,
    payload: SubmitRepairItemsRequest,
    actor: models.User,
    access_user: models.User,
    commit: bool,
) -> int:
    repair = db.query(models.Repair).filter(
        models.Repair.repair_no == repair_no
    ).first()

    if not repair:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repair not found"
        )

    assert_repair_access(db, access_user, repair_no, allow_queue=True)

    if not payload.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No repair items to submit"
        )

    current_date = jdatetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')
    if payload.end_date:
        normalized_end = normalize_jalali_date_string(payload.end_date.strip())
        if normalized_end:
            if " " not in normalized_end and ":" not in normalized_end:
                current_date = (
                    f"{normalized_end} "
                    f"{jdatetime.datetime.now().strftime('%H:%M:%S')}"
                )
            else:
                current_date = normalized_end

    reports_created = 0

    for item in payload.items:
        step = db.query(models.RepairStep).filter(
            models.RepairStep.repair_no == repair_no,
            models.RepairStep.repair_item_name == item.item_name
        ).first()

        if step:
            step.item_status = payload.item_status
            step.personal_id = actor.personal_id
            step.end_date = current_date
            if repair.item_code:
                step.item_code = repair.item_code
        else:
            db.add(models.RepairStep(
                repair_no=repair_no,
                repair_item_name=item.item_name,
                item_status=payload.item_status,
                personal_id=actor.personal_id,
                start_date=repair.entry_date or current_date,
                end_date=current_date,
                item_code=repair.item_code,
            ))

        if not item.parts:
            db.add(models.RepairItemReport(
                repair_no=repair_no,
                antenna_serial_no=repair.antenna_serial_no,
                manufacturer=repair.constructor,
                personal_id=actor.personal_id,
                first_name=actor.user_first_name,
                last_name=actor.user_last_name,
                item_name=item.item_name,
                status=payload.item_status,
                final_status="Ø¯Ø± Ø§Ù†ØªØ¸Ø§Ø±",
                repair_date=current_date,
                item_description=(item.description or "").strip() or None,
            ))
            reports_created += 1
            continue

        for part in item.parts:
            if part.quantity <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid quantity for part {part.fragment_part_no}"
                )

            if part.arsenal_name == ARSENAL_EQUIPMENT:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Ù‚Ø·Ø¹Ø§Øª Ø§Ù†Ø¨Ø§Ø± ØªØ¬Ù‡ÛŒØ²Ø§Øª Ø¯Ø± ÙØ±Ø¢ÛŒÙ†Ø¯ ØªØ¹Ù…ÛŒØ± Ù‚Ø§Ø¨Ù„ Ø§Ø³ØªÙØ§Ø¯Ù‡ Ù†ÛŒØ³ØªÙ†Ø¯ ({part.fragment_name})"
                )

            if part.arsenal_name not in REPAIR_ARSENAL_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Ù†ÙˆØ¹ Ø§Ù†Ø¨Ø§Ø± Ù†Ø§Ù…Ø¹ØªØ¨Ø± Ø¨Ø±Ø§ÛŒ ØªØ¹Ù…ÛŒØ±: {part.arsenal_name}"
                )

            arsenal = db.query(models.ArsenalTable).filter(
                models.ArsenalTable.fragment_part_no == part.fragment_part_no,
                models.ArsenalTable.arsenal_name == part.arsenal_name
            ).first()

            if not arsenal:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Part {part.fragment_part_no} not found in inventory"
                )

            if arsenal.fragment_qty < part.quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient stock for {part.fragment_name}"
                )

            arsenal.fragment_qty -= part.quantity

            db.add(models.UserSupplyUsage(
                repair_no=repair_no,
                repair_item_name=item.item_name,
                fragment_part_no=part.fragment_part_no,
                arsenal_name=part.arsenal_name,
                repair_fragment_qty=part.quantity,
            ))

            db.add(models.InventoryHistory(
                part_no=part.fragment_part_no,
                operation_type="Ø¨Ø±Ø¯Ø§Ø´Øª",
                quantity=part.quantity,
                personal_id=str(actor.personal_id),
                operation_date=current_date,
            ))

            db.add(models.RepairItemReport(
                repair_no=repair_no,
                antenna_serial_no=repair.antenna_serial_no,
                manufacturer=repair.constructor,
                personal_id=actor.personal_id,
                first_name=actor.user_first_name,
                last_name=actor.user_last_name,
                item_name=item.item_name,
                fragment_name=part.fragment_name,
                fragment_part_no=part.fragment_part_no,
                arsenal_name=part.arsenal_name,
                used_quantity=part.quantity,
                status=payload.item_status,
                final_status="Ø¯Ø± Ø§Ù†ØªØ¸Ø§Ø±",
                repair_date=current_date,
                item_description=(part.description or item.description or "").strip() or None,
            ))
            reports_created += 1

    if commit:
        db.commit()
    else:
        db.flush()

    return reports_created

