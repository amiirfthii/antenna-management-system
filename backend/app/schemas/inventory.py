#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pydantic import BaseModel, field_validator
from typing import Optional

from app.core.arsenal import ALL_ARSENAL_TYPES
from app.core.jalali_dates import normalize_jalali_date_string


class InventoryBase(BaseModel):
    fragment_part_no: str
    arsenal_name: str
    fragment_name: str
    fragment_qty: int


class InventoryCreate(BaseModel):
    fragment_name: str
    fragment_part_no: str
    arsenal_name: str
    fragment_qty: int
    entry_date: Optional[str] = None

    @field_validator("arsenal_name")
    @classmethod
    def validate_arsenal_name(cls, value: str) -> str:
        if value not in ALL_ARSENAL_TYPES:
            raise ValueError(f"نوع انبار باید یکی از {', '.join(ALL_ARSENAL_TYPES)} باشد")
        return value

    @field_validator("entry_date", mode="before")
    @classmethod
    def normalize_entry_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return value
        return normalize_jalali_date_string(value)


class InventoryUpdate(BaseModel):
    fragment_name: Optional[str] = None
    fragment_qty: Optional[int] = None
    initial_qty: Optional[int] = None


class Inventory(InventoryBase):
    class Config:
        from_attributes = True


class InventoryWithdrawal(BaseModel):
    part_no: str
    quantity: int


class InventoryHistory(BaseModel):
    id: int
    part_no: str
    operation_type: str
    quantity: int
    personal_id: str
    operation_date: str

    @field_validator("operation_date", mode="before")
    @classmethod
    def normalize_operation_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return value
        return normalize_jalali_date_string(value)

    class Config:
        from_attributes = True


class SupplyFragmentEntry(BaseModel):
    fragment_entry_no: int
    fragment_entry_name: Optional[str] = None
    fragment_entry_qty: Optional[int] = None
    fragment_entry_date: Optional[str] = None
    fragment_part_no: Optional[str] = None
    arsenal_name: Optional[str] = None

    @field_validator("fragment_entry_date", mode="before")
    @classmethod
    def normalize_fragment_entry_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return value
        return normalize_jalali_date_string(value)

    class Config:
        from_attributes = True
