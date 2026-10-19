#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    CheckConstraint,
    Index,
)
from sqlalchemy.orm import relationship, synonym
from app.db.database import Base

NAME_LEN = 191  # Safe length for utf8mb4 indexes in MySQL
SHORT_TEXT_LEN = 50
PART_NO_LEN = 100
USERNAME_LEN = 150
PASSWORD_LEN = 255
CODE_LEN = 100

class User(Base):
    __tablename__ = "users"

    personal_id = Column(Integer, primary_key=True, index=True)
    user_first_name = Column(String(100), nullable=False)
    user_last_name = Column(String(100), nullable=False)
    user_type = Column(String(SHORT_TEXT_LEN), nullable=False)
    username = Column(String(USERNAME_LEN), unique=True, nullable=False, index=True)
    password_hash = Column(String(PASSWORD_LEN), nullable=False)
    is_active = Column(Boolean, default=True)

    # Relationships
    repairs_as_admin = relationship("Repair", back_populates="admin", foreign_keys="Repair.admin_id")
    repair_steps = relationship("RepairStep", back_populates="user")
    repair_items_reports = relationship("RepairItemReport", back_populates="user")
    miscellaneous_tasks = relationship("MiscellaneousTask", back_populates="user")
    door_productions = relationship("DoorProduction", back_populates="user")
    osanloui_daily_tasks = relationship("OsanlouiDailyTask", back_populates="user")

    __table_args__ = (
        CheckConstraint("user_type IN ('owner', 'admin', 'regularUser')", name='check_user_type'),
    )


class AntennaConstructor(Base):
    __tablename__ = "antennaConstructor"

    company_constructor = Column(String(NAME_LEN), primary_key=True)

    # Relationships
    repairs = relationship("Repair", back_populates="constructor_rel")


class AntennaType(Base):
    __tablename__ = "antennaTypes"

    antenna_type = Column(String(NAME_LEN), primary_key=True)

    # Relationships
    repairs = relationship("Repair", back_populates="antenna_type_rel")


class RepairItem(Base):
    __tablename__ = "repairItems"

    repair_item_name = Column(String(NAME_LEN), primary_key=True)

    # Relationships
    repair_steps = relationship("RepairStep", back_populates="repair_item")


class Repair(Base):
    __tablename__ = "repairs"

    repair_no = Column(Integer, primary_key=True, autoincrement=True)
    antenna_serial_no = Column(String(NAME_LEN), nullable=False, index=True)
    antenna_type = Column(String(NAME_LEN), ForeignKey("antennaTypes.antenna_type"))
    antenna_entry_type = Column(String(SHORT_TEXT_LEN), nullable=False)
    constructor = Column(String(NAME_LEN), ForeignKey("antennaConstructor.company_constructor"))
    entry_date = Column(String(SHORT_TEXT_LEN))
    exit_date = Column(String(SHORT_TEXT_LEN))
    tilt = Column(String(SHORT_TEXT_LEN))
    item_code = Column(String(CODE_LEN))
    admin_id = Column(Integer, ForeignKey("users.personal_id"))
    antenna_status = Column(String(SHORT_TEXT_LEN), default='نامعلوم')
    antenna_admin_check_date = Column(String(SHORT_TEXT_LEN))
    # منشأ آنتن سریال‌دار: "استان" یا "مستهلک" (برای آمار موجودی در مرکز)
    no_serial_category = Column(String(NAME_LEN), nullable=True)

    # Relationships
    admin = relationship("User", back_populates="repairs_as_admin", foreign_keys=[admin_id])
    constructor_rel = relationship("AntennaConstructor", back_populates="repairs")
    antenna_type_rel = relationship("AntennaType", back_populates="repairs")
    repair_steps = relationship("RepairStep", back_populates="repair", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("antenna_entry_type IN ('ورودی_خروجی', 'ورودی_تعمیر')", name='check_entry_type'),
        CheckConstraint("antenna_status IN ('تایید', 'فالتی_سالویج', 'فالتی_در_انتظار_تعمیر', 'نامعلوم', 'خروج', 'در_انتظار_تایید')", name='check_status'),
        Index('idx_repairs_serial', antenna_serial_no),
        Index('idx_repairs_admin', admin_id),
        Index('idx_repairs_status', antenna_status),
        # یکتایی سریال در سطح دیتابیس با ایندکس UNIQUE سراسری تضمین می‌شود
        # (case-insensitive، سریال خالی مستثنا) — نگاه کنید به:
        # app/db/migrations/serial_unique_index.py
    )


class RepairStep(Base):
    __tablename__ = "repairSteps"

    repair_no = Column(Integer, ForeignKey("repairs.repair_no", ondelete="CASCADE"), primary_key=True)
    repair_item_name = Column(String(NAME_LEN), ForeignKey("repairItems.repair_item_name"), primary_key=True)
    item_status = Column(String(SHORT_TEXT_LEN), default='انجام نشده')
    personal_id = Column(Integer, ForeignKey("users.personal_id"))
    start_date = Column(String(SHORT_TEXT_LEN))
    end_date = Column(String(SHORT_TEXT_LEN))
    item_code = Column(String(CODE_LEN))

    # Relationships
    repair = relationship("Repair", back_populates="repair_steps")
    repair_item = relationship("RepairItem", back_populates="repair_steps")
    user = relationship("User", back_populates="repair_steps")
    supply_usages = relationship("UserSupplyUsage", back_populates="repair_step", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("item_status IN ('در حال انجام', 'انجام نشده', 'انجام شده', 'فالتی')", name='check_item_status'),
        Index('idx_repair_steps_status', item_status),
    )


class ArsenalTable(Base):
    __tablename__ = "arsenalTable"

    fragment_part_no = Column(String(PART_NO_LEN), primary_key=True)
    arsenal_name = Column(String(SHORT_TEXT_LEN), primary_key=True)
    fragment_name = Column(String(NAME_LEN), nullable=False)
    fragment_qty = Column(Integer, nullable=False)

    # Relationships
    supply_entries = relationship("SupplyFragmentEntry", back_populates="arsenal", cascade="all, delete-orphan")
    supply_usages = relationship("UserSupplyUsage", back_populates="arsenal", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("arsenal_name IN ('نو', 'سالویج', 'تجهیزات')", name='check_arsenal_name'),
        Index('idx_arsenal_name', fragment_name),
        Index('idx_arsenal_type', arsenal_name),
    )


class UserSupplyUsage(Base):
    __tablename__ = "userSupplyUsage"

    repair_no = Column(Integer, primary_key=True)
    repair_item_name = Column(String(NAME_LEN), primary_key=True)
    fragment_part_no = Column(String(PART_NO_LEN), primary_key=True)
    arsenal_name = Column(String(SHORT_TEXT_LEN), primary_key=True)
    repair_fragment_qty = Column(Integer)

    # Relationships
    repair_step = relationship("RepairStep", back_populates="supply_usages")
    arsenal = relationship("ArsenalTable", back_populates="supply_usages")

    __table_args__ = (
        ForeignKeyConstraint(
            ['repair_no', 'repair_item_name'],
            ['repairSteps.repair_no', 'repairSteps.repair_item_name'],
            ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ['fragment_part_no', 'arsenal_name'],
            ['arsenalTable.fragment_part_no', 'arsenalTable.arsenal_name'],
            ondelete="CASCADE"
        ),
        CheckConstraint("arsenal_name IN ('نو', 'سالویج')", name='check_arsenal_name_usage'),
        Index('idx_supply_usage_repair', repair_no, repair_item_name),
        Index('idx_supply_usage_fragment', fragment_part_no, arsenal_name),
    )


class SupplyFragmentEntry(Base):
    __tablename__ = "supplyFragmentEntry"

    fragment_entry_no = Column(Integer, primary_key=True, autoincrement=True)
    fragment_entry_name = Column(String(NAME_LEN))
    fragment_entry_qty = Column(Integer)
    fragment_entry_date = Column(String(SHORT_TEXT_LEN))
    fragment_part_no = Column(String(PART_NO_LEN))
    arsenal_name = Column(String(SHORT_TEXT_LEN))

    # Relationships
    arsenal = relationship("ArsenalTable", back_populates="supply_entries")

    __table_args__ = (
        ForeignKeyConstraint(
            ['fragment_part_no', 'arsenal_name'],
            ['arsenalTable.fragment_part_no', 'arsenalTable.arsenal_name']
        ),
        Index('idx_fragment_entry_part', fragment_part_no, arsenal_name),
    )


class RepairItemReport(Base):
    __tablename__ = "repairItemsReport"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repair_no = Column(Integer, index=True)
    antenna_serial_no = Column(String(NAME_LEN))
    manufacturer = Column(String(NAME_LEN))
    personal_id = Column(Integer, ForeignKey("users.personal_id"))
    first_name = Column(String(100))
    last_name = Column(String(100))
    item_name = Column(String(NAME_LEN))
    fragment_name = Column(String(NAME_LEN))
    fragment_part_no = Column(String(PART_NO_LEN))
    arsenal_name = Column(String(SHORT_TEXT_LEN))
    used_quantity = Column(Integer)
    status = Column(String(SHORT_TEXT_LEN))
    final_status = Column(String(SHORT_TEXT_LEN), default='در انتظار')
    repair_date = Column(String(SHORT_TEXT_LEN))
    item_description = Column(String(500))

    # Relationships
    user = relationship("User", back_populates="repair_items_reports")

    __table_args__ = (
        Index('idx_repair_items_report_repair_no', repair_no),
        Index('idx_repair_items_report_personal_id', personal_id),
    )


class ItemCodeAssignment(Base):
    __tablename__ = "itemCodeAssignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manufacturer = Column(String(NAME_LEN), nullable=False, index=True)
    antenna_type = Column(String(NAME_LEN), nullable=False, index=True)
    tilt_type = Column(String(SHORT_TEXT_LEN), nullable=False)
    item_code = Column(String(CODE_LEN), nullable=False, index=True)
    created_date = Column(String(SHORT_TEXT_LEN), nullable=False)
    created_time = Column(String(SHORT_TEXT_LEN), nullable=False)

    __table_args__ = (
        Index('idx_item_code_manufacturer', manufacturer),
        Index('idx_item_code_antenna_type', antenna_type),
        Index('idx_item_code_item_code', item_code),
    )


class DeliveredAntenna(Base):
    __tablename__ = "deliveredAntennas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repair_no = Column(String(SHORT_TEXT_LEN), nullable=False, index=True)
    antenna_serial_no = Column(String(NAME_LEN), nullable=False, index=True)
    antenna_type = Column(String(NAME_LEN), nullable=False)
    manufacturer = Column(String(NAME_LEN), nullable=False)
    item_code = Column(String(CODE_LEN), nullable=False)
    entry_date = Column(String(SHORT_TEXT_LEN), nullable=False)
    antenna_status = Column(String(SHORT_TEXT_LEN), nullable=False)
    delivery_time = Column(String(SHORT_TEXT_LEN), nullable=False)

    __table_args__ = (
        Index('idx_delivered_serial', antenna_serial_no),
        Index('idx_delivered_repair_no', repair_no),
    )


class NoSerialAntenna(Base):
    """آنتن‌های بدون سریال (ورودی استان / مستهلک)."""
    __tablename__ = "noSerialAntennas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor = Column(String(NAME_LEN), nullable=False)
    antenna_type = Column(String(NAME_LEN), nullable=False)
    item_code = Column(String(CODE_LEN), nullable=False)
    category = Column(String(NAME_LEN), nullable=False, default="استان")
    province = Column(String(NAME_LEN), nullable=False, default="")
    quantity = Column(Integer, nullable=False)  # تعداد ورود در آن تاریخ
    remaining_quantity = Column(Integer, nullable=True)  # موجودی باقی‌مانده
    created_date = Column(String(SHORT_TEXT_LEN))  # تاریخ ورود شمسی YYYY/MM/DD
    entry_date = synonym("created_date")


# backward-compatible alias
ProvinceAntenna = NoSerialAntenna


class AntennaTarget(Base):
    """تارگت خواسته‌شدهٔ کارفرما به‌ازای هر کلاس آنتن (2X، 3X، …)."""
    __tablename__ = "antennaTargets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bucket_code = Column(String(NAME_LEN), unique=True, nullable=False)
    target_qty = Column(Integer, nullable=False, default=0)
    updated_date = Column(String(SHORT_TEXT_LEN))


class PmoScope(Base):
    """اسکوپ دستیِ تاییدشدهٔ کارفرما (کل تعمیری/SCOPE) به‌ازای هر ردیف PMO.

    این عدد در دیتابیس نداریم و باید دستی در صفحهٔ PMO وارد شود؛
    ردیف‌ها مطابق نوع‌های PMO هستند: x-pole، 2x-pole، …، TDD، 8x-irani.
    """
    __tablename__ = "pmoScope"

    id = Column(Integer, primary_key=True, autoincrement=True)
    row_type = Column(String(NAME_LEN), unique=True, nullable=False)
    scope_qty = Column(Integer, nullable=False, default=0)
    updated_date = Column(String(SHORT_TEXT_LEN))


class PmoSnapshot(Base):
    """اعداد مستقل صفحه PMO / داشبورد — از جدول repairs خوانده نمی‌شود."""
    __tablename__ = "pmoSnapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    row_type = Column(String(NAME_LEN), unique=True, nullable=False, index=True)
    dep = Column(Integer, nullable=False, default=0)
    p1 = Column(Integer, nullable=False, default=0)
    p2 = Column(Integer, nullable=False, default=0)
    tot = Column(Integer, nullable=False, default=0)
    sap = Column(Integer, nullable=False, default=0)
    wait = Column(Integer, nullable=False, default=0)
    updated_date = Column(String(SHORT_TEXT_LEN))


class PmoAntennaMapping(Base):
    """نگاشت دستی نوع آنتن → ستون PMO در نمودار (x-pole، 2x-pole، …).

    pmo_row_type خالی = استفاده از تشخیص خودکار سیستم.
    pmo_row_type برابر __skip__ = نادیده گرفتن در نمودار.
    """
    __tablename__ = "pmoAntennaMapping"

    id = Column(Integer, primary_key=True, autoincrement=True)
    antenna_type = Column(String(NAME_LEN), unique=True, nullable=False, index=True)
    pmo_row_type = Column(String(NAME_LEN), nullable=False, default="")
    updated_date = Column(String(SHORT_TEXT_LEN))


class PmoItemMapping(Base):
    """نگاشت دستی (وندور + نوع آنتن + آیتم‌کد) → بسته PMO.

    اولویت بالاتر از نگاشت نوع آنتن؛ برای قرار دادن آیتم‌کدها در بسته درست نمودار.
    """
    __tablename__ = "pmoItemMapping"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor = Column(String(NAME_LEN), nullable=False, default="")
    antenna_type = Column(String(NAME_LEN), nullable=False, default="")
    item_code = Column(String(CODE_LEN), nullable=False, index=True)
    pmo_row_type = Column(String(NAME_LEN), nullable=False, default="")
    updated_date = Column(String(SHORT_TEXT_LEN))

    __table_args__ = (
        Index(
            "idx_pmo_item_mapping_triple",
            vendor,
            antenna_type,
            item_code,
            unique=True,
        ),
    )


class MiscellaneousTask(Base):
    __tablename__ = "miscellaneousTasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(NAME_LEN), nullable=False, index=True)
    description = Column(String(2000), nullable=False, default="")
    personal_id = Column(Integer, ForeignKey("users.personal_id"), nullable=False, index=True)
    user_first_name = Column(String(100))
    user_last_name = Column(String(100))
    created_date = Column(String(SHORT_TEXT_LEN), nullable=False, index=True)

    user = relationship("User", back_populates="miscellaneous_tasks")

    __table_args__ = (
        Index("idx_misc_tasks_date", created_date),
        Index("idx_misc_tasks_personal", personal_id),
    )


class OsanlouiDailyTask(Base):
    """Daily production counts entered by Mohammad Osanloui (Today's Task)."""
    __tablename__ = "osanlouiDailyTasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_date = Column(String(SHORT_TEXT_LEN), nullable=False, index=True)
    item_name = Column(String(NAME_LEN), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    personal_id = Column(Integer, ForeignKey("users.personal_id"), nullable=False, index=True)
    user_first_name = Column(String(100))
    user_last_name = Column(String(100))
    created_date = Column(String(SHORT_TEXT_LEN), nullable=False, index=True)

    user = relationship("User", back_populates="osanloui_daily_tasks")

    __table_args__ = (
        Index("idx_osanloui_task_date", task_date),
        Index("idx_osanloui_item", item_name),
        Index("idx_osanloui_personal", personal_id),
    )


class DoorProduction(Base):
    __tablename__ = "doorProductions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor = Column(String(NAME_LEN), nullable=False, index=True)
    antenna_type = Column(String(NAME_LEN), nullable=False, index=True)
    item_code = Column(String(CODE_LEN))
    quantity = Column(Integer, nullable=False)
    description = Column(String(2000), nullable=False, default="")
    personal_id = Column(Integer, ForeignKey("users.personal_id"), nullable=False, index=True)
    user_first_name = Column(String(100))
    user_last_name = Column(String(100))
    created_date = Column(String(SHORT_TEXT_LEN), nullable=False, index=True)

    user = relationship("User", back_populates="door_productions")
    parts = relationship(
        "DoorProductionPart",
        back_populates="door_production",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_door_prod_date", created_date),
        Index("idx_door_prod_personal", personal_id),
    )


class DoorProductionPart(Base):
    __tablename__ = "doorProductionParts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    door_production_id = Column(
        Integer,
        ForeignKey("doorProductions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fragment_part_no = Column(String(PART_NO_LEN), nullable=False)
    fragment_name = Column(String(NAME_LEN))
    arsenal_name = Column(String(SHORT_TEXT_LEN), nullable=False)
    quantity = Column(Integer, nullable=False)

    door_production = relationship("DoorProduction", back_populates="parts")

class InventoryHistory(Base):
    __tablename__ = "inventory_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    part_no = Column(String(PART_NO_LEN), nullable=False, index=True)
    operation_type = Column(String(SHORT_TEXT_LEN), nullable=False)
    quantity = Column(Integer, nullable=False)
    personal_id = Column(String(SHORT_TEXT_LEN), nullable=False)
    operation_date = Column(String(SHORT_TEXT_LEN), nullable=False)

    __table_args__ = (
        Index('idx_inventory_history_part', part_no),
        Index('idx_inventory_history_date', operation_date),
    )
