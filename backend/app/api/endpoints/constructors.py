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


class Constructor(BaseModel):
    company_constructor: str

    class Config:
        from_attributes = True


class ConstructorCreate(BaseModel):
    company_constructor: str


@router.get("/", response_model=List[Constructor])
async def get_constructors(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Get all constructors (vendors)"""
    constructors = db.query(models.AntennaConstructor).order_by(
        models.AntennaConstructor.company_constructor
    ).all()
    return constructors


@router.post("/", response_model=Constructor, status_code=status.HTTP_201_CREATED)
async def create_constructor(
    constructor_in: ConstructorCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Create new constructor (vendor)"""
    # Check if constructor already exists
    existing_constructor = db.query(models.AntennaConstructor).filter(
        models.AntennaConstructor.company_constructor == constructor_in.company_constructor
    ).first()

    if existing_constructor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Constructor already exists"
        )

    # Create new constructor
    db_constructor = models.AntennaConstructor(
        company_constructor=constructor_in.company_constructor
    )

    db.add(db_constructor)
    db.commit()
    db.refresh(db_constructor)

    return db_constructor


@router.delete("/{company_constructor}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_constructor(
    company_constructor: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Delete constructor (vendor)"""
    constructor = db.query(models.AntennaConstructor).filter(
        models.AntennaConstructor.company_constructor == company_constructor
    ).first()

    if not constructor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Constructor not found"
        )

    db.delete(constructor)
    db.commit()

    return None


@router.get("/public", response_model=List[Constructor])
async def get_constructors_public(
    db: Session = Depends(get_db)
):
    """Get all constructors (public endpoint, no auth required)"""
    constructors = db.query(models.AntennaConstructor).order_by(
        models.AntennaConstructor.company_constructor
    ).all()
    return constructors

