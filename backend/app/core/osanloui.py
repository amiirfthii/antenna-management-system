#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helpers for Mohammad Osanloui (اسانلویی / اوسانلویی) daily tasks."""

from __future__ import annotations

import re
import unicodedata

from app.db import models


def _norm_name(value: str) -> str:
    text = unicodedata.normalize("NFC", (value or "").strip())
    text = re.sub(r"[\u200c\u200d\ufeff]", "", text)
    return re.sub(r"\s+", " ", text)


def is_osanloui_user(user: models.User | None) -> bool:
    """Match محمد اسانلویی / محمد اوسانلویی (DB spelling may vary)."""
    if user is None:
        return False
    first = _norm_name(user.user_first_name or "")
    last = _norm_name(user.user_last_name or "")
    if first != "محمد":
        return False
    return ("اسانلویی" in last) or ("اوسانلویی" in last)


def can_manage_osanloui_tasks(user: models.User) -> bool:
    """Admins/owners manage reports; Osanloui can create his own tasks."""
    if user.user_type in ("owner", "admin"):
        return True
    return is_osanloui_user(user)
