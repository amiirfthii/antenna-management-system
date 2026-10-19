#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Optional

from sqlalchemy.orm import Session

from app.api.websocket import manager
from app.db import models

SECTION_LABELS = {
    "misc": "کارهای متفرقه",
    "door": "ساخت درب آنتن",
}


def get_admin_personal_ids(db: Session) -> List[str]:
    rows = (
        db.query(models.User.personal_id)
        .filter(
            models.User.is_active.is_(True),
            models.User.user_type.in_(("admin", "owner")),
        )
        .all()
    )
    return [str(row[0]) for row in rows]


def actor_display_name(user: models.User) -> str:
    first = (user.user_first_name or "").strip()
    last = (user.user_last_name or "").strip()
    name = f"{first} {last}".strip()
    return name or user.username


async def notify_admins_new_record(
    db: Session,
    *,
    actor: models.User,
    section: str,
    record_id: int,
    title: Optional[str] = None,
) -> None:
    admin_ids = [
        pid for pid in get_admin_personal_ids(db) if pid != str(actor.personal_id)
    ]
    if not admin_ids:
        return

    section_label = SECTION_LABELS.get(section, section)
    actor_name = actor_display_name(actor)
    message = f"{actor_name} در قسمت {section_label} رکورد جدید ثبت کرد"

    await manager.broadcast_to_users(
        {
            "type": "notification",
            "data": {
                "kind": "new_record",
                "section": section,
                "record_id": record_id,
                "message": message,
                "title": title,
                "actor_name": actor_name,
            },
        },
        admin_ids,
    )
