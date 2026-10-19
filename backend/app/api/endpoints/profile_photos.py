#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.profile_photos import (
    get_photo_url,
    get_photo_version,
    resolve_photo_path,
)

router = APIRouter()


@router.get("/profile-photos/url")
async def profile_photo_url(
    user_first_name: str = Query(...),
    user_last_name: str = Query(...),
):
    return {"url": get_photo_url(user_first_name, user_last_name)}


@router.get("/profile-photos/{filename:path}")
async def serve_profile_photo(filename: str):
    filename = unquote(filename)
    path = resolve_photo_path(filename)
    if not path:
        raise HTTPException(status_code=404, detail="Profile photo not found")

    version = get_photo_version(filename)
    return FileResponse(
        path,
        media_type="image/png",
        headers={
            "Cache-Control": "no-cache, must-revalidate",
            "ETag": f'W/"{version}"',
        },
    )
