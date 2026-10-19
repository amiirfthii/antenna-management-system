-- ============================================================
--  سامانه مدیریت آنتن - طرح پایگاه‌داده برای نسخه وب (MySQL)
--  منطبق با ساختار موجود در اپ دسکتاپ (SQLite)
--  فایل: backend/app/db/schema.sql
-- ============================================================

SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

-- ------------------------------------------------------------
-- جدول کاربران
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    personal_id      INT            NOT NULL PRIMARY KEY,
    user_first_name  VARCHAR(100)   NOT NULL,
    user_last_name   VARCHAR(100)   NOT NULL,
    user_type        VARCHAR(50)    NOT NULL,
    username         VARCHAR(150)   NOT NULL UNIQUE,
    password_hash    VARCHAR(255)   NOT NULL,
    is_active        BOOLEAN        NOT NULL DEFAULT TRUE,
    CONSTRAINT check_user_type
        CHECK (user_type IN ('owner', 'admin', 'regularUser'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_users_username ON users(username);

-- ------------------------------------------------------------
-- جداول مرجع
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS antennaConstructor (
    company_constructor VARCHAR(191) NOT NULL PRIMARY KEY
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS antennaTypes (
    antenna_type VARCHAR(191) NOT NULL PRIMARY KEY
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS repairItems (
    repair_item_name VARCHAR(191) NOT NULL PRIMARY KEY
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- جدول تعمیرات
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS repairs (
    repair_no                 INT AUTO_INCREMENT PRIMARY KEY,
    antenna_serial_no         VARCHAR(191) NOT NULL,
    antenna_type              VARCHAR(191),
    antenna_entry_type        VARCHAR(50)  NOT NULL,
    constructor               VARCHAR(191),
    entry_date                VARCHAR(50),
    exit_date                 VARCHAR(50),
    tilt                      VARCHAR(50),
    item_code                 VARCHAR(100),
    admin_id                  INT,
    antenna_status            VARCHAR(50)  NOT NULL DEFAULT 'نامعلوم',
    antenna_admin_check_date  VARCHAR(50),
    CONSTRAINT fk_repairs_type        FOREIGN KEY (antenna_type) REFERENCES antennaTypes(antenna_type),
    CONSTRAINT fk_repairs_constructor FOREIGN KEY (constructor) REFERENCES antennaConstructor(company_constructor),
    CONSTRAINT fk_repairs_admin       FOREIGN KEY (admin_id) REFERENCES users(personal_id),
    CONSTRAINT check_entry_type
        CHECK (antenna_entry_type IN ('ورودی_خروجی', 'ورودی_تعمیر')),
    CONSTRAINT check_status
        CHECK (antenna_status IN ('تایید', 'فالتی_سالویج', 'فالتی_در_انتظار_تعمیر', 'نامعلوم', 'خروج', 'در_انتظار_تایید'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_repairs_serial ON repairs(antenna_serial_no);
CREATE INDEX idx_repairs_admin ON repairs(admin_id);
CREATE INDEX idx_repairs_status ON repairs(antenna_status);

-- ------------------------------------------------------------
-- مراحل تعمیر
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS repairSteps (
    repair_no        INT         NOT NULL,
    repair_item_name VARCHAR(191) NOT NULL,
    item_status      VARCHAR(50)  NOT NULL DEFAULT 'انجام نشده',
    personal_id      INT,
    start_date       VARCHAR(50),
    end_date         VARCHAR(50),
    item_code        VARCHAR(100),
    PRIMARY KEY (repair_no, repair_item_name),
    CONSTRAINT fk_steps_repair       FOREIGN KEY (repair_no)        REFERENCES repairs(repair_no) ON DELETE CASCADE,
    CONSTRAINT fk_steps_item         FOREIGN KEY (repair_item_name) REFERENCES repairItems(repair_item_name),
    CONSTRAINT fk_steps_user         FOREIGN KEY (personal_id)      REFERENCES users(personal_id),
    CONSTRAINT check_item_status
        CHECK (item_status IN ('در حال انجام', 'انجام نشده', 'انجام شده', 'فالتی'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_repair_steps_status ON repairSteps(item_status);

-- ------------------------------------------------------------
-- انبار قطعات
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS arsenalTable (
    fragment_part_no VARCHAR(100) NOT NULL,
    arsenal_name     VARCHAR(50)  NOT NULL,
    fragment_name    VARCHAR(191) NOT NULL,
    fragment_qty     INT          NOT NULL,
    PRIMARY KEY (fragment_part_no, arsenal_name),
    CONSTRAINT check_arsenal_name
        CHECK (arsenal_name IN ('نو', 'سالویج', 'تجهیزات'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_arsenal_name ON arsenalTable(fragment_name);
CREATE INDEX idx_arsenal_type ON arsenalTable(arsenal_name);

-- ------------------------------------------------------------
-- مصرف قطعات توسط کاربران در مراحل تعمیر
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS userSupplyUsage (
    repair_no          INT          NOT NULL,
    repair_item_name   VARCHAR(191) NOT NULL,
    fragment_part_no   VARCHAR(100) NOT NULL,
    arsenal_name       VARCHAR(50)  NOT NULL,
    repair_fragment_qty INT,
    PRIMARY KEY (repair_no, repair_item_name, fragment_part_no, arsenal_name),
    CONSTRAINT fk_usage_step FOREIGN KEY (repair_no, repair_item_name)
        REFERENCES repairSteps(repair_no, repair_item_name)
        ON DELETE CASCADE,
    CONSTRAINT fk_usage_inventory FOREIGN KEY (fragment_part_no, arsenal_name)
        REFERENCES arsenalTable(fragment_part_no, arsenal_name)
        ON DELETE CASCADE,
    CONSTRAINT check_arsenal_name_usage
        CHECK (arsenal_name IN ('نو', 'سالویج'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_supply_usage_repair   ON userSupplyUsage(repair_no, repair_item_name);
CREATE INDEX idx_supply_usage_fragment ON userSupplyUsage(fragment_part_no, arsenal_name);

-- ------------------------------------------------------------
-- ورود قطعات به انبار
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS supplyFragmentEntry (
    fragment_entry_no   INT AUTO_INCREMENT PRIMARY KEY,
    fragment_entry_name VARCHAR(191),
    fragment_entry_qty  INT,
    fragment_entry_date VARCHAR(50),
    fragment_part_no    VARCHAR(100),
    arsenal_name        VARCHAR(50),
    CONSTRAINT fk_entry_inventory FOREIGN KEY (fragment_part_no, arsenal_name)
        REFERENCES arsenalTable(fragment_part_no, arsenal_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_fragment_entry_part ON supplyFragmentEntry(fragment_part_no, arsenal_name);

-- ------------------------------------------------------------
-- گزارش مصرف قطعات
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS repairItemsReport (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    repair_no        INT,
    antenna_serial_no VARCHAR(191),
    manufacturer     VARCHAR(191),
    personal_id      INT,
    first_name       VARCHAR(100),
    last_name        VARCHAR(100),
    item_name        VARCHAR(191),
    fragment_name    VARCHAR(191),
    fragment_part_no VARCHAR(100),
    arsenal_name     VARCHAR(50),
    used_quantity    INT,
    status           VARCHAR(50),
    final_status     VARCHAR(50) DEFAULT 'در انتظار',
    repair_date      VARCHAR(50),
    CONSTRAINT fk_report_user FOREIGN KEY (personal_id) REFERENCES users(personal_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_repair_items_report_repair_no   ON repairItemsReport(repair_no);
CREATE INDEX idx_repair_items_report_personal_id ON repairItemsReport(personal_id);

-- ------------------------------------------------------------
-- نگاشت کد آیتم
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS itemCodeAssignments (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    manufacturer  VARCHAR(191) NOT NULL,
    antenna_type  VARCHAR(191) NOT NULL,
    tilt_type     VARCHAR(50)  NOT NULL,
    item_code     VARCHAR(100) NOT NULL,
    created_date  VARCHAR(50)  NOT NULL,
    created_time  VARCHAR(50)  NOT NULL,
    CONSTRAINT fk_itemcode_type  FOREIGN KEY (antenna_type) REFERENCES antennaTypes(antenna_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_item_code_manufacturer ON itemCodeAssignments(manufacturer);
CREATE INDEX idx_item_code_antenna_type ON itemCodeAssignments(antenna_type);
CREATE INDEX idx_item_code_item_code    ON itemCodeAssignments(item_code);

-- ------------------------------------------------------------
-- آنتن‌های تحویل‌شده
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS deliveredAntennas (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    repair_no         VARCHAR(50)  NOT NULL,
    antenna_serial_no VARCHAR(191) NOT NULL,
    antenna_type      VARCHAR(191) NOT NULL,
    manufacturer      VARCHAR(191) NOT NULL,
    item_code         VARCHAR(100) NOT NULL,
    entry_date        VARCHAR(50)  NOT NULL,
    antenna_status    VARCHAR(50)  NOT NULL,
    delivery_time     VARCHAR(50)  NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_delivered_serial   ON deliveredAntennas(antenna_serial_no);
CREATE INDEX idx_delivered_repair_no ON deliveredAntennas(repair_no);

-- ------------------------------------------------------------
-- تاریخچه عملیات انبار
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inventory_history (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    part_no       VARCHAR(100) NOT NULL,
    operation_type VARCHAR(50) NOT NULL,
    quantity      INT          NOT NULL,
    personal_id   VARCHAR(50)  NOT NULL,
    operation_date VARCHAR(50) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_inventory_history_part ON inventory_history(part_no);
CREATE INDEX idx_inventory_history_date ON inventory_history(operation_date);

-- ------------------------------------------------------------
-- تریگرها (همتراز با نسخه دسکتاپ)
-- ------------------------------------------------------------
DELIMITER //

CREATE TRIGGER trg_supply_usage_insert
AFTER INSERT ON userSupplyUsage
FOR EACH ROW
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM arsenalTable
        WHERE fragment_part_no = NEW.fragment_part_no
          AND arsenal_name = NEW.arsenal_name
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'عدم موجودی';
    END IF;

    UPDATE arsenalTable
    SET fragment_qty = fragment_qty - NEW.repair_fragment_qty
    WHERE fragment_part_no = NEW.fragment_part_no
      AND arsenal_name = NEW.arsenal_name;

    IF (SELECT fragment_qty FROM arsenalTable
        WHERE fragment_part_no = NEW.fragment_part_no
          AND arsenal_name = NEW.arsenal_name) < 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'کمبود موجودی';
    END IF;
END//

CREATE TRIGGER trg_supply_usage_update
AFTER UPDATE ON userSupplyUsage
FOR EACH ROW
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM arsenalTable
        WHERE fragment_part_no = NEW.fragment_part_no
          AND arsenal_name = NEW.arsenal_name
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'عدم موجودی';
    END IF;

    UPDATE arsenalTable
    SET fragment_qty = fragment_qty + OLD.repair_fragment_qty - NEW.repair_fragment_qty
    WHERE fragment_part_no = NEW.fragment_part_no
      AND arsenal_name = NEW.arsenal_name;

    IF (SELECT fragment_qty FROM arsenalTable
        WHERE fragment_part_no = NEW.fragment_part_no
          AND arsenal_name = NEW.arsenal_name) < 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'کمبود موجودی';
    END IF;
END//

CREATE TRIGGER trg_supply_usage_delete
AFTER DELETE ON userSupplyUsage
FOR EACH ROW
BEGIN
    UPDATE arsenalTable
    SET fragment_qty = fragment_qty + OLD.repair_fragment_qty
    WHERE fragment_part_no = OLD.fragment_part_no
      AND arsenal_name = OLD.arsenal_name;
END//

CREATE TRIGGER trg_fragment_entry_insert
AFTER INSERT ON supplyFragmentEntry
FOR EACH ROW
BEGIN
    INSERT IGNORE INTO arsenalTable (fragment_part_no, arsenal_name, fragment_name, fragment_qty)
    VALUES (NEW.fragment_part_no, NEW.arsenal_name, NEW.fragment_entry_name, 0);

    UPDATE arsenalTable
    SET fragment_qty = fragment_qty + NEW.fragment_entry_qty,
        fragment_name = NEW.fragment_entry_name
    WHERE fragment_part_no = NEW.fragment_part_no
      AND arsenal_name = NEW.arsenal_name;
END//

CREATE TRIGGER trg_repairs_exit_date
AFTER UPDATE ON repairs
FOR EACH ROW
BEGIN
    IF NEW.antenna_status = 'خروج'
       AND OLD.antenna_status <> 'خروج'
       AND NEW.exit_date IS NULL THEN
        UPDATE repairs
        SET exit_date = DATE_FORMAT(CONVERT_TZ(NOW(), '+00:00', '+03:30'), '%Y/%m/%d')
        WHERE repair_no = NEW.repair_no;
    END IF;
END//

DELIMITER ;

