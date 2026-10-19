#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
import jdatetime

from app.db.database import get_db
from app.db import models
from app.schemas.inventory import Inventory, InventoryCreate, InventoryUpdate, InventoryWithdrawal, InventoryHistory, SupplyFragmentEntry
from app.api.deps import get_current_user, get_current_admin_user
from app.core.arsenal import ARSENAL_EQUIPMENT, CONSUMABLE_ARSENAL_TYPES

router = APIRouter()


@router.get("/", response_model=List[Inventory])
async def get_inventory(
    skip: int = 0,
    limit: int = 1000,
    category: Optional[str] = Query(
        None,
        description="consumable = نو/سالویج, equipment = تجهیزات only",
    ),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get all inventory items"""
    query = db.query(models.ArsenalTable)
    if category == "consumable":
        query = query.filter(models.ArsenalTable.arsenal_name.in_(CONSUMABLE_ARSENAL_TYPES))
    elif category == "equipment":
        query = query.filter(models.ArsenalTable.arsenal_name == ARSENAL_EQUIPMENT)
    items = query.order_by(
        models.ArsenalTable.fragment_name
    ).offset(skip).limit(limit).all()
    return items


@router.get("/entries", response_model=List[SupplyFragmentEntry])
async def get_inventory_entries(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get all inventory entry records (supplyFragmentEntry)"""
    entries = db.query(models.SupplyFragmentEntry).order_by(
        models.SupplyFragmentEntry.fragment_entry_no.desc()
    ).all()
    return entries


@router.get("/{part_no}/{arsenal_name}", response_model=Inventory)
async def get_inventory_item(
    part_no: str,
    arsenal_name: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get specific inventory item"""
    item = db.query(models.ArsenalTable).filter(
        models.ArsenalTable.fragment_part_no == part_no,
        models.ArsenalTable.arsenal_name == arsenal_name
    ).first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found"
        )

    return item


@router.post("/", response_model=Inventory, status_code=status.HTTP_201_CREATED)
async def add_inventory(
    item_in: InventoryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Add new inventory item or update existing quantity"""
    # Check if item exists
    existing_item = db.query(models.ArsenalTable).filter(
        models.ArsenalTable.fragment_part_no == item_in.fragment_part_no,
        models.ArsenalTable.arsenal_name == item_in.arsenal_name
    ).first()

    current_time = jdatetime.datetime.now().strftime('%H:%M:%S')
    if item_in.entry_date and item_in.entry_date.strip():
        entry_date = item_in.entry_date.strip()
        if len(entry_date) <= 10:
            entry_date = f"{entry_date} {current_time}"
    else:
        entry_date = jdatetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')

    if existing_item:
        existing_item.fragment_qty += item_in.fragment_qty
        operation_type = "افزودن"
        db.commit()
        db.refresh(existing_item)
        result = existing_item
    else:
        db_item = models.ArsenalTable(**item_in.model_dump(exclude={'entry_date'}))
        db.add(db_item)
        operation_type = "ورود"
        db.commit()
        db.refresh(db_item)
        result = db_item

    supply_entry = models.SupplyFragmentEntry(
        fragment_entry_name=item_in.fragment_name,
        fragment_part_no=item_in.fragment_part_no,
        arsenal_name=item_in.arsenal_name,
        fragment_entry_qty=item_in.fragment_qty,
        fragment_entry_date=entry_date
    )
    db.add(supply_entry)

    history_entry = models.InventoryHistory(
        part_no=item_in.fragment_part_no,
        operation_type=operation_type,
        quantity=item_in.fragment_qty,
        personal_id=str(current_user.personal_id),
        operation_date=entry_date
    )
    db.add(history_entry)

    db.commit()

    return result


@router.post("/withdraw", response_model=dict)
async def withdraw_inventory(
    withdrawal: InventoryWithdrawal,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Withdraw items from inventory"""
    # Find item (try both arsenals)
    item = db.query(models.ArsenalTable).filter(
        models.ArsenalTable.fragment_part_no == withdrawal.part_no
    ).first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Part not found in inventory"
        )

    if item.fragment_qty < withdrawal.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient quantity in inventory"
        )

    # Update quantity
    item.fragment_qty -= withdrawal.quantity

    # Log to history
    current_date = jdatetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')
    history_entry = models.InventoryHistory(
        part_no=withdrawal.part_no,
        operation_type="برداشت",
        quantity=withdrawal.quantity,
        personal_id=str(current_user.personal_id),
        operation_date=current_date
    )
    db.add(history_entry)

    db.commit()

    return {"message": "Withdrawal successful", "remaining_quantity": item.fragment_qty}


@router.put("/{part_no}/{arsenal_name}", response_model=Inventory)
async def update_inventory_item(
    part_no: str,
    arsenal_name: str,
    item_in: InventoryUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Update inventory item name and/or quantity"""
    item = db.query(models.ArsenalTable).filter(
        models.ArsenalTable.fragment_part_no == part_no,
        models.ArsenalTable.arsenal_name == arsenal_name
    ).first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found"
        )

    update_data = item_in.model_dump(exclude_unset=True)

    if "initial_qty" in update_data and update_data["initial_qty"] is not None:
        initial_qty = int(update_data["initial_qty"])
        if initial_qty < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="موجودی اولیه نمی‌تواند منفی باشد",
            )
        stock = int(item.fragment_qty or 0)
        if initial_qty < stock:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="موجودی اولیه نمی‌تواند کمتر از موجودی فعلی باشد",
            )
        entries = db.query(models.SupplyFragmentEntry).filter(
            models.SupplyFragmentEntry.fragment_part_no == part_no,
            models.SupplyFragmentEntry.arsenal_name == arsenal_name,
        ).all()
        current_total = sum(int(e.fragment_entry_qty or 0) for e in entries)
        delta = initial_qty - current_total
        if delta != 0:
            entry_date = jdatetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            db.add(
                models.SupplyFragmentEntry(
                    fragment_entry_name=item.fragment_name,
                    fragment_part_no=part_no,
                    arsenal_name=arsenal_name,
                    fragment_entry_qty=delta,
                    fragment_entry_date=entry_date,
                )
            )
            db.add(
                models.InventoryHistory(
                    part_no=part_no,
                    operation_type="اصلاح موجودی اولیه",
                    quantity=abs(delta),
                    personal_id=str(current_user.personal_id),
                    operation_date=entry_date,
                )
            )

    elif "fragment_qty" in update_data and update_data["fragment_qty"] is not None:
        if update_data["fragment_qty"] < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quantity cannot be negative",
            )
        item.fragment_qty = update_data["fragment_qty"]

    if "fragment_name" in update_data and update_data["fragment_name"] is not None:
        item.fragment_name = update_data["fragment_name"].strip()

    db.commit()
    db.refresh(item)
    return item


@router.get("/history/{part_no}", response_model=List[InventoryHistory])
async def get_inventory_history(
    part_no: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Get history for specific part"""
    history = db.query(models.InventoryHistory).filter(
        models.InventoryHistory.part_no == part_no
    ).order_by(models.InventoryHistory.operation_date.desc()).all()

    return history


@router.delete("/{part_no}/{arsenal_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inventory_item(
    part_no: str,
    arsenal_name: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Delete inventory item"""
    item = db.query(models.ArsenalTable).filter(
        models.ArsenalTable.fragment_part_no == part_no,
        models.ArsenalTable.arsenal_name == arsenal_name
    ).first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found"
        )

    db.delete(item)
    db.commit()

    return None
