#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Optional

import jdatetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user, get_current_user
from app.core.admin_notifications import notify_admins_new_record
from app.core.jalali_dates import apply_jalali_date_range_filter, normalize_jalali_date_string
from app.db import models
from app.db.database import get_db
from app.schemas.miscellaneous_task import (
    MiscellaneousTask,
    MiscellaneousTaskCreate,
    MiscellaneousTaskUpdate,
)

router = APIRouter()


def _normalize_task_date(raw: Optional[str]) -> str:
    value = (raw or "").strip()
    if not value:
        return jdatetime.datetime.now().strftime("%Y/%m/%d")
    normalized = normalize_jalali_date_string(value) or value.replace(".", "/").replace("-", "/")
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="فرمت تاریخ نامعتبر است")
    return normalized.strip()


def _apply_title_filter(query, title: Optional[str]):
    if not title or not title.strip():
        return query
    tokens = [t.strip() for t in title.split() if t.strip()]
    for token in tokens:
        query = query.filter(models.MiscellaneousTask.title.like(f"%{token}%"))
    return query


@router.get("/", response_model=List[MiscellaneousTask])
async def list_miscellaneous_tasks(
    title: Optional[str] = Query(None, description="جستجو بر اساس موضوع"),
    start_date: Optional[str] = Query(None, description="تاریخ اولیه"),
    end_date: Optional[str] = Query(None, description="تاریخ ثانویه"),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
) -> List[MiscellaneousTask]:
    query = db.query(models.MiscellaneousTask)
    query = _apply_title_filter(query, title)
    query = apply_jalali_date_range_filter(query, models.MiscellaneousTask.created_date, start_date, end_date)
    rows = (
        query.order_by(models.MiscellaneousTask.created_date.desc(), models.MiscellaneousTask.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return rows


@router.post("/", response_model=MiscellaneousTask, status_code=status.HTTP_201_CREATED)
async def create_miscellaneous_task(
    payload: MiscellaneousTaskCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> MiscellaneousTask:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="موضوع الزامی است")

    created_date = _normalize_task_date(payload.created_date)
    row = models.MiscellaneousTask(
        title=title,
        description=(payload.description or "").strip(),
        personal_id=current_user.personal_id,
        user_first_name=current_user.user_first_name,
        user_last_name=current_user.user_last_name,
        created_date=created_date,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    await notify_admins_new_record(
        db,
        actor=current_user,
        section="misc",
        record_id=row.id,
        title=row.title,
    )
    return row


@router.get("/{task_id}", response_model=MiscellaneousTask)
async def get_miscellaneous_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
) -> MiscellaneousTask:
    row = db.query(models.MiscellaneousTask).filter(models.MiscellaneousTask.id == task_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="رکورد یافت نشد")
    return row


@router.put("/{task_id}", response_model=MiscellaneousTask)
async def update_miscellaneous_task(
    task_id: int,
    payload: MiscellaneousTaskUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
) -> MiscellaneousTask:
    row = db.query(models.MiscellaneousTask).filter(models.MiscellaneousTask.id == task_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="رکورد یافت نشد")

    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="موضوع نمی‌تواند خالی باشد")
        row.title = title
    if payload.description is not None:
        row.description = payload.description.strip()
    if payload.created_date is not None:
        row.created_date = _normalize_task_date(payload.created_date)

    db.commit()
    db.refresh(row)
    return row


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_miscellaneous_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
) -> None:
    row = db.query(models.MiscellaneousTask).filter(models.MiscellaneousTask.id == task_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="رکورد یافت نشد")
    db.delete(row)
    db.commit()
