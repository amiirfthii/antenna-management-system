#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest

from app.core.jalali_dates import normalize_jalali_date_string


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1404.12.06", "1404/12/06"),
        ("1404/12/06", "1404/12/06"),
        ("1404.12.06 14:30:00", "1404/12/06 14:30:00"),
        ("1404/1/6", "1404/01/06"),
        ("1404.1.6", "1404/01/06"),
        ("", ""),
        (None, None),
        ("not-a-date", "not-a-date"),
        ("1404.12.06 14:30", "1404/12/06 14:30"),
    ],
)
def test_normalize_jalali_date_string(raw, expected):
    assert normalize_jalali_date_string(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1404/12/29", "1404/12/29 23:59:59"),
        ("1404/12/29 10:00:00", "1404/12/29 10:00:00"),
        (None, None),
    ],
)
def test_jalali_end_date_upper_bound(raw, expected):
    from app.core.jalali_dates import jalali_end_date_upper_bound

    assert jalali_end_date_upper_bound(raw) == expected


def test_persian_digits_normalized():
    assert normalize_jalali_date_string("۱۴۰۵/۰۲/۰۱") == "1405/02/01"
    assert normalize_jalali_date_string("1405.02.02") == "1405/02/02"
