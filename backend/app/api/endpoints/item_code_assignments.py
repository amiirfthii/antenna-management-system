#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, field_validator
import jdatetime

from app.db.database import get_db
from app.db import models
from app.api.deps import get_current_admin_user, get_current_user
from app.core.jalali_dates import normalize_jalali_date_string

router = APIRouter()


class ItemCodeAssignmentBase(BaseModel):
    manufacturer: str
    antenna_type: str
    tilt_type: str
    item_code: str


class ItemCodeAssignmentCreate(ItemCodeAssignmentBase):
    pass


class ItemCodeAssignmentUpdate(ItemCodeAssignmentBase):
    pass


class ItemCodeAssignment(ItemCodeAssignmentBase):
    id: int
    created_date: str
    created_time: str

    @field_validator("created_date", mode="before")
    @classmethod
    def normalize_created_date(cls, value: str) -> str:
        if not value:
            return value
        normalized = normalize_jalali_date_string(value)
        return normalized if normalized is not None else value

    class Config:
        from_attributes = True


@router.get("/", response_model=List[ItemCodeAssignment])
async def get_item_code_assignments(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Get all item code assignments"""
    assignments = db.query(models.ItemCodeAssignment).order_by(
        models.ItemCodeAssignment.item_code
    ).all()
    return assignments


@router.post("/", response_model=ItemCodeAssignment, status_code=status.HTTP_201_CREATED)
async def create_item_code_assignment(
    assignment_in: ItemCodeAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Create new item code assignment"""
    # Check if assignment already exists (same manufacturer, antenna_type, tilt_type, item_code)
    existing = db.query(models.ItemCodeAssignment).filter(
        models.ItemCodeAssignment.manufacturer == assignment_in.manufacturer,
        models.ItemCodeAssignment.antenna_type == assignment_in.antenna_type,
        models.ItemCodeAssignment.tilt_type == assignment_in.tilt_type,
        models.ItemCodeAssignment.item_code == assignment_in.item_code
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item code assignment already exists"
        )

    # Get current date and time
    now = jdatetime.datetime.now()
    created_date = now.strftime("%Y/%m/%d")
    created_time = now.strftime("%H:%M:%S")

    # Create new assignment
    db_assignment = models.ItemCodeAssignment(
        manufacturer=assignment_in.manufacturer,
        antenna_type=assignment_in.antenna_type,
        tilt_type=assignment_in.tilt_type,
        item_code=assignment_in.item_code,
        created_date=created_date,
        created_time=created_time
    )

    db.add(db_assignment)
    db.commit()
    db.refresh(db_assignment)

    return db_assignment


@router.put("/{assignment_id}", response_model=ItemCodeAssignment)
async def update_item_code_assignment(
    assignment_id: int,
    assignment_in: ItemCodeAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Update an existing item code assignment"""
    assignment = db.query(models.ItemCodeAssignment).filter(
        models.ItemCodeAssignment.id == assignment_id
    ).first()

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item code assignment not found"
        )

    # Prevent duplicate of another row with same key fields
    duplicate = db.query(models.ItemCodeAssignment).filter(
        models.ItemCodeAssignment.id != assignment_id,
        models.ItemCodeAssignment.manufacturer == assignment_in.manufacturer,
        models.ItemCodeAssignment.antenna_type == assignment_in.antenna_type,
        models.ItemCodeAssignment.tilt_type == assignment_in.tilt_type,
        models.ItemCodeAssignment.item_code == assignment_in.item_code,
    ).first()

    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item code assignment already exists"
        )

    assignment.manufacturer = assignment_in.manufacturer
    assignment.antenna_type = assignment_in.antenna_type
    assignment.tilt_type = assignment_in.tilt_type
    assignment.item_code = assignment_in.item_code

    db.commit()
    db.refresh(assignment)
    return assignment


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item_code_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Delete item code assignment"""
    assignment = db.query(models.ItemCodeAssignment).filter(
        models.ItemCodeAssignment.id == assignment_id
    ).first()

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item code assignment not found"
        )

    db.delete(assignment)
    db.commit()

    return None


@router.get("/lookup", response_model=Optional[str])
async def lookup_item_code(
    manufacturer: str = Query(..., description="Manufacturer/Constructor name"),
    antenna_type: str = Query(..., description="Antenna type"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Lookup item code by manufacturer and antenna type"""
    # جستجو برای اولین item code assignment که با manufacturer و antenna_type مطابقت دارد
    # استفاده از case-insensitive و trim برای تطبیق بهتر
    manufacturer_clean = manufacturer.strip().lower()
    antenna_type_clean = antenna_type.strip().lower()
    
    # دریافت همه assignments و فیلتر کردن در Python برای سازگاری با SQLite
    all_assignments = db.query(models.ItemCodeAssignment).all()
    
    for assignment in all_assignments:
        if (assignment.manufacturer and assignment.antenna_type and
            assignment.manufacturer.strip().lower() == manufacturer_clean and
            assignment.antenna_type.strip().lower() == antenna_type_clean):
            return assignment.item_code
    
    return None

