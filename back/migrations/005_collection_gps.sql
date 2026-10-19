-- 005: additive capture identity and independent GPS stream, MySQL 5.7+.
-- Run on a reviewed isolated test database before production. DDL commits implicitly.
-- Do not replay 001-004 or import the destructive greenfield schema into an existing DB.
-- All new DATETIME(3) values are UTC. Legacy device_raw_data clocks remain UTC+08 naive.
CREATE TABLE collection_sessions (
  capture_id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
  clinician_id INT NOT NULL,
  patient_id INT NOT NULL,
  device_id INT NOT NULL,
  mobile_started_at DATETIME(3) NOT NULL,
  mobile_stopped_at DATETIME(3) NULL,
  server_created_at DATETIME(3) NOT NULL,
  server_stopped_at DATETIME(3) NULL,
  KEY idx_collection_patient (patient_id),
  FOREIGN KEY (clinician_id) REFERENCES clinicians(id),
  FOREIGN KEY (patient_id) REFERENCES patients(id),
  FOREIGN KEY (device_id) REFERENCES devices(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE collection_insole_frames (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  capture_id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  stream ENUM('insole') NOT NULL,
  event_id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  connection_epoch BIGINT NOT NULL,
  stream_sequence BIGINT NOT NULL,
  mobile_received_at DATETIME(3) NOT NULL,
  server_received_at DATETIME(3) NOT NULL,
  payload_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  left_raw_id INT NOT NULL UNIQUE,
  right_raw_id INT NOT NULL UNIQUE,
  UNIQUE KEY uq_collection_insole_event (capture_id,stream,event_id),
  UNIQUE KEY uq_collection_insole_sequence (capture_id,stream,connection_epoch,stream_sequence),
  CONSTRAINT ck_collection_insole_sequence CHECK (connection_epoch >= 0 AND stream_sequence >= 0),
  FOREIGN KEY (capture_id) REFERENCES collection_sessions(capture_id),
  FOREIGN KEY (left_raw_id) REFERENCES device_raw_data(id),
  FOREIGN KEY (right_raw_id) REFERENCES device_raw_data(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE collection_gps_raw (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  capture_id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  stream ENUM('gps') NOT NULL,
  event_id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  connection_epoch BIGINT NOT NULL,
  stream_sequence BIGINT NOT NULL,
  mobile_received_at DATETIME(3) NOT NULL,
  server_received_at DATETIME(3) NOT NULL,
  payload_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  raw_line VARCHAR(1024) NOT NULL,
  seq BIGINT NOT NULL,
  fix TINYINT(1) NOT NULL,
  lat DOUBLE NULL, lon DOUBLE NULL, alt DOUBLE NULL, speed DOUBLE NULL,
  sats BIGINT NOT NULL,
  hdop DOUBLE NULL,
  age BIGINT NOT NULL,
  utc VARCHAR(1024) NOT NULL,
  chars BIGINT NOT NULL,
  errors BIGINT NOT NULL,
  UNIQUE KEY uq_collection_gps_event (capture_id,stream,event_id),
  UNIQUE KEY uq_collection_gps_sequence (capture_id,stream,connection_epoch,stream_sequence),
  KEY idx_collection_gps_receive (capture_id,connection_epoch,mobile_received_at),
  CONSTRAINT ck_collection_gps_nonnegative CHECK (connection_epoch >= 0 AND stream_sequence >= 0 AND seq >= 0 AND sats >= 0 AND age >= 0 AND chars >= 0 AND errors >= 0),
  FOREIGN KEY (capture_id) REFERENCES collection_sessions(capture_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
