#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db import models


def is_admin_or_owner(user: models.User) -> bool:
    return user.user_type in ("admin", "owner")


def user_owns_repair(db: Session, user: models.User, repair_no: int) -> bool:
    pid = user.personal_id
    has_step = db.query(models.RepairStep).filter(
        models.RepairStep.repair_no == repair_no,
        models.RepairStep.personal_id == pid,
    ).first()
    if has_step:
        return True
    has_report = db.query(models.RepairItemReport).filter(
        models.RepairItemReport.repair_no == repair_no,
        models.RepairItemReport.personal_id == pid,
    ).first()
    return has_report is not None


REPAIR_QUEUE_STATUSES = ("نامعلوم", "فالتی_در_انتظار_تعمیر")


def _is_in_repair_queue(repair: models.Repair | None) -> bool:
    return bool(
        repair
        and repair.antenna_entry_type == "ورودی_تعمیر"
        and repair.antenna_status in REPAIR_QUEUE_STATUSES
    )


def can_access_repair(db: Session, user: models.User, repair_no: int, *, allow_queue: bool = False) -> bool:
    if is_admin_or_owner(user):
        return True
    if user_owns_repair(db, user, repair_no):
        return True
    if not allow_queue:
        return False
    repair = db.query(models.Repair).filter(models.Repair.repair_no == repair_no).first()
    return _is_in_repair_queue(repair)


def assert_repair_access(
    db: Session,
    user: models.User,
    repair_no: int,
    *,
    allow_queue: bool = False,
) -> None:
    if can_access_repair(db, user, repair_no, allow_queue=allow_queue):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not enough permissions",
    )


def assert_repair_update_access(
    db: Session,
    user: models.User,
    repair_no: int,
    update_data: dict,
) -> None:
    if is_admin_or_owner(user):
        return
    if user_owns_repair(db, user, repair_no):
        return
    repair = db.query(models.Repair).filter(models.Repair.repair_no == repair_no).first()
    if (
        _is_in_repair_queue(repair)
        and set(update_data.keys()) <= {"antenna_status"}
        and update_data.get("antenna_status") == "در_انتظار_تایید"
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not enough permissions",
    )


def assert_report_access(db: Session, user: models.User, report: models.RepairItemReport) -> None:
    if is_admin_or_owner(user):
        return
    if report.personal_id != user.personal_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
