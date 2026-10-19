#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from fastapi import APIRouter, Request, Depends, Form, status as http_status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import Optional
from jose import JWTError

from app.api.deps import get_db
from app.core.security import create_access_token, verify_password, decode_token
from app.core.config import settings
from app.core.jalali_dates import normalize_jalali_date_string
from app.db import models

import os

from app.core.profile_photos import get_photo_url

# Setup templates
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

router = APIRouter()


# Helper function to get current user from cookie
async def get_user_from_cookie(request: Request, db: Session) -> Optional[models.User]:
    """Get current user from JWT token in cookie"""
    token = request.cookies.get("access_token")
    if not token:
        return None

    # Extract token from "Bearer <token>" format
    if token.startswith("Bearer "):
        token = token[7:]

    try:
        # Decode token
        payload = decode_token(token)
        username: str = payload.get("sub")
        if not username:
            return None

        # Get user from database
        user = db.query(models.User).filter(models.User.username == username).first()
        if not user or not user.is_active:
            return None

        return user

    except JWTError:
        # مشکل در توکن (expire/invalid و ...)
        return None
    except Exception:
        # هر خطای دیگر را امن‌طور نادیده می‌گیریم
        return None


@router.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    db: Session = Depends(get_db),
    search: Optional[str] = None,
):
    """Display users page"""
    user = await get_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=http_status.HTTP_302_FOUND)

    # Only admin and owner can access
    if user.user_type not in ["admin", "owner"]:
        return RedirectResponse(url="/dashboard", status_code=http_status.HTTP_302_FOUND)

    try:
        query = db.query(models.User).filter(models.User.is_active.is_(True))

        if search:
            query = query.filter(
                (models.User.username.contains(search))
                | (models.User.user_first_name.contains(search))
                | (models.User.user_last_name.contains(search))
            )

        users = query.order_by(models.User.user_first_name).all()
    except Exception:
        users = []

    return templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "user": user,
            "users": users,
            "search": search,
        },
    )


@router.post("/users/create")
async def create_user(
    request: Request,
    db: Session = Depends(get_db),
    personal_id: int = Form(...),
    user_first_name: str = Form(...),
    user_last_name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    user_type: str = Form(...),
):
    """Create new user (admin/owner only)"""
    user = await get_user_from_cookie(request, db)
    if not user or user.user_type not in ["admin", "owner"]:
        return RedirectResponse(url="/login", status_code=http_status.HTTP_302_FOUND)

    try:
        from app.core.security import get_password_hash

        # Check if username exists
        existing = (
            db.query(models.User).filter(models.User.username == username).first()
        )
        if existing:
            return templates.TemplateResponse(
                "users.html",
                {
                    "request": request,
                    "user": user,
                    "users": [],
                    "error": "نام کاربری تکراری است",
                },
            )

        new_user = models.User(
            personal_id=personal_id,
            user_first_name=user_first_name,
            user_last_name=user_last_name,
            username=username,
            password_hash=get_password_hash(password),
            user_type=user_type,
            is_active=True,
        )

        db.add(new_user)
        db.commit()
    except Exception as e:
        db.rollback()
        return templates.TemplateResponse(
            "users.html",
            {
                "request": request,
                "user": user,
                "users": [],
                "error": f"خطا در ثبت کاربر: {str(e)}",
            },
        )

    return RedirectResponse(url="/users", status_code=http_status.HTTP_302_FOUND)


@router.get("/", response_class=HTMLResponse)
async def root(request: Request, db: Session = Depends(get_db)):
    """Redirect to login or dashboard"""
    user = await get_user_from_cookie(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=http_status.HTTP_302_FOUND)
    return RedirectResponse(url="/login", status_code=http_status.HTTP_302_FOUND)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Display login page"""
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Handle login form submission"""
    try:
        # Find user
        user = db.query(models.User).filter(models.User.username == username).first()

        if not user or not verify_password(password, user.password_hash):
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "نام کاربری یا رمز عبور اشتباه است"},
            )

        if not user.is_active:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "کاربر غیرفعال است"},
            )

        # Create access token
        access_token_expires = timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        access_token = create_access_token(
            data={
                "sub": user.username,
                "personal_id": user.personal_id,
                "user_type": user.user_type,
            },
            expires_delta=access_token_expires,
        )

        # Create response and set cookie
        response = RedirectResponse(
            url="/dashboard", status_code=http_status.HTTP_302_FOUND
        )
        response.set_cookie(
            key="access_token",
            value=f"Bearer {access_token}",
            httponly=True,
            max_age=1800,  # 30 minutes
            expires=1800,
        )
        return response

    except Exception as e:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": f"خطا در ورود: {str(e)}"},
        )


@router.get("/logout")
async def logout():
    """Handle logout"""
    response = RedirectResponse(url="/login", status_code=http_status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    return response


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """Display dashboard"""
    user = await get_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=http_status.HTTP_302_FOUND)

    # Get statistics
    try:
        # Count repairs by status
        active_statuses = ["در_انتظار_تایید", "فالتی_در_انتظار_تعمیر"]
        stats = {
            "active_repairs": db.query(models.Repair)
            .filter(models.Repair.antenna_status.in_(active_statuses))
            .count(),
            "completed_repairs": db.query(models.Repair)
            .filter(models.Repair.antenna_status == "خروج")
            .count(),
            "inventory_items": db.query(models.ArsenalTable).count(),
            "total_users": db.query(models.User)
            .filter(models.User.is_active.is_(True))
            .count(),
        }

        # Get recent repairs
        recent_repairs = (
            db.query(models.Repair)
            .order_by(models.Repair.repair_no.desc())
            .limit(10)
            .all()
        )

        # Get low stock items (items with quantity less than 5)
        low_stock_items = (
            db.query(models.ArsenalTable)
            .filter(models.ArsenalTable.fragment_qty < 5)
            .limit(10)
            .all()
        )
    except Exception:
        stats = {
            "active_repairs": 0,
            "completed_repairs": 0,
            "inventory_items": 0,
            "total_users": 0,
        }
        recent_repairs = []
        low_stock_items = []

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "stats": stats,
            "recent_repairs": recent_repairs,
            "low_stock_items": low_stock_items,
            "profile_photo_url": get_photo_url(user.user_first_name, user.user_last_name),
        },
    )


@router.get("/repairs", response_class=HTMLResponse)
async def repairs_page(
    request: Request,
    db: Session = Depends(get_db),
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
):
    """Display repairs page"""
    user = await get_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=http_status.HTTP_302_FOUND)

    try:
        # Build query
        query = db.query(models.Repair)

        if status_filter:
            query = query.filter(models.Repair.antenna_status == status_filter)

        if search:
            query = query.filter(
                models.Repair.antenna_serial_no.contains(search)
            )

        # Pagination
        per_page = 20
        total_items = query.count()
        total_pages = (
            (total_items + per_page - 1) // per_page if total_items > 0 else 0
        )

        repairs = (
            query.order_by(models.Repair.repair_no.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
    except Exception:
        repairs = []
        total_pages = 0

    # Get antenna types and constructors for dropdowns
    antenna_types = db.query(models.AntennaType).all()
    constructors = db.query(models.AntennaConstructor).all()

    return templates.TemplateResponse(
        "repairs.html",
        {
            "request": request,
            "user": user,
            "repairs": repairs,
            "current_page": page,
            "total_pages": total_pages,
            "antenna_types": antenna_types,
            "constructors": constructors,
            "status_filter": status_filter,
            "search": search,
        },
    )


@router.post("/repairs/create")
async def create_repair(
    request: Request,
    db: Session = Depends(get_db),
    antenna_serial_no: str = Form(...),
    antenna_type: str = Form(...),
    antenna_entry_type: str = Form(...),
    constructor: str = Form(...),
    entry_date: str = Form(...),
    tilt: Optional[str] = Form(None),
    item_code: Optional[str] = Form(None),
):
    """Create new repair"""
    user = await get_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=http_status.HTTP_302_FOUND)

    try:
        from app.services.serial_uniqueness import (
            assert_serial_unique_for_create,
            normalize_serial,
        )

        normalized_serial = normalize_serial(antenna_serial_no)
        duplicate_error = assert_serial_unique_for_create(db, normalized_serial)
        if duplicate_error:
            return templates.TemplateResponse(
                "repairs.html",
                {
                    "request": request,
                    "user": user,
                    "error": duplicate_error,
                },
                status_code=http_status.HTTP_400_BAD_REQUEST,
            )

        repair = models.Repair(
            antenna_serial_no=normalized_serial,
            antenna_type=antenna_type,
            antenna_entry_type=antenna_entry_type,
            constructor=constructor,
            entry_date=normalize_jalali_date_string(entry_date) or entry_date,
            tilt=tilt,
            item_code=item_code,
            admin_id=user.personal_id
            if user.user_type in ["admin", "owner"]
            else None,
            antenna_status="در_انتظار_تایید",
        )

        db.add(repair)
        db.commit()
        db.refresh(repair)
    except Exception as e:
        db.rollback()
        # Return with error
        return templates.TemplateResponse(
            "repairs.html",
            {
                "request": request,
                "user": user,
                "repairs": [],
                "error": f"خطا در ثبت تعمیر: {str(e)}",
            },
        )

    return RedirectResponse(url="/repairs", status_code=http_status.HTTP_302_FOUND)


@router.get("/inventory", response_class=HTMLResponse)
async def inventory_page(
    request: Request,
    db: Session = Depends(get_db),
    search: Optional[str] = None,
    low_stock: Optional[bool] = None,
    arsenal_name: Optional[str] = None,
):
    """Display inventory page"""
    user = await get_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=http_status.HTTP_302_FOUND)

    try:
        # Build query
        query = db.query(models.ArsenalTable)

        if arsenal_name:
            query = query.filter(models.ArsenalTable.arsenal_name == arsenal_name)

        if search:
            query = query.filter(
                (models.ArsenalTable.fragment_name.contains(search))
                | (models.ArsenalTable.fragment_part_no.contains(search))
            )

        if low_stock:
            query = query.filter(models.ArsenalTable.fragment_qty < 5)

        inventory_items = (
            query.order_by(models.ArsenalTable.fragment_name).all()
        )
    except Exception:
        inventory_items = []

    return templates.TemplateResponse(
        "inventory.html",
        {
            "request": request,
            "user": user,
            "inventory_items": inventory_items,
            "search": search,
            "low_stock": low_stock,
            "arsenal_name": arsenal_name,
        },
    )


@router.post("/inventory/create")
async def create_inventory_item(
    request: Request,
    db: Session = Depends(get_db),
    fragment_part_no: str = Form(...),
    fragment_name: str = Form(...),
    arsenal_name: str = Form(...),
    fragment_qty: int = Form(0),
):
    """Create new inventory item"""
    user = await get_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=http_status.HTTP_302_FOUND)

    try:
        # Check if item exists
        existing = db.query(models.ArsenalTable).filter(
            models.ArsenalTable.fragment_part_no == fragment_part_no,
            models.ArsenalTable.arsenal_name == arsenal_name,
        ).first()

        if existing:
            # Update quantity
            existing.fragment_qty += fragment_qty
        else:
            # Create new item
            item = models.ArsenalTable(
                fragment_part_no=fragment_part_no,
                fragment_name=fragment_name,
                arsenal_name=arsenal_name,
                fragment_qty=fragment_qty,
            )
            db.add(item)

        db.commit()
    except Exception as e:
        db.rollback()
        # Return with error
        return templates.TemplateResponse(
            "inventory.html",
            {
                "request": request,
                "user": user,
                "inventory_items": [],
                "error": f"خطا در ثبت موجودی: {str(e)}",
            },
        )

    return RedirectResponse(url="/inventory", status_code=http_status.HTTP_302_FOUND)


@router.post("/inventory/{part_no}/{arsenal_name}/update-quantity")
async def update_inventory_quantity(
    part_no: str,
    arsenal_name: str,
    request: Request,
    db: Session = Depends(get_db),
    operation: str = Form(...),
    amount: int = Form(...),
    note: Optional[str] = Form(None),
):
    """Update inventory item quantity"""
    user = await get_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=http_status.HTTP_302_FOUND)

    try:
        item = db.query(models.ArsenalTable).filter(
            models.ArsenalTable.fragment_part_no == part_no,
            models.ArsenalTable.arsenal_name == arsenal_name,
        ).first()

        if item:
            if operation == "add":
                item.fragment_qty += amount
            elif operation == "subtract":
                item.fragment_qty = max(0, item.fragment_qty - amount)

            db.commit()
    except Exception:
        db.rollback()

    return RedirectResponse(url="/inventory", status_code=http_status.HTTP_302_FOUND)
