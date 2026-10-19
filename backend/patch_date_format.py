#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch frontend bundle: accept dot or slash in Jalali date picker parse."""

from pathlib import Path

JS_PATH = Path(__file__).parent / "frontend_dist" / "assets" / "index-D2kbDbLZ.js"

OLD = r'function NG(e){const n=RG(e.trim()).match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})$/);'
NEW = r'function NG(e){const n=RG(e.trim()).match(/^(\d{4})[./](\d{1,2})[./](\d{1,2})$/);'


def main() -> None:
    content = JS_PATH.read_text(encoding="utf-8")
    if NEW.split("(")[1][:20] in content:
        print("Date parse patch already applied")
        return
    if OLD not in content:
        raise SystemExit("Jalali date parse marker not found in bundle")
    JS_PATH.write_text(content.replace(OLD, NEW, 1), encoding="utf-8")
    print("Date parse patch applied")


if __name__ == "__main__":
    main()
