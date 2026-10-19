#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Permission helpers for bulk repair operations."""

from app.db import models


def can_impersonate_repair_actor(user: models.User) -> bool:
    """
    Allow privileged users to attribute bulk repair operations
    to another user.
    """
    if user is None:
        return False

    return user.user_type == "owner"