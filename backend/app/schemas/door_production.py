#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Optional

from pydantic import BaseModel, Field


class DoorPartUsage(BaseModel):
    fragment_part_no: str = Field(..., min_length=1, max_length=100)
    fragment_name: Optional[str] = Field(None, max_length=191)
    arsenal_name: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., gt=0)


class DoorProductionCreate(BaseModel):
    vendor: str = Field(..., min_length=1, max_length=191)
    antenna_type: str = Field(..., min_length=1, max_length=191)
    item_code: Optional[str] = Field(None, max_length=100)
    quantity: int = Field(..., gt=0)
    description: str = Field("", max_length=2000)
    parts: List[DoorPartUsage] = Field(default_factory=list)


class DoorProductionUpdate(DoorProductionCreate):
    pass


class DoorProductionPartOut(DoorPartUsage):
    id: int

    class Config:
        from_attributes = True


class DoorProduction(BaseModel):
    id: int
    vendor: str
    antenna_type: str
    item_code: Optional[str] = None
    quantity: int
    description: str
    personal_id: int
    user_first_name: Optional[str] = None
    user_last_name: Optional[str] = None
    created_date: str
    parts: List[DoorProductionPartOut] = []

    class Config:
        from_attributes = True
