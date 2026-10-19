#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pydantic import BaseModel, Field
from typing import Optional


class UserBase(BaseModel):
    personal_id: int
    user_first_name: str
    user_last_name: str
    user_type: str
    username: str


class UserCreate(UserBase):
    password: str = Field(..., min_length=4)


class UserUpdate(BaseModel):
    user_first_name: Optional[str] = None
    user_last_name: Optional[str] = None
    user_type: Optional[str] = None
    password: Optional[str] = None


class UserInDB(UserBase):
    password_hash: str
    is_active: bool = True

    class Config:
        from_attributes = True


class User(UserBase):
    is_active: bool = True

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: Optional[str] = None
    personal_id: Optional[int] = None
    user_type: Optional[str] = None
