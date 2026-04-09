-- ============================================================
-- WildWatch — MySQL Setup Script
-- Database: wildanimal
-- Run: mysql -u root -p < setup_db.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS wildanimal CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE wildanimal;

-- Residents table (zone_id: 1=Webcam, 2=Video Zone2, 3=Video Zone3)
CREATE TABLE IF NOT EXISTS residents (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(80)  NOT NULL UNIQUE,
    password    VARCHAR(255) NOT NULL,
    phone       VARCHAR(20),
    name        VARCHAR(120),
    zone_id     INT          DEFAULT 1,
    created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP
);

-- Detection log (filled by app automatically)
CREATE TABLE IF NOT EXISTS detections (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    zone_id       INT          NOT NULL,
    species       VARCHAR(50),
    confidence    FLOAT,
    risk_level    VARCHAR(20),
    snapshot_path VARCHAR(255),
    detected_at   DATETIME     DEFAULT CURRENT_TIMESTAMP
);

-- Officers table
CREATE TABLE IF NOT EXISTS officers (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    username     VARCHAR(80)  NOT NULL UNIQUE,
    password     VARCHAR(255) NOT NULL,
    name         VARCHAR(120) NOT NULL,
    badge_number VARCHAR(30),
    phone        VARCHAR(20),
    `range`      VARCHAR(100) DEFAULT 'Erattupetta Range',
    designation  VARCHAR(100) DEFAULT 'Forest Officer',
    created_at   DATETIME     DEFAULT CURRENT_TIMESTAMP
);

-- ── Seed test residents ──────────────────────────────────────
INSERT IGNORE INTO residents (username, password, phone, name, zone_id) VALUES
  ('user',    'alert123', '9876543210', 'Test Resident', 1),
  ('resi1',   'pass123',  '9876543211', 'Anil Kumar',    1),
  ('resi2',   'pass123',  '9876543212', 'Sreeja P.',     2),
  ('resi3',   'pass123',  '9876543213', 'Manoj T.',      3);

-- ── Seed forest officers ─────────────────────────────────────
INSERT IGNORE INTO officers (username, password, name, badge_number, phone, `range`, designation) VALUES
  ('officer',  'forest123', 'Rajan K.',         'KL-FOR-301', '9447123456', 'Erattupetta Range',  'Forest Officer'),
  ('rfo',      'range123',  'Thomaschan V.',     'KL-FOR-302', '9447123457', 'Erattupetta Range',  'Range Forest Officer'),
  ('dfo',      'dept123',   'Sheeba Mathew',     'KL-FOR-303', '9447123458', 'Kottayam Division',  'Deputy Forest Officer');

SELECT 'Setup complete.' AS status;
SELECT 'Residents:' AS info;
SELECT id, username, name, zone_id FROM residents;
SELECT 'Officers:' AS info;
SELECT id, username, name, badge_number, designation FROM officers;

