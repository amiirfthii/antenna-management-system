#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.db.database import get_db
from app.db import models
from app.schemas.user import User, UserCreate, UserUpdate
from app.api.deps import get_current_admin_user, get_current_owner_user

router = APIRouter()


@router.get("/", response_model=List[User])
async def get_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Get all users (admin/owner only) - returns both active and inactive users"""
    users = db.query(models.User).offset(skip).limit(limit).all()
    return users


@router.get("/{personal_id}", response_model=User)
async def get_user(
    personal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Get user by ID"""
    user = db.query(models.User).filter(
        models.User.personal_id == personal_id
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return user


@router.post("/", response_model=User, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Create new user (admin/owner only)"""
    # Check if username already exists
    existing_user = db.query(models.User).filter(
        models.User.username == user_in.username
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )

    # Check if personal_id already exists
    existing_id = db.query(models.User).filter(
        models.User.personal_id == user_in.personal_id
    ).first()

    if existing_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Personal ID already registered"
        )

    # Create new user
    db_user = models.User(
        personal_id=user_in.personal_id,
        user_first_name=user_in.user_first_name,
        user_last_name=user_in.user_last_name,
        user_type=user_in.user_type,
        username=user_in.username,
        password_hash=get_password_hash(user_in.password)
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user


@router.put("/{personal_id}", response_model=User)
async def update_user(
    personal_id: int,
    user_in: UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Update user (admin/owner only)"""
    user = db.query(models.User).filter(
        models.User.personal_id == personal_id
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Update fields
    update_data = user_in.model_dump(exclude_unset=True)

    if "password" in update_data:
        update_data["password_hash"] = get_password_hash(update_data.pop("password"))

    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)

    return user


@router.delete("/{personal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    personal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Delete user (admin/owner only) - prevents deleting owner and self"""
    user = db.query(models.User).filter(
        models.User.personal_id == personal_id
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Prevent deleting owner
    if user.user_type == "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete owner user"
        )

    # Prevent deleting self
    if user.personal_id == current_user.personal_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete yourself"
        )

    # Soft delete
    user.is_active = False
    db.commit()

    return None


@router.get("/debug/count")
async def get_users_count_debug(
    db: Session = Depends(get_db),
):
    """Debug endpoint to check user count without authentication"""
    total = db.query(models.User).count()
    active = db.query(models.User).filter(models.User.is_active == True).count()
    inactive = db.query(models.User).filter(models.User.is_active == False).count()
    owner_count = db.query(models.User).filter(models.User.user_type == "owner").count()
    admin_count = db.query(models.User).filter(models.User.user_type == "admin").count()
    
    users = db.query(models.User).all()
    user_list = [
        {
            "personal_id": u.personal_id,
            "username": u.username,
            "user_first_name": u.user_first_name,
            "user_last_name": u.user_last_name,
            "user_type": u.user_type,
            "is_active": u.is_active,
        }
        for u in users
    ]
    
    return {
        "total": total,
        "active": active,
        "inactive": inactive,
        "owner_count": owner_count,
        "admin_count": admin_count,
        "users": user_list
    }
