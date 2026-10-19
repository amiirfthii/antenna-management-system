#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Map English city names (as used in Received Excel) to Persian province names."""

from __future__ import annotations

import re
from typing import Optional

from app.core.iran_provinces import IRAN_PROVINCES

# Major cities / logistics hubs used in province incoming spreadsheets.
CITY_TO_PROVINCE: dict[str, str] = {
    "tehran": "تهران",
    "karaj": "البرز",
    "mashhad": "خراسان رضوی",
    "isfahan": "اصفهان",
    "esfahan": "اصفهان",
    "shiraz": "فارس",
    "tabriz": "آذربایجان شرقی",
    "ahvaz": "خوزستان",
    "abadan": "خوزستان",
    "khorramabad": "لرستان",
    "kermanshah": "کرمانشاه",
    "rasht": "گیلان",
    "bandar abbas": "هرمزگان",
    "bandarabbas": "هرمزگان",
    "kerman": "کرمان",
    "yazd": "یزد",
    "qom": "قم",
    "qazvin": "قزوین",
    "zanjan": "زنجان",
    "hamadan": "همدان",
    "hamedan": "همدان",
    "sanandaj": "کردستان",
    "ardabil": "اردبیل",
    "urmia": "آذربایجان غربی",
    "orumié": "آذربایجان غربی",
    "sari": "مازندران",
    "gorgan": "گلستان",
    "birjand": "خراسان جنوبی",
    "bojnurd": "خراسان شمالی",
    "shahroud": "سمنان",
    "semnan": "سمنان",
    "yasuj": "کهگیلویه و بویراحمد",
    "bushehr": "بوشهر",
    "ilam": "ایلام",
    "arak": "مرکزی",
    "zahedan": "سیستان و بلوچستان",
    "chabahar": "سیستان و بلوچستان",
}


def _norm_city_key(value: str) -> str:
    text = (value or "").strip().lower()
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def resolve_city_to_province(city: str) -> Optional[str]:
    """Return canonical Persian province for an English city name."""
    key = _norm_city_key(city)
    if not key:
        return None

    if key in CITY_TO_PROVINCE:
        return CITY_TO_PROVINCE[key]

    # Direct Persian province name pasted into CITY column.
    for province in IRAN_PROVINCES:
        if key == province.lower() or key == _norm_city_key(province):
            return province

    # Partial match for common spellings (e.g. "Mashhad City").
    for city_name, province in CITY_TO_PROVINCE.items():
        if key == city_name or key.startswith(city_name + " ") or key.endswith(" " + city_name):
            return province

    return None
