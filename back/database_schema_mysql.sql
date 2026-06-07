-- 后端重构 scope A 权威 schema（与 back/models/models.py 一致）
-- 绿场净重设：无历史数据迁移。字符集 utf8mb4。

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS device_transformed_data;
DROP TABLE IF EXISTS device_raw_data;
DROP TABLE IF EXISTS patient_pii;
DROP TABLE IF EXISTS patients;
DROP TABLE IF EXISTS devices;
DROP TABLE IF EXISTS clinicians;
-- 旧模型表一并废弃
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS weekly_schedules;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE clinicians (
  id INT AUTO_INCREMENT PRIMARY KEY,
  hospital VARCHAR(100) NOT NULL,
  dept VARCHAR(100) NOT NULL,
  name VARCHAR(50) NOT NULL,
  phone VARCHAR(20) NOT NULL,
  terminal_code VARCHAR(100) NOT NULL,
  passcode_hash VARCHAR(255) NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_clinician_phone_terminal (phone, terminal_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE devices (
  id INT AUTO_INCREMENT PRIMARY KEY,
  device_code VARCHAR(50) NOT NULL UNIQUE,
  device_name VARCHAR(100),
  is_enabled TINYINT(1) DEFAULT 1,
  clinician_id INT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  KEY idx_devices_clinician (clinician_id),
  CONSTRAINT fk_devices_clinician FOREIGN KEY (clinician_id) REFERENCES clinicians(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE patients (
  id INT AUTO_INCREMENT PRIMARY KEY,
  clinician_id INT NOT NULL,
  subject_id VARCHAR(20) NOT NULL UNIQUE,
  gender VARCHAR(10),
  age INT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  last_collected_at DATETIME,
  KEY idx_patients_clinician (clinician_id),
  CONSTRAINT fk_patients_clinician FOREIGN KEY (clinician_id) REFERENCES clinicians(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE patient_pii (
  patient_id INT PRIMARY KEY,
  name VARCHAR(50) NOT NULL,
  phone VARCHAR(20) NOT NULL,
  email VARCHAR(100),
  address VARCHAR(255),
  CONSTRAINT fk_pii_patient FOREIGN KEY (patient_id) REFERENCES patients(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE device_raw_data (
  id INT AUTO_INCREMENT PRIMARY KEY,
  device_id INT NOT NULL,
  patient_id INT NOT NULL,
  clinician_id INT NOT NULL,
  ax FLOAT NOT NULL, ay FLOAT NOT NULL, az FLOAT NOT NULL,
  gx FLOAT NOT NULL, gy FLOAT NOT NULL, gz FLOAT NOT NULL,
  collected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  KEY idx_raw_device (device_id),
  KEY idx_raw_clinician (clinician_id),
  KEY idx_raw_patient_collected (patient_id, collected_at),
  CONSTRAINT fk_raw_device FOREIGN KEY (device_id) REFERENCES devices(id),
  CONSTRAINT fk_raw_patient FOREIGN KEY (patient_id) REFERENCES patients(id),
  CONSTRAINT fk_raw_clinician FOREIGN KEY (clinician_id) REFERENCES clinicians(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE device_transformed_data (
  id INT AUTO_INCREMENT PRIMARY KEY,
  raw_data_id INT NOT NULL,
  T1 FLOAT NOT NULL, T2 FLOAT NOT NULL, T3 FLOAT NOT NULL, T4 FLOAT NOT NULL, T5 FLOAT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  KEY idx_tr_raw (raw_data_id),
  CONSTRAINT fk_tr_raw FOREIGN KEY (raw_data_id) REFERENCES device_raw_data(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
