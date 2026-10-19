#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from fastapi import FastAPI, WebSocket, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
import os

from app.core.config import settings
from app.db.database import engine, Base
from app.api.endpoints import auth, users, repairs, inventory, frontend, repair_items, item_code_assignments, antenna_types, constructors, repair_item_reports, report_export, profile_photos, dashboard, province_antennas, miscellaneous_tasks, door_productions, antenna_targets, osanloui_tasks
from app.api.websocket import websocket_endpoint
from app.core.profile_photos import PROFILE_PHOTOS_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    print("Starting up...")
    # Create database tables (with error handling)
    try:
        Base.metadata.create_all(bind=engine)
        print("Database tables ready")
        
        # Migration: Add missing columns to existing SQLite database
        try:
            from sqlalchemy import inspect, text
            
            inspector = inspect(engine)
            if 'repairs' in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns('repairs')]
                
                # Add tilt column if it doesn't exist (for SQLite)
                if 'tilt' not in columns and engine.url.drivername == 'sqlite':
                    print("Migrating: Adding 'tilt' column to repairs table...")
                    with engine.begin() as conn:  # begin() automatically commits
                        # SQLite uses TEXT instead of VARCHAR
                        conn.execute(text("ALTER TABLE repairs ADD COLUMN tilt TEXT"))
                    print("Migration completed: 'tilt' column added")
        except Exception as migration_error:
            print(f"Migration warning: {migration_error}")
            # Continue anyway - migration is optional

        try:
            from app.db.migrations.jalali_date_separators import migrate_jalali_date_separators
            migrate_jalali_date_separators(engine)
        except Exception as migration_error:
            print(f"Date format migration warning: {migration_error}")

        try:
            from app.db.migrations.arsenal_equipment import migrate_arsenal_equipment_type
            migrate_arsenal_equipment_type(engine)
        except Exception as migration_error:
            print(f"Arsenal migration warning: {migration_error}")

        try:
            from app.db.migrations.repair_report_description import migrate_repair_report_description
            migrate_repair_report_description(engine)
        except Exception as migration_error:
            print(f"Repair report description migration warning: {migration_error}")
            
        try:
            from app.db.migrations.no_serial_antenna import migrate_no_serial_antenna
            migrate_no_serial_antenna(engine)
        except Exception as migration_error:
            print(f"No-serial antenna migration warning: {migration_error}")

        try:
            from app.db.migrations.repair_source_category import migrate_repair_source_category
            migrate_repair_source_category(engine)
        except Exception as migration_error:
            print(f"Repair source category migration warning: {migration_error}")

        try:
            from app.db.migrations.repair_category_from_1405 import migrate_repair_category_from_1405
            migrate_repair_category_from_1405(engine)
        except Exception as migration_error:
            print(f"Repair 1405 category backfill warning: {migration_error}")

        try:
            from app.db.migrations.pmo_item_mapping import migrate_pmo_item_mapping
            migrate_pmo_item_mapping(engine)
        except Exception as migration_error:
            print(f"PMO item mapping migration warning: {migration_error}")

        try:
            from app.db.migrations.serial_unique_index import migrate_serial_unique_index
            migrate_serial_unique_index(engine)
        except Exception as migration_error:
            print(f"Serial uniqueness migration warning: {migration_error}")

    except Exception as e:
        print(f"WARNING: Could not connect to database: {e}")
        print("Application will continue but database features may not work")

    yield

    # Shutdown
    print("Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# ------------------ Static files ------------------
# اینجا به صورت صریح ریشه‌ی پروژه (backend) را حساب می‌کنیم
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(PROJECT_ROOT, "static")
FRONTEND_DIST_DIR = os.path.join(PROJECT_ROOT, "frontend_dist")

# Serve backend static files (if exists)
if os.path.isdir(STATIC_DIR):
    print(">>> Serving backend static files from:", STATIC_DIR)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    print(">>> WARNING: static directory not found:", STATIC_DIR)

# Serve frontend static assets (JS, CSS, images, etc.)
# این باید قبل از catch-all route بیاید تا فایل‌های استاتیک به درستی سرو شوند
if os.path.isdir(FRONTEND_DIST_DIR):
    print(">>> Serving frontend static files from:", FRONTEND_DIST_DIR)
    # Mount assets folder for JS, CSS, etc. (Vite build output)
    assets_dir = os.path.join(FRONTEND_DIST_DIR, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend_assets")
    data_dir = os.path.join(FRONTEND_DIST_DIR, "data")
    if os.path.isdir(data_dir):
        app.mount("/data", StaticFiles(directory=data_dir), name="frontend_data")
    # Mount other static files like favicon, etc.
    # Note: We mount at a specific path to avoid conflicts with API routes
else:
    print(">>> WARNING: frontend_dist directory not found:", FRONTEND_DIST_DIR)
    print(">>> Run 'cd frontend && npm run build' to build the frontend")

print(">>> Profile photos directory:", PROFILE_PHOTOS_DIR)

# ------------------ CORS ------------------
# برای استفاده از همان origin، CORS را برای همه origins مجاز می‌کنیم
# چون frontend و backend روی همان domain هستند
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # یا می‌توانید لیست مشخصی از origins را بگذارید
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------ Routers ------------------
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(repairs.router, prefix="/api/repairs", tags=["Repairs"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["Inventory"])
app.include_router(repair_items.router, prefix="/api/repair-items", tags=["Repair Items"])
app.include_router(item_code_assignments.router, prefix="/api/item-code-assignments", tags=["Item Code Assignments"])
app.include_router(antenna_types.router, prefix="/api/antenna-types", tags=["Antenna Types"])
app.include_router(constructors.router, prefix="/api/constructors", tags=["Constructors"])
app.include_router(repair_item_reports.router, prefix="/api/repair-item-reports", tags=["Repair Item Reports"])
app.include_router(report_export.router, prefix="/api/reports", tags=["Report Export"])
app.include_router(profile_photos.router, prefix="/api", tags=["Profile Photos"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(province_antennas.router, prefix="/api/province-antennas", tags=["Province Antennas"])
app.include_router(antenna_targets.router, prefix="/api/antenna-targets", tags=["Antenna Targets"])
app.include_router(miscellaneous_tasks.router, prefix="/api/misc-tasks", tags=["Miscellaneous Tasks"])
app.include_router(door_productions.router, prefix="/api/door-productions", tags=["Door Productions"])
app.include_router(osanloui_tasks.router, prefix="/api/osanloui-tasks", tags=["Osanloui Daily Tasks"])

# NOTE: Old template-based frontend router is commented out
# We're now using React SPA which is served from frontend_dist
# app.include_router(frontend.router, tags=["Frontend"])


# WebSocket endpoint
@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    await websocket_endpoint(websocket)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# Root endpoint - serve frontend index.html
@app.get("/")
async def root():
    """Serve frontend index.html for root route"""
    frontend_index = os.path.join(FRONTEND_DIST_DIR, "index.html")
    if os.path.isfile(frontend_index):
        return FileResponse(frontend_index)
    # اگر frontend build نشده، به old frontend redirect کن یا پیام خطا بده
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/login")


# Exception handler برای 404 - اگر route پیدا نشد، frontend را سرو کن (SPA routing)
@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    """
    برای مسیرهای غیر API که پیدا نشدند، frontend index.html را برگردان (SPA routing)
    """
    path = request.url.path
    
    # اگر مسیر API، static، assets، ws، یا health است، 404 واقعی برگردان
    if (path.startswith("/api/") or 
        path.startswith("/static/") or 
        path.startswith("/assets/") or
        path == "/ws" or
        path == "/health"):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    if path and path != "/":
        dist_file = os.path.normpath(os.path.join(FRONTEND_DIST_DIR, path.lstrip("/")))
        if dist_file.startswith(os.path.normpath(FRONTEND_DIST_DIR)) and os.path.isfile(dist_file):
            return FileResponse(dist_file)
    
    # برای بقیه مسیرها، frontend index.html را برگردان (SPA routing)
    frontend_index = os.path.join(FRONTEND_DIST_DIR, "index.html")
    if os.path.isfile(frontend_index):
        return FileResponse(frontend_index)
    
    # اگر frontend build نشده، پیام خطا برگردان
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Frontend not built. Please run 'cd frontend && npm run build'"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
