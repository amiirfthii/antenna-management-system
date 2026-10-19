#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional

from pydantic import BaseModel, Field


class OsanlouiDailyTaskCreate(BaseModel):
    task_date: str = Field(..., min_length=1, max_length=50)
    item_name: str = Field(..., min_length=1, max_length=191)
    quantity: int = Field(..., ge=1)


class OsanlouiDailyTaskUpdate(BaseModel):
    task_date: Optional[str] = Field(None, min_length=1, max_length=50)
    item_name: Optional[str] = Field(None, min_length=1, max_length=191)
    quantity: Optional[int] = Field(None, ge=1)


class OsanlouiDailyTask(BaseModel):
    id: int
    task_date: str
    item_name: str
    quantity: int
    personal_id: int
    user_first_name: Optional[str] = None
    user_last_name: Optional[str] = None
    created_date: str

    class Config:
        from_attributes = True
