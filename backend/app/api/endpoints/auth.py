#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.db.database import get_db
from app.db import models
from app.schemas.user import Token, User
from app.api.deps import get_current_user, get_current_admin_user

router = APIRouter()


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Login endpoint - returns JWT token"""
    # Find user by username
    user = db.query(models.User).filter(
        models.User.username == form_data.username
    ).first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": user.username,
            "personal_id": user.personal_id,
            "user_type": user.user_type
        },
        expires_delta=access_token_expires
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.get("/me", response_model=User)
async def read_users_me(current_user: models.User = Depends(get_current_user)):
    """Get current user info"""
    return current_user


@router.post("/logout")
async def logout():
    """Logout endpoint (client should delete token)"""
    return {"message": "Successfully logged out"}


@router.post("/impersonate/{personal_id}", response_model=Token)
async def impersonate_user(
    personal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user),
):
    """Switch session to a regular user (admin/owner only)."""
    target = db.query(models.User).filter(
        models.User.personal_id == personal_id,
        models.User.is_active.is_(True),
    ).first()

    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if target.user_type in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot impersonate admin or owner accounts",
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": target.username,
            "personal_id": target.personal_id,
            "user_type": target.user_type,
            "impersonator_id": current_user.personal_id,
        },
        expires_delta=access_token_expires,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.post("/reset-users")
async def reset_users(db: Session = Depends(get_db)):
    """
    Reset all users and create default owner user.
    WARNING: This will delete all users!
    Username: owner
    Password: 123456
    """
    from app.core.security import get_password_hash
    from app.db import models
    
    try:
        # Delete all users
        deleted_count = db.query(models.User).delete()
        db.commit()
        
        # Create owner user
        owner_user = models.User(
            personal_id=100001,
            user_first_name="مالک",
            user_last_name="سیستم",
            user_type="owner",
            username="owner",
            password_hash=get_password_hash("123456"),
            is_active=True,
        )
        
        db.add(owner_user)
        db.commit()
        db.refresh(owner_user)
        
        return {
            "message": "Users reset successfully",
            "deleted_count": deleted_count,
            "owner_created": True,
            "username": "owner",
            "password": "123456"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error resetting users: {str(e)}"
        )
