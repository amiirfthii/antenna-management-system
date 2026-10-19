#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.database import get_db
from app.db import models
from app.api.deps import get_current_admin_user, get_current_user

router = APIRouter()


class RepairItem(BaseModel):
    repair_item_name: str

    class Config:
        from_attributes = True


class RepairItemCreate(BaseModel):
    repair_item_name: str


@router.get("/", response_model=List[RepairItem])
async def get_repair_items(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get all repair items"""
    items = db.query(models.RepairItem).order_by(models.RepairItem.repair_item_name).all()
    return items


@router.post("/", response_model=RepairItem, status_code=status.HTTP_201_CREATED)
async def create_repair_item(
    item_in: RepairItemCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Create new repair item"""
    # Check if item already exists
    existing_item = db.query(models.RepairItem).filter(
        models.RepairItem.repair_item_name == item_in.repair_item_name
    ).first()

    if existing_item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repair item already exists"
        )

    # Create new item
    db_item = models.RepairItem(
        repair_item_name=item_in.repair_item_name
    )

    db.add(db_item)
    db.commit()
    db.refresh(db_item)

    return db_item


@router.delete("/{repair_item_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repair_item(
    repair_item_name: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Delete repair item"""
    item = db.query(models.RepairItem).filter(
        models.RepairItem.repair_item_name == repair_item_name
    ).first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repair item not found"
        )

    db.delete(item)
    db.commit()

    return None

