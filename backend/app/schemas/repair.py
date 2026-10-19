#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, List

from app.core.jalali_dates import normalize_jalali_date_string


def _normalize_optional_date(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return value
    return normalize_jalali_date_string(value)


class RepairBase(BaseModel):
    antenna_serial_no: str
    antenna_type: Optional[str] = None
    antenna_entry_type: str
    constructor: Optional[str] = None
    entry_date: Optional[str] = None
    tilt: Optional[str] = None
    item_code: Optional[str] = None


class RepairCreate(RepairBase):
    antenna_status: str = "نامعلوم"
    no_serial_category: Optional[str] = None
    allow_duplicate_re_registration: bool = False

    @field_validator("entry_date", mode="before")
    @classmethod
    def normalize_entry_date(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional_date(value)


class RepairUpdate(BaseModel):
    antenna_serial_no: Optional[str] = None
    antenna_type: Optional[str] = None
    antenna_entry_type: Optional[str] = None
    constructor: Optional[str] = None
    entry_date: Optional[str] = None
    exit_date: Optional[str] = None
    tilt: Optional[str] = None
    item_code: Optional[str] = None
    antenna_status: Optional[str] = None
    admin_id: Optional[int] = None
    antenna_admin_check_date: Optional[str] = None
    no_serial_category: Optional[str] = None

    @field_validator(
        "entry_date",
        "exit_date",
        "antenna_admin_check_date",
        mode="before",
    )
    @classmethod
    def normalize_dates(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional_date(value)


class Repair(RepairBase):
    repair_no: int
    exit_date: Optional[str] = None
    admin_id: Optional[int] = None
    antenna_status: str
    antenna_admin_check_date: Optional[str] = None
    no_serial_category: Optional[str] = None

    @model_validator(mode="after")
    def fill_province_category(self):
        current = (self.no_serial_category or "").strip()
        if current:
            return self
        raw = normalize_jalali_date_string(self.entry_date) or ""
        if len(raw) >= 10 and raw[:10] >= "1405/01/01":
            self.no_serial_category = "استان"
        return self

    @field_validator(
        "entry_date",
        "exit_date",
        "antenna_admin_check_date",
        mode="before",
    )
    @classmethod
    def normalize_dates(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional_date(value)

    class Config:
        from_attributes = True


class RepairStepBase(BaseModel):
    repair_no: int
    repair_item_name: str
    item_status: str = "انجام نشده"
    personal_id: Optional[int] = None


class RepairStepCreate(RepairStepBase):
    pass


class RepairStepUpdate(BaseModel):
    item_status: Optional[str] = None
    end_date: Optional[str] = None
    item_code: Optional[str] = None

    @field_validator("end_date", mode="before")
    @classmethod
    def normalize_end_date(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional_date(value)


class RepairStep(RepairStepBase):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    item_code: Optional[str] = None

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def normalize_dates(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional_date(value)

    class Config:
        from_attributes = True


class RepairPartUsage(BaseModel):
    fragment_part_no: str
    fragment_name: str
    arsenal_name: str
    quantity: int
    description: Optional[str] = None


class RepairQueueGroup(BaseModel):
    vendor: str
    antenna_type: str
    count: int


class RepairItemSubmission(BaseModel):
    item_name: str
    description: Optional[str] = None
    parts: List["RepairPartUsage"] = []


class SubmitRepairItemsRequest(BaseModel):
    item_status: str
    items: List[RepairItemSubmission]
    end_date: Optional[str] = None
    acting_personal_id: Optional[int] = None

    @field_validator("end_date", mode="before")
    @classmethod
    def normalize_end_date(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional_date(value)


class BulkSubmitRepairItemsRequest(BaseModel):
    repair_nos: List[int]
    item_status: str
    items: List[RepairItemSubmission]
    end_date: Optional[str] = None
    acting_personal_id: Optional[int] = None

    @field_validator("end_date", mode="before")
    @classmethod
    def normalize_end_date(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional_date(value)


class SubmitRepairItemsResponse(BaseModel):
    message: str
    reports_created: int


class BulkSubmitRepairItemsResponse(BaseModel):
    message: str
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    reports_created: int = 0
    errors: List[str] = []


class BulkDeleteRepairItemsRequest(BaseModel):
    repair_nos: List[int]
    item_name: str


class BulkDeleteRepairItemsResponse(BaseModel):
    message: str
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    deleted_reports: int = 0
    errors: List[str] = []


class SerialExcelImportedRow(BaseModel):
    repair_no: Optional[int] = None
    serial: str
    vendor: str
    antenna_type: str
    item_code: str
    entry_date: Optional[str] = None
    category: Optional[str] = None


class SerialExcelImportResult(BaseModel):
    total: int = 0
    imported: int = 0
    failed: int = 0
    errors: List[str] = []
    imported_rows: List[SerialExcelImportedRow] = []


class SerialRangeImportRequest(BaseModel):
    serial_from: str
    serial_to: str
    antenna_type: str
    constructor: str
    antenna_entry_type: str
    item_code: str
    no_serial_category: str
    entry_date: Optional[str] = None

    @field_validator("entry_date", mode="before")
    @classmethod
    def normalize_entry_date(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional_date(value)


class PackagingExcelPackagedRow(BaseModel):
    repair_no: Optional[int] = None
    serial: str
    vendor: str
    antenna_type: str
    packaging_date: Optional[str] = None
    status: str = "تایید"


class PackagingExcelApplyResult(BaseModel):
    total_in_file: int = 0
    packaged: int = 0
    exited: int = 0
    failed: int = 0
    errors: List[str] = []
    packaged_rows: List[PackagingExcelPackagedRow] = []
