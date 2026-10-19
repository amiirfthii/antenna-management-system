#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import html
from io import BytesIO
from typing import Any, List, Literal

import jdatetime
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from pydantic import BaseModel

from app.api.deps import get_current_admin_user
from app.db import models

router = APIRouter()


class ReportExportRequest(BaseModel):
    title: str
    headers: List[str]
    rows: List[List[Any]]
    file_base_name: str = "report"
    format: Literal["excel", "word"]


def _build_word_html(title: str, headers: List[str], rows: List[List[Any]]) -> str:
    header_cells = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body = []
    for row in rows:
        cells = "".join(
            f"<td>{html.escape(str(c if c is not None else ''))}</td>" for c in row
        )
        body.append(f"<tr>{cells}</tr>")
    return f"""<!DOCTYPE html>
<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word">
<head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
table {{ border-collapse: collapse; width: 100%; direction: rtl; font-family: Tahoma, Arial, sans-serif; }}
th, td {{ border: 1px solid #333; padding: 6px; text-align: center; }}
th {{ background: #f0f0f0; font-weight: bold; }}
h2 {{ text-align: center; direction: rtl; }}
</style></head>
<body dir="rtl">
<h2>{html.escape(title)}</h2>
<table><thead><tr>{header_cells}</tr></thead><tbody>{''.join(body)}</tbody></table>
</body></html>"""


@router.post("/export")
async def export_report(
    request: ReportExportRequest,
    current_user: models.User = Depends(get_current_admin_user),
):
    if not request.rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="داده‌ای برای خروجی وجود ندارد",
        )

    ts = jdatetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = request.file_base_name or "report"

    if request.format == "excel":
        wb = Workbook()
        ws = wb.active
        ws.title = "Report"
        ws.append(request.headers)
        for row in request.rows:
            ws.append([c if c is not None else "" for c in row])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        filename = f"{safe_name}_{ts}.xlsx"
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    html_content = _build_word_html(request.title, request.headers, request.rows)
    buf = BytesIO(html_content.encode("utf-8-sig"))
    filename = f"{safe_name}_{ts}.doc"
    return StreamingResponse(
        buf,
        media_type="application/msword",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
