#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.database import get_db
from app.db import models
from app.api.deps import get_current_admin_user

router = APIRouter()


class AntennaType(BaseModel):
    antenna_type: str

    class Config:
        from_attributes = True


class AntennaTypeCreate(BaseModel):
    antenna_type: str


@router.get("/", response_model=List[AntennaType])
async def get_antenna_types(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Get all antenna types"""
    types = db.query(models.AntennaType).order_by(models.AntennaType.antenna_type).all()
    return types


@router.get("/public", response_model=List[AntennaType])
async def get_antenna_types_public(
    db: Session = Depends(get_db)
):
    """Get all antenna types (public endpoint, no auth required)"""
    types = db.query(models.AntennaType).order_by(models.AntennaType.antenna_type).all()
    return types


@router.post("/", response_model=AntennaType, status_code=status.HTTP_201_CREATED)
async def create_antenna_type(
    type_in: AntennaTypeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Create new antenna type"""
    # Check if type already exists
    existing_type = db.query(models.AntennaType).filter(
        models.AntennaType.antenna_type == type_in.antenna_type
    ).first()

    if existing_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Antenna type already exists"
        )

    # Create new type
    db_type = models.AntennaType(
        antenna_type=type_in.antenna_type
    )

    db.add(db_type)
    db.commit()
    db.refresh(db_type)

    return db_type


@router.delete("/{antenna_type}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_antenna_type(
    antenna_type: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Delete antenna type"""
    type_obj = db.query(models.AntennaType).filter(
        models.AntennaType.antenna_type == antenna_type
    ).first()

    if not type_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Antenna type not found"
        )

    db.delete(type_obj)
    db.commit()

    return None

