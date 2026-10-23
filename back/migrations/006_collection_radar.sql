-- 006: additive independent radar observations; never replay 005 or import greenfield schema.
-- Requires enforced CHECK constraints (MySQL 8.0.16+); verify in an isolated DB before rollout.
-- All DATETIME(3) clocks are UTC; no old raw or snapshot backfill.
CREATE TABLE collection_radar_raw (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  capture_id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  stream ENUM('radar') NOT NULL,
  event_id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  connection_epoch BIGINT NOT NULL,
  stream_sequence BIGINT NOT NULL,
  mobile_received_at DATETIME(3) NOT NULL,
  server_received_at DATETIME(3) NOT NULL,
  payload_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  payload_json LONGTEXT COLLATE utf8mb4_bin NOT NULL,
  frames BIGINT NOT NULL,
  bytes BIGINT NOT NULL,
  age_ms DOUBLE NULL,
  stale TINYINT(1) NOT NULL,
  UNIQUE KEY uq_collection_radar_event (capture_id,stream,event_id),
  UNIQUE KEY uq_collection_radar_sequence (capture_id,stream,connection_epoch,stream_sequence),
  KEY idx_collection_radar_receive (capture_id,mobile_received_at),
  CONSTRAINT ck_collection_radar_counters CHECK (connection_epoch BETWEEN 0 AND 9007199254740991 AND stream_sequence BETWEEN 0 AND 9007199254740991 AND frames BETWEEN 0 AND 9007199254740991 AND bytes BETWEEN 0 AND 9007199254740991),
  CONSTRAINT ck_collection_radar_age CHECK (age_ms IS NULL OR (age_ms >= 0 AND age_ms <= 1.7976931348623157e308)),
  CONSTRAINT ck_collection_radar_stale CHECK (stale IN (0,1)),
  FOREIGN KEY (capture_id) REFERENCES collection_sessions(capture_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE collection_radar_targets (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  parent_id INT NOT NULL,
  slot INT NOT NULL,
  ordinal INT NOT NULL,
  present TINYINT(1) NOT NULL,
  x_mm INT NOT NULL,
  y_mm INT NOT NULL,
  speed_cms INT NOT NULL,
  resolution_mm INT NOT NULL,
  UNIQUE KEY uq_collection_radar_target_slot (parent_id,slot),
  UNIQUE KEY uq_collection_radar_target_ordinal (parent_id,ordinal),
  CONSTRAINT ck_collection_radar_target_slot CHECK (slot BETWEEN 1 AND 3 AND ordinal BETWEEN 0 AND 2),
  CONSTRAINT ck_collection_radar_target_present CHECK (present IN (0,1)),
  CONSTRAINT ck_collection_radar_target_values CHECK (x_mm BETWEEN -32767 AND 32767 AND y_mm BETWEEN -32767 AND 32767 AND speed_cms BETWEEN -32767 AND 32767 AND resolution_mm BETWEEN 0 AND 65535),
  FOREIGN KEY (parent_id) REFERENCES collection_radar_raw(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
