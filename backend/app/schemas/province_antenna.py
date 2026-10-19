#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

CATEGORY_PROVINCE = "استان"
CATEGORY_DEPRECIATED = "مستهلک"
NoSerialCategory = Literal["استان", "مستهلک"]


class ItemCodePair(BaseModel):
    vendor: str
    antenna_type: str
    item_code: str
    tilt_type: Optional[str] = None


class NoSerialAntennaMeta(BaseModel):
    vendors: List[str]
    antenna_types: List[str]
    provinces: List[str]
    item_codes: List[ItemCodePair] = []


class NoSerialAntennaCreate(BaseModel):
    vendor: str
    antenna_type: str
    item_code: str
    quantity: int = Field(..., gt=0)
    category: NoSerialCategory = CATEGORY_PROVINCE
    province: Optional[str] = None
    entry_date: Optional[str] = None


class NoSerialAntennaUpdate(BaseModel):
    vendor: Optional[str] = None
    antenna_type: Optional[str] = None
    item_code: Optional[str] = None
    quantity: Optional[int] = Field(None, gt=0)
    category: Optional[NoSerialCategory] = None
    province: Optional[str] = None
    entry_date: Optional[str] = None


class NoSerialAntenna(BaseModel):
    id: int
    vendor: str
    antenna_type: str
    item_code: str
    category: str
    province: str
    quantity: int
    remaining_quantity: Optional[int] = None
    created_date: Optional[str] = None
    entry_date: Optional[str] = None

    @model_validator(mode="after")
    def sync_entry_date(self):
        date = self.entry_date or self.created_date
        self.entry_date = date
        self.created_date = date
        if self.remaining_quantity is None:
            self.remaining_quantity = int(self.quantity or 0)
        return self

    class Config:
        from_attributes = True


class NoSerialAntennaImportResult(BaseModel):
    total: int = 0
    imported: int = 0
    failed: int = 0
    errors: List[str] = []


# backward-compatible aliases
ProvinceAntennaMeta = NoSerialAntennaMeta
ProvinceAntennaCreate = NoSerialAntennaCreate
ProvinceAntenna = NoSerialAntenna
ProvinceAntennaImportResult = NoSerialAntennaImportResult
