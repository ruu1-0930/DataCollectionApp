-- 迁移 001：device_raw_data 由「6 轴 IMU」扩为「每脚一帧 19 传感字段 + L/R 标记」
-- 依据：硬件原始导出格式（每行带 L/R，9 压力 + 6 IMU + 4 步态，A 列为毫秒级 UTC 采集时刻）。
-- 前提：绿场无历史数据（CLAUDE.md 阶段 0/1），对空表 ADD ... NOT NULL 安全、无需 DEFAULT 回填。
-- 演练：先在测试库执行本脚本，确认无报错、列齐全，再上 RDS（§3.3）。
-- 若线上 device_raw_data 已有行，须改为先 ADD ... NULL → 回填 → 再 ALTER ... NOT NULL，不可直接跑本脚本。

START TRANSACTION;

ALTER TABLE device_raw_data
  ADD COLUMN foot ENUM('L','R') NOT NULL AFTER clinician_id,
  ADD COLUMN p1 FLOAT NOT NULL AFTER foot,
  ADD COLUMN p2 FLOAT NOT NULL AFTER p1,
  ADD COLUMN p3 FLOAT NOT NULL AFTER p2,
  ADD COLUMN p4 FLOAT NOT NULL AFTER p3,
  ADD COLUMN p5 FLOAT NOT NULL AFTER p4,
  ADD COLUMN p6 FLOAT NOT NULL AFTER p5,
  ADD COLUMN p7 FLOAT NOT NULL AFTER p6,
  ADD COLUMN p8 FLOAT NOT NULL AFTER p7,
  ADD COLUMN p9 FLOAT NOT NULL AFTER p8,
  ADD COLUMN step_length FLOAT NOT NULL AFTER gz,
  ADD COLUMN walking_speed FLOAT NOT NULL AFTER step_length,
  ADD COLUMN single_support_time FLOAT NOT NULL AFTER walking_speed,
  ADD COLUMN double_support_time FLOAT NOT NULL AFTER single_support_time;

-- 采集时刻提升到毫秒精度（原始 A 列含 .xxx）
ALTER TABLE device_raw_data
  MODIFY COLUMN collected_at DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3);

COMMIT;
