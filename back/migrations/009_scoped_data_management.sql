-- 009: maintenance window only; stop API writers first. No FK disable.
CREATE TABLE data_management_preview (
 id VARCHAR(36) PRIMARY KEY, actor_id INT NOT NULL, scope_json LONGTEXT NOT NULL,
 inventory_json LONGTEXT NOT NULL, scope_hash VARCHAR(64) NOT NULL, expires_at DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE data_management_operation (
 id VARCHAR(36) PRIMARY KEY, request_id VARCHAR(36) NOT NULL, preview_id VARCHAR(36) NOT NULL,
 actor_id INT NOT NULL, owner_id INT NOT NULL, patient_id INT NOT NULL, kind VARCHAR(32) NOT NULL,
 record_id VARCHAR(128) NOT NULL, scope_json LONGTEXT NOT NULL, scope_hash VARCHAR(64) NOT NULL,
 inventory_json LONGTEXT NOT NULL, counts_json LONGTEXT NOT NULL, trace_id VARCHAR(36) NOT NULL,
 stage VARCHAR(32) NOT NULL, state VARCHAR(32) NOT NULL, error_code VARCHAR(64), discard_pending BOOLEAN NOT NULL,
 created_at DATETIME(6) NOT NULL, completed_at DATETIME(6),
 UNIQUE KEY uq_management_request(actor_id,request_id), KEY ix_management_patient(patient_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE data_management_item (
 operation_id VARCHAR(36) NOT NULL, table_name VARCHAR(64) NOT NULL, row_id VARCHAR(128) NOT NULL,
 PRIMARY KEY(operation_id,table_name,row_id), FOREIGN KEY(operation_id) REFERENCES data_management_operation(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE data_management_audit_bridge (
 event_hash VARCHAR(64) PRIMARY KEY, previous_event_hash VARCHAR(64), operation_id VARCHAR(36) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

DELIMITER $$
DROP TRIGGER trg_clinical_audit_event_no_delete$$
CREATE TRIGGER trg_clinical_audit_event_no_delete BEFORE DELETE ON clinical_audit_event FOR EACH ROW
BEGIN
 IF NOT EXISTS (SELECT 1 FROM data_management_item i JOIN data_management_operation o ON o.id=i.operation_id WHERE i.table_name='clinical_audit_event' AND i.row_id=CAST(OLD.id AS CHAR) AND o.stage='agent_purged' AND o.state='running') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='scoped management required';
 END IF;
END$$
CREATE TRIGGER trg_device_raw_data_no_delete BEFORE DELETE ON device_raw_data FOR EACH ROW
BEGIN
 IF NOT EXISTS (SELECT 1 FROM data_management_item i JOIN data_management_operation o ON o.id=i.operation_id WHERE i.table_name='device_raw_data' AND i.row_id=CAST(OLD.id AS CHAR) AND o.stage='agent_purged' AND o.state='running') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='scoped management required';
 END IF;
END$$
CREATE TRIGGER trg_device_transformed_data_no_delete BEFORE DELETE ON device_transformed_data FOR EACH ROW
BEGIN
 IF NOT EXISTS (SELECT 1 FROM data_management_item i JOIN data_management_operation o ON o.id=i.operation_id WHERE i.table_name='device_transformed_data' AND i.row_id=CAST(OLD.id AS CHAR) AND o.stage='agent_purged' AND o.state='running') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='scoped management required';
 END IF;
END$$
CREATE TRIGGER trg_collection_sessions_no_delete BEFORE DELETE ON collection_sessions FOR EACH ROW
BEGIN
 IF NOT EXISTS (SELECT 1 FROM data_management_item i JOIN data_management_operation o ON o.id=i.operation_id WHERE i.table_name='collection_sessions' AND i.row_id=CAST(OLD.capture_id AS CHAR) AND o.stage='agent_purged' AND o.state='running') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='scoped management required';
 END IF;
END$$
CREATE TRIGGER trg_collection_insole_frames_no_delete BEFORE DELETE ON collection_insole_frames FOR EACH ROW
BEGIN
 IF NOT EXISTS (SELECT 1 FROM data_management_item i JOIN data_management_operation o ON o.id=i.operation_id WHERE i.table_name='collection_insole_frames' AND i.row_id=CAST(OLD.id AS CHAR) AND o.stage='agent_purged' AND o.state='running') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='scoped management required';
 END IF;
END$$
CREATE TRIGGER trg_collection_gps_raw_no_delete BEFORE DELETE ON collection_gps_raw FOR EACH ROW
BEGIN
 IF NOT EXISTS (SELECT 1 FROM data_management_item i JOIN data_management_operation o ON o.id=i.operation_id WHERE i.table_name='collection_gps_raw' AND i.row_id=CAST(OLD.id AS CHAR) AND o.stage='agent_purged' AND o.state='running') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='scoped management required';
 END IF;
END$$
CREATE TRIGGER trg_collection_radar_raw_no_delete BEFORE DELETE ON collection_radar_raw FOR EACH ROW
BEGIN
 IF NOT EXISTS (SELECT 1 FROM data_management_item i JOIN data_management_operation o ON o.id=i.operation_id WHERE i.table_name='collection_radar_raw' AND i.row_id=CAST(OLD.id AS CHAR) AND o.stage='agent_purged' AND o.state='running') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='scoped management required';
 END IF;
END$$
CREATE TRIGGER trg_collection_radar_targets_no_delete BEFORE DELETE ON collection_radar_targets FOR EACH ROW
BEGIN
 IF NOT EXISTS (SELECT 1 FROM data_management_item i JOIN data_management_operation o ON o.id=i.operation_id WHERE i.table_name='collection_radar_targets' AND i.row_id=CAST(OLD.id AS CHAR) AND o.stage='agent_purged' AND o.state='running') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='scoped management required';
 END IF;
END$$
CREATE TRIGGER trg_gait_session_revision_no_delete BEFORE DELETE ON gait_session_revision FOR EACH ROW
BEGIN
 IF NOT EXISTS (SELECT 1 FROM data_management_item i JOIN data_management_operation o ON o.id=i.operation_id WHERE i.table_name='gait_session_revision' AND i.row_id=CAST(OLD.id AS CHAR) AND o.stage='agent_purged' AND o.state='running') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='scoped management required';
 END IF;
END$$
CREATE TRIGGER trg_analysis_snapshot_no_delete BEFORE DELETE ON analysis_snapshot FOR EACH ROW
BEGIN
 IF NOT EXISTS (SELECT 1 FROM data_management_item i JOIN data_management_operation o ON o.id=i.operation_id WHERE i.table_name='analysis_snapshot' AND i.row_id=CAST(OLD.id AS CHAR) AND o.stage='agent_purged' AND o.state='running') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='scoped management required';
 END IF;
END$$
CREATE TRIGGER trg_agent_snapshot_projection_no_delete BEFORE DELETE ON agent_snapshot_projection FOR EACH ROW
BEGIN
 IF NOT EXISTS (SELECT 1 FROM data_management_item i JOIN data_management_operation o ON o.id=i.operation_id WHERE i.table_name='agent_snapshot_projection' AND i.row_id=CAST(OLD.snapshot_id AS CHAR) AND o.stage='agent_purged' AND o.state='running') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='scoped management required';
 END IF;
END$$
CREATE TRIGGER trg_snapshot_publication_claim_no_delete BEFORE DELETE ON snapshot_publication_claim FOR EACH ROW
BEGIN
 IF NOT EXISTS (SELECT 1 FROM data_management_item i JOIN data_management_operation o ON o.id=i.operation_id WHERE i.table_name='snapshot_publication_claim' AND i.row_id=CAST(OLD.id AS CHAR) AND o.stage='agent_purged' AND o.state='running') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='scoped management required';
 END IF;
END$$
CREATE TRIGGER trg_integration_outbox_no_delete BEFORE DELETE ON integration_outbox FOR EACH ROW
BEGIN
 IF NOT EXISTS (SELECT 1 FROM data_management_item i JOIN data_management_operation o ON o.id=i.operation_id WHERE i.table_name='integration_outbox' AND i.row_id=CAST(OLD.id AS CHAR) AND o.stage='agent_purged' AND o.state='running') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='scoped management required';
 END IF;
END$$
CREATE TRIGGER trg_snapshot_build_attempt_no_delete BEFORE DELETE ON snapshot_build_attempt FOR EACH ROW
BEGIN
 IF NOT EXISTS (SELECT 1 FROM data_management_item i JOIN data_management_operation o ON o.id=i.operation_id WHERE i.table_name='snapshot_build_attempt' AND i.row_id=CAST(OLD.id AS CHAR) AND o.stage='agent_purged' AND o.state='running') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='scoped management required';
 END IF;
END$$
DELIMITER ;
