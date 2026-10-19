#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pydantic import BaseModel, field_validator
from typing import Optional, List

from app.core.jalali_dates import normalize_jalali_date_string


def _normalize_optional_date(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return value
    return normalize_jalali_date_string(value)


class RepairItemReportBase(BaseModel):
    repair_no: Optional[int] = None
    antenna_serial_no: Optional[str] = None
    manufacturer: Optional[str] = None
    personal_id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    item_name: Optional[str] = None
    fragment_name: Optional[str] = None
    fragment_part_no: Optional[str] = None
    arsenal_name: Optional[str] = None
    used_quantity: Optional[int] = None
    status: Optional[str] = None
    final_status: Optional[str] = None
    repair_date: Optional[str] = None
    antenna_type: Optional[str] = None
    item_code: Optional[str] = None
    item_description: Optional[str] = None

    @field_validator("repair_date", mode="before")
    @classmethod
    def normalize_repair_date(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional_date(value)


class RepairItemReportUpdate(BaseModel):
    manufacturer: Optional[str] = None
    antenna_serial_no: Optional[str] = None
    antenna_type: Optional[str] = None
    item_code: Optional[str] = None
    personal_id: Optional[int] = None
    item_name: Optional[str] = None
    status: Optional[str] = None
    final_status: Optional[str] = None
    repair_date: Optional[str] = None

    @field_validator("repair_date", mode="before")
    @classmethod
    def normalize_repair_date(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional_date(value)


class RepairItemReportCreate(RepairItemReportBase):
    pass


class RepairItemReport(RepairItemReportBase):
    id: int

    class Config:
        from_attributes = True


class RepairItemReportImportIssue(BaseModel):
    row_no: int
    reason: str
    result: str


class RepairItemReportImportResult(BaseModel):
    total: int
    imported: int
    failed: int
    skipped: int
    issues: List[RepairItemReportImportIssue] = []


class MissingItemCodePair(BaseModel):
    manufacturer: str
    antenna_type: str


class TiltSkipReason(BaseModel):
    reason: str
    count: int


class TiltSkippedRecord(BaseModel):
    id: int
    repair_no: Optional[int] = None
    antenna_serial_no: Optional[str] = None
    antenna_type: Optional[str] = None
    manufacturer: Optional[str] = None
    item_code: Optional[str] = None
    fragment_name: Optional[str] = None
    reason: str


class ApplyTiltQuantitiesResult(BaseModel):
    updated: int
    skipped: int
    unchanged: int
    inventory_adjusted: int = 0
    skip_reasons: List[TiltSkipReason] = []
    skipped_records: List[TiltSkippedRecord] = []


