#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Classify antenna model strings into X-type buckets (2X, 3X, X-Pole, …)."""

from __future__ import annotations

import re
from typing import List

# Display order on dashboard charts
ANTENNA_X_BUCKET_ORDER: List[str] = [
    "X-Pole",
    "V-Pole",
    "2X",
    "3X",
    "4X",
    "5X",
    "6X",
    "7X",
    "8X",
    "9X",
    "TDD",
    "X",
    "سایر",
]

_BUCKET_SORT = {name: index for index, name in enumerate(ANTENNA_X_BUCKET_ORDER)}


def classify_antenna_x_bucket(antenna_type: str) -> str:
    text = (antenna_type or "").strip()
    if not text:
        return "سایر"

    lowered = text.lower().replace("_", "-")
    lowered = re.sub(r"\s+", "", lowered)

    if "tdd" in lowered:
        return "TDD"

    if "v-pole" in lowered or "vpole" in lowered:
        return "V-Pole"

    # Nx-pole must be checked before plain x-pole ("2x-pole" contains "x-pole").
    match = re.search(r"(?:^|[^\d])(\d+)[xX]-?pole", lowered)
    if match:
        count = int(match.group(1))
        if count <= 1:
            return "X-Pole"
        bucket = f"{count}X"
        return bucket if bucket in _BUCKET_SORT else "سایر"

    if "x-pole" in lowered or "xpole" in lowered or "xpole" == lowered:
        return "X-Pole"

    match = re.search(r"(?:^|[^\d])(\d+)\s*[xX](?:\b|[-/])", text)
    if not match:
        match = re.match(r"^(\d+)\s*[xX]", text)
    if match:
        count = int(match.group(1))
        if count <= 1:
            return "X"
        bucket = f"{count}X"
        return bucket if bucket in _BUCKET_SORT else "سایر"

    match = re.search(r"MQ(\d+)", text, re.IGNORECASE)
    if match:
        count = int(match.group(1))
        bucket = f"{count}X"
        return bucket if bucket in _BUCKET_SORT else "سایر"

    if re.match(r"^[xX][-/]", text) or re.match(r"^[xX]\d", text):
        return "X"

    return "سایر"


def antenna_x_bucket_sort_key(bucket: str) -> tuple[int, str]:
    return (_BUCKET_SORT.get(bucket, len(ANTENNA_X_BUCKET_ORDER)), bucket)
