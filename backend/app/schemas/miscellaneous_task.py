#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Optional

from pydantic import BaseModel, Field


class MiscellaneousTaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=191)
    description: str = Field("", max_length=2000)
    created_date: Optional[str] = Field(None, min_length=1, max_length=50)


class MiscellaneousTaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=191)
    description: Optional[str] = Field(None, max_length=2000)
    created_date: Optional[str] = Field(None, min_length=1, max_length=50)


class MiscellaneousTask(BaseModel):
    id: int
    title: str
    description: str
    personal_id: int
    user_first_name: Optional[str] = None
    user_last_name: Optional[str] = None
    created_date: str

    class Config:
        from_attributes = True
