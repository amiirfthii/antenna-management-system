#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import unicodedata
from urllib.parse import quote

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROFILE_PHOTOS_DIR = os.path.dirname(os.path.dirname(BACKEND_ROOT))

USER_PHOTO_FILES: dict[tuple[str, str], str] = {}

ALLOWED_FILES = set(USER_PHOTO_FILES.values())


def _normalize_name(name: str) -> str:
    """Normalize Persian names for consistent photo lookup."""
    name = unicodedata.normalize("NFC", name.strip())
    name = re.sub(r"[\u200c\u200d\ufeff]", "", name)
    return re.sub(r"\s+", " ", name)


_NORMALIZED_PHOTO_FILES: dict[tuple[str, str], str] = {
    (_normalize_name(first), _normalize_name(last)): filename
    for (first, last), filename in USER_PHOTO_FILES.items()
}


def get_photo_filename(first_name: str, last_name: str) -> str | None:
    key = (_normalize_name(first_name), _normalize_name(last_name))
    return _NORMALIZED_PHOTO_FILES.get(key)


def resolve_photo_path(filename: str) -> str | None:
    if filename not in ALLOWED_FILES:
        return None
    if not os.path.isdir(PROFILE_PHOTOS_DIR):
        return None

    exact = os.path.join(PROFILE_PHOTOS_DIR, filename)
    if os.path.isfile(exact):
        return exact

    target = filename.lower()
    for entry in os.listdir(PROFILE_PHOTOS_DIR):
        if entry.lower() == target:
            return os.path.join(PROFILE_PHOTOS_DIR, entry)
    return None


def get_photo_version(filename: str) -> int | None:
    path = resolve_photo_path(filename)
    if not path:
        return None
    return int(os.path.getmtime(path))


def get_photo_url(first_name: str, last_name: str) -> str | None:
    filename = get_photo_filename(first_name, last_name)
    if not filename:
        return None
    version = get_photo_version(filename)
    if version is None:
        return None
    return f"/api/profile-photos/{quote(filename)}?v={version}"
