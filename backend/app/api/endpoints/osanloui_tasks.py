#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Optional

import jdatetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user, get_current_user
from app.core.jalali_dates import apply_jalali_date_range_filter, normalize_jalali_date_string
from app.core.osanloui import can_manage_osanloui_tasks, is_osanloui_user
from app.db import models
from app.db.database import get_db
from app.schemas.osanloui_daily_task import (
    OsanlouiDailyTask,
    OsanlouiDailyTaskCreate,
    OsanlouiDailyTaskUpdate,
)

router = APIRouter()


def _normalize_task_date(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="تاریخ الزامی است")
    normalized = normalize_jalali_date_string(value) or value.replace(".", "/").replace("-", "/")
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="فرمت تاریخ نامعتبر است")
    return normalized.strip()


def _ensure_item_exists(db: Session, item_name: str) -> str:
    name = (item_name or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="نام آیتم الزامی است")
    item = db.query(models.RepairItem).filter(models.RepairItem.repair_item_name == name).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"آیتم تعمیر «{name}» یافت نشد",
        )
    return item.repair_item_name


@router.get("/", response_model=List[OsanlouiDailyTask])
async def list_osanloui_daily_tasks(
    item_name: Optional[str] = Query(None, description="جستجو بر اساس نام آیتم"),
    start_date: Optional[str] = Query(None, description="تاریخ اولیه"),
    end_date: Optional[str] = Query(None, description="تاریخ ثانویه"),
    skip: int = Query(0, ge=0),
    limit: int = Query(300, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> List[OsanlouiDailyTask]:
    if not can_manage_osanloui_tasks(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="دسترسی مجاز نیست")

    query = db.query(models.OsanlouiDailyTask)
    if current_user.user_type not in ("owner", "admin"):
        query = query.filter(models.OsanlouiDailyTask.personal_id == current_user.personal_id)

    if item_name and item_name.strip():
        for token in [t.strip() for t in item_name.split() if t.strip()]:
            query = query.filter(models.OsanlouiDailyTask.item_name.like(f"%{token}%"))

    query = apply_jalali_date_range_filter(
        query, models.OsanlouiDailyTask.task_date, start_date, end_date
    )
    rows = (
        query.order_by(
            models.OsanlouiDailyTask.task_date.desc(),
            models.OsanlouiDailyTask.id.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )
    return rows


@router.post("/", response_model=OsanlouiDailyTask, status_code=status.HTTP_201_CREATED)
async def create_osanloui_daily_task(
    payload: OsanlouiDailyTaskCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> OsanlouiDailyTask:
    if not is_osanloui_user(current_user) and current_user.user_type not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="فقط محمد اوسانلویی مجاز به ثبت Today's Task است",
        )

    item_name = _ensure_item_exists(db, payload.item_name)
    task_date = _normalize_task_date(payload.task_date)
    if payload.quantity < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="تعداد باید حداقل ۱ باشد")

    created_date = jdatetime.datetime.now().strftime("%Y/%m/%d")
    row = models.OsanlouiDailyTask(
        task_date=task_date,
        item_name=item_name,
        quantity=int(payload.quantity),
        personal_id=current_user.personal_id,
        user_first_name=current_user.user_first_name,
        user_last_name=current_user.user_last_name,
        created_date=created_date,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{task_id}", response_model=OsanlouiDailyTask)
async def update_osanloui_daily_task(
    task_id: int,
    payload: OsanlouiDailyTaskUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
) -> OsanlouiDailyTask:
    row = db.query(models.OsanlouiDailyTask).filter(models.OsanlouiDailyTask.id == task_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="رکورد یافت نشد")

    data = payload.model_dump(exclude_unset=True)
    if "item_name" in data and data["item_name"] is not None:
        row.item_name = _ensure_item_exists(db, data["item_name"])
    if "task_date" in data and data["task_date"] is not None:
        row.task_date = _normalize_task_date(data["task_date"])
    if "quantity" in data and data["quantity"] is not None:
        if int(data["quantity"]) < 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="تعداد باید حداقل ۱ باشد")
        row.quantity = int(data["quantity"])

    db.commit()
    db.refresh(row)
    return row


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_osanloui_daily_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
):
    row = db.query(models.OsanlouiDailyTask).filter(models.OsanlouiDailyTask.id == task_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="رکورد یافت نشد")
    db.delete(row)
    db.commit()
    return None
