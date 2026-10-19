#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Optional, Dict, Tuple
import jdatetime
from fastapi import APIRouter, Depends, Query, HTTPException, status, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pathlib import Path
import pandas as pd

from app.db.database import get_db
from app.db import models
from app.schemas.repair_item_report import (
    RepairItemReport,
    RepairItemReportUpdate,
    RepairItemReportImportResult,
    MissingItemCodePair,
    ApplyTiltQuantitiesResult,
)
from app.api.deps import get_current_user, get_current_admin_user
from app.core.permissions import assert_report_access, is_admin_or_owner
from app.core.jalali_dates import apply_jalali_date_range_filter
from app.services.repair_report_excel_import import import_repair_reports_from_excel
from app.services.tilt_electric_quantities import apply_tilt_electric_quantities
from app.services.ghaltaki_quantities import apply_ghaltaki_quantities as run_apply_ghaltaki_quantities
from app.services.fixator_quantities import apply_fixator_quantities as run_apply_fixator_quantities
from app.services.full_repair_report_export import build_full_report_workbook
from app.services.repair_report_display_status import display_status_for_report

router = APIRouter()

# Cache برای mapping Excel
_excel_antenna_type_cache: Optional[Dict[Tuple[str, str], str]] = None


def _apply_token_filter(query, column, text: str):
    """Each whitespace-separated token must appear in the column (AND)."""
    tokens = [t.strip() for t in text.split() if t.strip()]
    for token in tokens:
        query = query.filter(column.like(f"%{token}%"))
    return query

def get_excel_file_path() -> Path:
    """یافتن مسیر فایل Excel"""
    # مسیرهای ممکن
    possible_paths = [
        Path(__file__).parent.parent.parent.parent.parent / "need" / "تعمیرات.xlsx",
        Path("C:/Users/user/Desktop/need/تعمیرات.xlsx"),
        Path.home() / "Desktop" / "need" / "تعمیرات.xlsx",
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    # اگر پیدا نشد، اولین مسیر را برمی‌گردانیم
    return possible_paths[0]

def load_excel_antenna_types() -> Dict[Tuple[str, str], str]:
    """بارگذاری mapping نوع آنتن از فایل Excel"""
    global _excel_antenna_type_cache
    
    if _excel_antenna_type_cache is not None:
        return _excel_antenna_type_cache
    
    _excel_antenna_type_cache = {}
    
    try:
        excel_file_path = get_excel_file_path()
        if excel_file_path.exists():
            df = pd.read_excel(excel_file_path)
            
            for _, row in df.iterrows():
                if pd.notna(row.get('antenna_serial_no')) and pd.notna(row.get(' Antenna type')):
                    # تبدیل شماره سریال به string
                    serial_raw = row['antenna_serial_no']
                    if isinstance(serial_raw, float):
                        serial_no = str(int(serial_raw)).strip()
                    else:
                        serial_no = str(serial_raw).strip()
                    
                    vendor = str(row['Supplier Vendor']).strip() if pd.notna(row.get('Supplier Vendor')) else ""
                    antenna_type = str(row[' Antenna type']).strip()
                    
                    if serial_no and antenna_type:
                        key = (serial_no, vendor)
                        # اگر چند رکورد برای یک شماره سریال وجود دارد، آخرین را نگه داریم
                        _excel_antenna_type_cache[key] = antenna_type
    except Exception as e:
        print(f"Warning: Could not load Excel file: {e}")
    
    return _excel_antenna_type_cache


def _build_item_code_assignment_map(db: Session) -> Dict[Tuple[str, str], str]:
    mapping: Dict[Tuple[str, str], str] = {}
    for assignment in db.query(models.ItemCodeAssignment).all():
        if not assignment.manufacturer or not assignment.antenna_type:
            continue
        key = (
            assignment.manufacturer.strip().lower(),
            assignment.antenna_type.strip().lower(),
        )
        if key not in mapping:
            mapping[key] = assignment.item_code
    return mapping


def _lookup_assigned_item_code(
    assignment_map: Dict[Tuple[str, str], str],
    manufacturer: Optional[str],
    antenna_type: Optional[str],
) -> Optional[str]:
    if not manufacturer or not antenna_type:
        return None
    key = (manufacturer.strip().lower(), antenna_type.strip().lower())
    return assignment_map.get(key)


def _enrich_repair_item_reports(
    db: Session,
    reports: List[models.RepairItemReport],
    antenna_type: Optional[str] = None,
    antenna_types: Optional[List[str]] = None,
) -> List[RepairItemReport]:
    if not reports:
        return []

    excel_mapping = load_excel_antenna_types()
    assignment_map = _build_item_code_assignment_map(db)

    repair_nos = {r.repair_no for r in reports if r.repair_no}
    repairs_by_no: Dict[int, models.Repair] = {}
    if repair_nos:
        for repair in db.query(models.Repair).filter(
            models.Repair.repair_no.in_(repair_nos)
        ).all():
            repairs_by_no[repair.repair_no] = repair

    serials = {r.antenna_serial_no for r in reports if r.antenna_serial_no}
    repairs_by_serial: Dict[str, models.Repair] = {}
    repairs_by_serial_vendor: Dict[Tuple[str, str], models.Repair] = {}
    if serials:
        for repair in (
            db.query(models.Repair)
            .filter(models.Repair.antenna_serial_no.in_(list(serials)))
            .order_by(models.Repair.repair_no.desc())
            .all()
        ):
            serial_key = repair.antenna_serial_no
            if serial_key and serial_key not in repairs_by_serial:
                repairs_by_serial[serial_key] = repair
            vendor_key = (repair.antenna_serial_no, repair.constructor or "")
            if vendor_key[0] and vendor_key not in repairs_by_serial_vendor:
                repairs_by_serial_vendor[vendor_key] = repair

    enriched_reports: List[RepairItemReport] = []
    for report in reports:
        found_antenna_type = None
        found_item_code = None

        if report.repair_no and report.repair_no in repairs_by_no:
            repair_by_no = repairs_by_no[report.repair_no]
            found_antenna_type = repair_by_no.antenna_type

        vendor_str = str(report.manufacturer).strip() if report.manufacturer else ""
        serial_str = str(report.antenna_serial_no).strip() if report.antenna_serial_no else ""

        if not found_antenna_type and serial_str and vendor_str:
            repair_by_serial = repairs_by_serial_vendor.get((serial_str, vendor_str))
            if repair_by_serial:
                found_antenna_type = repair_by_serial.antenna_type

        if not found_antenna_type and serial_str:
            repair_by_serial_only = repairs_by_serial.get(serial_str)
            if repair_by_serial_only:
                found_antenna_type = repair_by_serial_only.antenna_type

        if not found_antenna_type and serial_str:
            key = (serial_str, vendor_str)
            if key in excel_mapping:
                found_antenna_type = excel_mapping[key]
            else:
                for (s, _v), at in excel_mapping.items():
                    if s == serial_str:
                        found_antenna_type = at
                        break

        found_item_code = _lookup_assigned_item_code(
            assignment_map,
            vendor_str or report.manufacturer,
            found_antenna_type,
        )

        disp_status, disp_final = display_status_for_report(
            item_name=report.item_name,
            status=report.status,
            final_status=report.final_status,
            antenna_serial_no=report.antenna_serial_no,
            personal_id=report.personal_id,
            manufacturer=report.manufacturer,
        )

        enriched_reports.append(
            RepairItemReport(
                id=report.id,
                repair_no=report.repair_no,
                antenna_serial_no=report.antenna_serial_no,
                manufacturer=report.manufacturer,
                personal_id=report.personal_id,
                first_name=report.first_name,
                last_name=report.last_name,
                item_name=report.item_name,
                fragment_name=report.fragment_name,
                fragment_part_no=report.fragment_part_no,
                arsenal_name=report.arsenal_name,
                used_quantity=report.used_quantity,
                status=disp_status,
                final_status=disp_final,
                repair_date=report.repair_date,
                antenna_type=found_antenna_type,
                item_code=found_item_code,
                item_description=report.item_description,
            )
        )

    if antenna_type:
        filter_value = antenna_type.strip()
        enriched_reports = [
            r for r in enriched_reports
            if r.antenna_type and r.antenna_type.strip() == filter_value
        ]
    elif antenna_types:
        allowed = {t.strip() for t in antenna_types}
        enriched_reports = [
            r for r in enriched_reports
            if r.antenna_type and r.antenna_type.strip() in allowed
        ]

    return enriched_reports


def _filtered_reports_query(
    db: Session,
    current_user: models.User,
    *,
    repair_no: Optional[int] = None,
    serial_no: Optional[str] = None,
    manufacturer: Optional[str] = None,
    manufacturers: Optional[List[str]] = None,
    item_name: Optional[str] = None,
    item_names: Optional[List[str]] = None,
    item_code: Optional[str] = None,
    status: Optional[str] = None,
    statuses: Optional[List[str]] = None,
    antenna_type: Optional[str] = None,
    antenna_types: Optional[List[str]] = None,
    personal_ids: Optional[List[int]] = None,
    repair_start_date: Optional[str] = None,
    repair_end_date: Optional[str] = None,
):
    query = db.query(models.RepairItemReport)

    if not is_admin_or_owner(current_user):
        query = query.filter(models.RepairItemReport.personal_id == current_user.personal_id)
    elif personal_ids:
        query = query.filter(models.RepairItemReport.personal_id.in_(personal_ids))

    if repair_no:
        query = query.filter(models.RepairItemReport.repair_no == repair_no)

    if serial_no:
        query = query.filter(models.RepairItemReport.antenna_serial_no.like(f"%{serial_no}%"))

    if manufacturer:
        query = query.filter(models.RepairItemReport.manufacturer.like(f"%{manufacturer}%"))

    if manufacturers:
        query = query.filter(models.RepairItemReport.manufacturer.in_(manufacturers))

    if item_names:
        query = query.filter(models.RepairItemReport.item_name.in_(item_names))
    elif item_name:
        query = _apply_token_filter(query, models.RepairItemReport.item_name, item_name)

    if statuses:
        query = query.filter(or_(
            models.RepairItemReport.status.in_(statuses),
            models.RepairItemReport.final_status.in_(statuses),
        ))
    elif status:
        query = query.filter(or_(
            models.RepairItemReport.status.like(f"%{status}%"),
            models.RepairItemReport.final_status.like(f"%{status}%"),
        ))

    query = apply_jalali_date_range_filter(
        query,
        models.RepairItemReport.repair_date,
        repair_start_date,
        repair_end_date,
    )

    if item_code or antenna_type or antenna_types:
        query = query.join(
            models.Repair,
            models.RepairItemReport.repair_no == models.Repair.repair_no,
            isouter=True,
        )
        if item_code:
            query = query.filter(models.Repair.item_code.like(f"%{item_code}%"))
        if antenna_type:
            query = query.filter(models.Repair.antenna_type.like(f"%{antenna_type}%"))
        if antenna_types:
            query = query.filter(models.Repair.antenna_type.in_(antenna_types))

    return query.order_by(models.RepairItemReport.repair_no.desc())


@router.get("/", response_model=List[RepairItemReport])
async def get_repair_item_reports(
    skip: int = 0,
    limit: Optional[int] = None,
    repair_no: Optional[int] = None,
    serial_no: Optional[str] = None,
    manufacturer: Optional[str] = None,
    manufacturers: Optional[List[str]] = Query(None),
    item_name: Optional[str] = None,
    item_names: Optional[List[str]] = Query(None),
    item_code: Optional[str] = None,
    status: Optional[str] = None,
    statuses: Optional[List[str]] = Query(None),
    antenna_type: Optional[str] = None,
    antenna_types: Optional[List[str]] = Query(None),
    personal_ids: Optional[List[int]] = Query(None),
    repair_start_date: Optional[str] = None,
    repair_end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get all repair item reports with optional filters"""
    query = _filtered_reports_query(
        db,
        current_user,
        repair_no=repair_no,
        serial_no=serial_no,
        manufacturer=manufacturer,
        manufacturers=manufacturers,
        item_name=item_name,
        item_names=item_names,
        item_code=item_code,
        status=status,
        statuses=statuses,
        antenna_type=antenna_type,
        antenna_types=antenna_types,
        personal_ids=personal_ids,
        repair_start_date=repair_start_date,
        repair_end_date=repair_end_date,
    )

    if skip > 0:
        query = query.offset(skip)

    if limit is not None:
        query = query.limit(limit)

    reports = query.all()

    return _enrich_repair_item_reports(
        db,
        reports,
        antenna_type=antenna_type,
        antenna_types=antenna_types,
    )


@router.get("/full-excel")
async def export_full_repair_report_excel(
    repair_no: Optional[int] = None,
    serial_no: Optional[str] = None,
    manufacturer: Optional[str] = None,
    manufacturers: Optional[List[str]] = Query(None),
    item_name: Optional[str] = None,
    item_names: Optional[List[str]] = Query(None),
    item_code: Optional[str] = None,
    status: Optional[str] = None,
    statuses: Optional[List[str]] = Query(None),
    antenna_type: Optional[str] = None,
    antenna_types: Optional[List[str]] = Query(None),
    personal_ids: Optional[List[int]] = Query(None),
    repair_start_date: Optional[str] = None,
    repair_end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Export گزارش کلی Excel — same filters as repair-items list (repair_date + personal_id)."""
    query = _filtered_reports_query(
        db,
        current_user,
        repair_no=repair_no,
        serial_no=serial_no,
        manufacturer=manufacturer,
        manufacturers=manufacturers,
        item_name=item_name,
        item_names=item_names,
        item_code=item_code,
        status=status,
        statuses=statuses,
        antenna_type=antenna_type,
        antenna_types=antenna_types,
        personal_ids=personal_ids,
        repair_start_date=repair_start_date,
        repair_end_date=repair_end_date,
    )
    reports = query.all()
    if not reports:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="داده‌ای برای خروجی وجود ندارد",
        )

    buf = build_full_report_workbook(db, reports)
    ts = jdatetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"full_repair_report_{ts}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import-excel", response_model=RepairItemReportImportResult)
async def import_repair_item_reports_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
):
    """Import repair item reports from Excel (admin only)."""
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
        result = import_repair_reports_from_excel(db, content)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"خطا در خواندن فایل اکسل: {exc}",
        ) from exc

    return RepairItemReportImportResult(**result)


def _cleanup_after_report_delete(db: Session, report: models.RepairItemReport):
    """Remove related repair step and supply usage when report is deleted."""
    repair_no = report.repair_no
    item_name = report.item_name

    if repair_no and item_name and report.fragment_part_no and report.arsenal_name:
        usage = db.query(models.UserSupplyUsage).filter(
            models.UserSupplyUsage.repair_no == repair_no,
            models.UserSupplyUsage.repair_item_name == item_name,
            models.UserSupplyUsage.fragment_part_no == report.fragment_part_no,
            models.UserSupplyUsage.arsenal_name == report.arsenal_name,
        ).first()
        if usage:
            arsenal = db.query(models.ArsenalTable).filter(
                models.ArsenalTable.fragment_part_no == report.fragment_part_no,
                models.ArsenalTable.arsenal_name == report.arsenal_name,
            ).first()
            if arsenal and usage.repair_fragment_qty:
                arsenal.fragment_qty += usage.repair_fragment_qty
            db.delete(usage)

    db.delete(report)
    db.flush()

    if not repair_no or not item_name:
        return

    remaining = db.query(models.RepairItemReport).filter(
        models.RepairItemReport.repair_no == repair_no,
        models.RepairItemReport.item_name == item_name,
    ).count()

    if remaining > 0:
        return

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

    step = db.query(models.RepairStep).filter(
        models.RepairStep.repair_no == repair_no,
        models.RepairStep.repair_item_name == item_name,
    ).first()
    if step:
        db.delete(step)


@router.put("/{report_id}", response_model=RepairItemReport)
async def update_repair_item_report(
    report_id: int,
    report_in: RepairItemReportUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    report = db.query(models.RepairItemReport).filter(
        models.RepairItemReport.id == report_id
    ).first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    assert_report_access(db, current_user, report)

    if not is_admin_or_owner(current_user):
        report_in = RepairItemReportUpdate(
            **report_in.model_dump(exclude_unset=True, exclude={"personal_id", "final_status"})
        )

    update_data = report_in.model_dump(exclude_unset=True)
    repair_fields = {}

    if "manufacturer" in update_data:
        report.manufacturer = update_data["manufacturer"]
        repair_fields["constructor"] = update_data["manufacturer"]
    if "antenna_serial_no" in update_data:
        report.antenna_serial_no = update_data["antenna_serial_no"]
        repair_fields["antenna_serial_no"] = update_data["antenna_serial_no"]
    if "personal_id" in update_data:
        report.personal_id = update_data["personal_id"]
        user = db.query(models.User).filter(models.User.personal_id == update_data["personal_id"]).first()
        if user:
            report.first_name = user.user_first_name
            report.last_name = user.user_last_name
    if "item_name" in update_data:
        report.item_name = update_data["item_name"]
    if "status" in update_data:
        report.status = update_data["status"]
    if "final_status" in update_data:
        report.final_status = update_data["final_status"]
    if "repair_date" in update_data:
        report.repair_date = update_data["repair_date"]

    if report.repair_no and ("antenna_type" in update_data or "item_code" in update_data or repair_fields):
        repair = db.query(models.Repair).filter(models.Repair.repair_no == report.repair_no).first()
        if repair:
            if "antenna_type" in update_data:
                repair.antenna_type = update_data["antenna_type"]
                repair_fields["antenna_type"] = update_data["antenna_type"]
            if "item_code" in update_data:
                repair.item_code = update_data["item_code"]
                repair_fields["item_code"] = update_data["item_code"]
            for field, value in repair_fields.items():
                setattr(repair, field, value)
            from app.api.endpoints.repairs import _sync_repair_related_records
            _sync_repair_related_records(db, repair, repair_fields)

    db.commit()
    db.refresh(report)

    antenna_type = update_data.get("antenna_type")
    item_code = update_data.get("item_code")
    if report.repair_no and (antenna_type is None or item_code is None):
        repair = db.query(models.Repair).filter(models.Repair.repair_no == report.repair_no).first()
        if repair:
            if antenna_type is None:
                antenna_type = repair.antenna_type
            if item_code is None:
                item_code = repair.item_code

    return RepairItemReport(
        id=report.id,
        repair_no=report.repair_no,
        antenna_serial_no=report.antenna_serial_no,
        manufacturer=report.manufacturer,
        personal_id=report.personal_id,
        first_name=report.first_name,
        last_name=report.last_name,
        item_name=report.item_name,
        fragment_name=report.fragment_name,
        fragment_part_no=report.fragment_part_no,
        arsenal_name=report.arsenal_name,
        used_quantity=report.used_quantity,
        status=report.status,
        final_status=report.final_status,
        repair_date=report.repair_date,
        antenna_type=antenna_type,
        item_code=item_code,
        item_description=report.item_description,
    )


@router.get("/filter-options")
async def get_repair_item_report_filter_options(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Distinct status values from repair item reports (for multi-select filters)."""
    query = db.query(
        models.RepairItemReport.status,
        models.RepairItemReport.final_status,
    )
    if not is_admin_or_owner(current_user):
        query = query.filter(models.RepairItemReport.personal_id == current_user.personal_id)

    statuses: set[str] = set()
    for status, final_status in query.distinct().all():
        if status and status.strip():
            statuses.add(status.strip())
        if final_status and final_status.strip():
            statuses.add(final_status.strip())

    return {"statuses": sorted(statuses)}


@router.get("/missing-item-code-pairs", response_model=List[MissingItemCodePair])
async def get_missing_item_code_pairs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Distinct vendor + antenna type pairs in repair reports with no item code assignment."""
    query = db.query(models.RepairItemReport)
    if not is_admin_or_owner(current_user):
        query = query.filter(models.RepairItemReport.personal_id == current_user.personal_id)

    reports = query.all()
    enriched = _enrich_repair_item_reports(db, reports)

    seen: set[Tuple[str, str]] = set()
    missing: List[MissingItemCodePair] = []
    for row in enriched:
        if not row.manufacturer or not row.antenna_type:
            continue
        key = (row.manufacturer.strip().lower(), row.antenna_type.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        if row.item_code:
            continue
        missing.append(
            MissingItemCodePair(
                manufacturer=row.manufacturer.strip(),
                antenna_type=row.antenna_type.strip(),
            )
        )

    missing.sort(key=lambda p: (p.manufacturer.lower(), p.antenna_type.lower()))
    return missing


@router.post("/apply-tilt-quantities", response_model=ApplyTiltQuantitiesResult)
async def apply_tilt_quantities(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
):
    """Update used_quantity for electric tilt reports by fragment band (admin only)."""
    return apply_tilt_electric_quantities(db)


@router.post("/apply-ghaltaki-quantities", response_model=ApplyTiltQuantitiesResult)
async def apply_ghaltaki_quantities(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
):
    """Update used_quantity for ghaltaki reports from sibling electric-tilt bands (admin only)."""
    return run_apply_ghaltaki_quantities(db)


@router.post("/apply-fixator-quantities", response_model=ApplyTiltQuantitiesResult)
async def apply_fixator_quantities(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
):
    """Update fixator used_quantity and inventory by antenna type/vendor (admin only)."""
    return run_apply_fixator_quantities(db)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repair_item_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    report = db.query(models.RepairItemReport).filter(
        models.RepairItemReport.id == report_id
    ).first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    assert_report_access(db, current_user, report)
    _cleanup_after_report_delete(db, report)
    db.commit()
    return None


@router.get("/{report_id}", response_model=RepairItemReport)
async def get_repair_item_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get a specific repair item report by ID"""
    report = db.query(models.RepairItemReport).filter(
        models.RepairItemReport.id == report_id
    ).first()
    
    if not report:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found"
        )

    assert_report_access(db, current_user, report)
    
    return report


