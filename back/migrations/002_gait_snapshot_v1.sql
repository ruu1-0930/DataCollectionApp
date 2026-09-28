-- 002: additive B snapshot persistence, MySQL 5.7+; forward-only DDL.
-- Apply only after 001 on a reviewed test database, then deploy separately.
-- MySQL DDL commits implicitly; this script is NOT a transaction or rollback.
-- MySQL native ENUM needs strict SQL mode on application connections; triggers below
-- enforce positive numeric fields because MySQL 5.7 ignores CHECK.
-- Application identity has INSERT/SELECT only on clinical_audit_event; migrations use a separate identity.
-- DataCollectionApp raw ingestion and the six clinical source tables are untouched.

CREATE TABLE gait_session_revision (
  id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  patient_id INT NOT NULL,
  device_id INT NOT NULL,
  session_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  revision INT NOT NULL,
  state ENUM('collecting','closed_by_inactivity','superseded') NOT NULL,
  ordered_row_ids_canonical LONGTEXT COLLATE utf8mb4_bin NOT NULL,
  first_row_id INT NOT NULL,
  last_row_id INT NOT NULL,
  row_count INT NOT NULL,
  last_accepted_row_id INT NOT NULL,
  event_start_at DATETIME(6) NOT NULL,
  event_end_at DATETIME(6) NOT NULL,
  ingest_start_at DATETIME(6) NOT NULL,
  ingest_end_at DATETIME(6) NOT NULL,
  closure_policy_version VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  closure_evidence_canonical LONGTEXT COLLATE utf8mb4_bin NULL,
  closed_at DATETIME(3) NULL,
  superseded_by_revision_id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
  created_at DATETIME(3) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_session_revision (patient_id, session_key, revision),
  UNIQUE KEY uq_session_revision_patient (id, patient_id),
  KEY ix_session_device (device_id),
  KEY ix_session_first_row (first_row_id),
  KEY ix_session_last_row (last_row_id),
  KEY ix_session_last_accepted_row (last_accepted_row_id),
  KEY ix_session_superseded_by (superseded_by_revision_id),
  CONSTRAINT fk_session_patient FOREIGN KEY (patient_id) REFERENCES patients(id),
  CONSTRAINT fk_session_device FOREIGN KEY (device_id) REFERENCES devices(id),
  CONSTRAINT fk_session_first_row FOREIGN KEY (first_row_id) REFERENCES device_raw_data(id),
  CONSTRAINT fk_session_last_row FOREIGN KEY (last_row_id) REFERENCES device_raw_data(id),
  CONSTRAINT fk_session_last_accepted_row FOREIGN KEY (last_accepted_row_id) REFERENCES device_raw_data(id),
  CONSTRAINT fk_session_superseded_by FOREIGN KEY (superseded_by_revision_id) REFERENCES gait_session_revision(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE snapshot_build_attempt (
  id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  identity_fingerprint VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  attempt_number INT NOT NULL,
  state ENUM('pending','running','succeeded','failed') NOT NULL,
  error_code VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  error_message VARCHAR(256) NULL,
  trace_id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  created_at DATETIME(3) NOT NULL,
  started_at DATETIME(3) NULL,
  finished_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_build_attempt_number (identity_fingerprint, attempt_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE analysis_snapshot (
  id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  patient_id INT NOT NULL,
  session_revision_id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  raw_data_fingerprint VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  identity_fingerprint VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  snapshot_schema_version VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  analyzer_set_version VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  threshold_profile_version VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  canonical_payload LONGTEXT COLLATE utf8mb4_bin NOT NULL,
  content_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  state ENUM('published','superseded') NOT NULL,
  state_version INT NOT NULL,
  superseded_by_snapshot_id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
  created_at DATETIME(3) NOT NULL,
  published_at DATETIME(3) NOT NULL,
  superseded_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_snapshot_identity (patient_id, session_revision_id, raw_data_fingerprint, snapshot_schema_version, analyzer_set_version, threshold_profile_version),
  UNIQUE KEY uq_snapshot_identity_fingerprint (identity_fingerprint),
  KEY ix_snapshot_revision_patient (session_revision_id, patient_id),
  KEY ix_snapshot_superseded_by (superseded_by_snapshot_id),
  CONSTRAINT fk_snapshot_patient FOREIGN KEY (patient_id) REFERENCES patients(id),
  CONSTRAINT fk_snapshot_revision_patient FOREIGN KEY (session_revision_id, patient_id) REFERENCES gait_session_revision(id, patient_id),
  CONSTRAINT fk_snapshot_superseded_by FOREIGN KEY (superseded_by_snapshot_id) REFERENCES analysis_snapshot(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE agent_snapshot_projection (
  snapshot_id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  projection_schema_version VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  canonical_payload LONGTEXT COLLATE utf8mb4_bin NOT NULL,
  content_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  created_at DATETIME(3) NOT NULL,
  PRIMARY KEY (snapshot_id, projection_schema_version),
  CONSTRAINT fk_projection_snapshot FOREIGN KEY (snapshot_id) REFERENCES analysis_snapshot(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE snapshot_publication_claim (
  id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  snapshot_id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  state_version INT NOT NULL,
  workflow_run_id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  candidate_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  actor_id INT NOT NULL,
  claimed_at DATETIME(3) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_snapshot_claim (snapshot_id, state_version, workflow_run_id, candidate_hash),
  KEY ix_claim_actor (actor_id),
  CONSTRAINT fk_claim_snapshot FOREIGN KEY (snapshot_id) REFERENCES analysis_snapshot(id),
  CONSTRAINT fk_claim_actor FOREIGN KEY (actor_id) REFERENCES clinicians(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE clinical_audit_event (
  id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  trace_id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  actor_id INT NOT NULL,
  patient_id INT NOT NULL,
  session_revision_id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
  snapshot_id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
  action VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  result VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  canonical_payload LONGTEXT COLLATE utf8mb4_bin NOT NULL,
  event_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  previous_event_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  created_at DATETIME(3) NOT NULL,
  PRIMARY KEY (id),
  KEY ix_audit_actor (actor_id),
  KEY ix_audit_patient (patient_id),
  KEY ix_audit_revision (session_revision_id),
  KEY ix_audit_snapshot (snapshot_id),
  CONSTRAINT fk_audit_actor FOREIGN KEY (actor_id) REFERENCES clinicians(id),
  CONSTRAINT fk_audit_patient FOREIGN KEY (patient_id) REFERENCES patients(id),
  CONSTRAINT fk_audit_revision FOREIGN KEY (session_revision_id) REFERENCES gait_session_revision(id),
  CONSTRAINT fk_audit_snapshot FOREIGN KEY (snapshot_id) REFERENCES analysis_snapshot(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE integration_outbox (
  id BIGINT NOT NULL AUTO_INCREMENT,
  event_type VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  event_version VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  snapshot_id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  patient_id INT NOT NULL,
  state_version INT NOT NULL,
  canonical_payload LONGTEXT COLLATE utf8mb4_bin NOT NULL,
  content_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  created_at DATETIME(3) NOT NULL,
  published_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  KEY ix_outbox_snapshot (snapshot_id),
  KEY ix_outbox_patient (patient_id),
  CONSTRAINT fk_outbox_snapshot FOREIGN KEY (snapshot_id) REFERENCES analysis_snapshot(id),
  CONSTRAINT fk_outbox_patient FOREIGN KEY (patient_id) REFERENCES patients(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

DELIMITER $$

CREATE TRIGGER trg_gait_session_revision_frozen BEFORE UPDATE ON gait_session_revision
FOR EACH ROW BEGIN
  IF NOT (BINARY NEW.id <=> BINARY OLD.id) OR NOT (BINARY NEW.patient_id <=> BINARY OLD.patient_id) OR NOT (BINARY NEW.device_id <=> BINARY OLD.device_id) OR NOT (BINARY NEW.session_key <=> BINARY OLD.session_key) OR NOT (BINARY NEW.revision <=> BINARY OLD.revision) OR NOT (BINARY NEW.created_at <=> BINARY OLD.created_at) OR (OLD.state <> 'collecting' AND (NOT (BINARY NEW.ordered_row_ids_canonical <=> BINARY OLD.ordered_row_ids_canonical) OR NOT (BINARY NEW.first_row_id <=> BINARY OLD.first_row_id) OR NOT (BINARY NEW.last_row_id <=> BINARY OLD.last_row_id) OR NOT (BINARY NEW.row_count <=> BINARY OLD.row_count) OR NOT (BINARY NEW.last_accepted_row_id <=> BINARY OLD.last_accepted_row_id) OR NOT (BINARY NEW.event_start_at <=> BINARY OLD.event_start_at) OR NOT (BINARY NEW.event_end_at <=> BINARY OLD.event_end_at) OR NOT (BINARY NEW.ingest_start_at <=> BINARY OLD.ingest_start_at) OR NOT (BINARY NEW.ingest_end_at <=> BINARY OLD.ingest_end_at) OR NOT (BINARY NEW.closure_policy_version <=> BINARY OLD.closure_policy_version) OR NOT (BINARY NEW.closure_evidence_canonical <=> BINARY OLD.closure_evidence_canonical) OR NOT (BINARY NEW.closed_at <=> BINARY OLD.closed_at))) OR (OLD.state <> 'collecting' AND NEW.state = 'collecting') THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'frozen session revision';
  END IF;
END$$

CREATE TRIGGER trg_analysis_snapshot_immutable BEFORE UPDATE ON analysis_snapshot
FOR EACH ROW BEGIN
  IF NOT (BINARY NEW.id <=> BINARY OLD.id) OR NOT (BINARY NEW.patient_id <=> BINARY OLD.patient_id) OR NOT (BINARY NEW.session_revision_id <=> BINARY OLD.session_revision_id) OR NOT (BINARY NEW.raw_data_fingerprint <=> BINARY OLD.raw_data_fingerprint) OR NOT (BINARY NEW.identity_fingerprint <=> BINARY OLD.identity_fingerprint) OR NOT (BINARY NEW.snapshot_schema_version <=> BINARY OLD.snapshot_schema_version) OR NOT (BINARY NEW.analyzer_set_version <=> BINARY OLD.analyzer_set_version) OR NOT (BINARY NEW.threshold_profile_version <=> BINARY OLD.threshold_profile_version) OR NOT (BINARY NEW.canonical_payload <=> BINARY OLD.canonical_payload) OR NOT (BINARY NEW.content_hash <=> BINARY OLD.content_hash) OR NOT (BINARY NEW.created_at <=> BINARY OLD.created_at) OR NOT (BINARY NEW.published_at <=> BINARY OLD.published_at) OR NEW.state_version < OLD.state_version OR (NEW.state <> OLD.state AND NEW.state_version <= OLD.state_version) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'immutable content or state version';
  END IF;
END$$

CREATE TRIGGER trg_agent_snapshot_projection_immutable BEFORE UPDATE ON agent_snapshot_projection
FOR EACH ROW BEGIN
  IF NOT (BINARY NEW.snapshot_id <=> BINARY OLD.snapshot_id) OR NOT (BINARY NEW.projection_schema_version <=> BINARY OLD.projection_schema_version) OR NOT (BINARY NEW.canonical_payload <=> BINARY OLD.canonical_payload) OR NOT (BINARY NEW.content_hash <=> BINARY OLD.content_hash) OR NOT (BINARY NEW.created_at <=> BINARY OLD.created_at) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'immutable content or state version';
  END IF;
END$$

CREATE TRIGGER trg_snapshot_publication_claim_immutable BEFORE UPDATE ON snapshot_publication_claim
FOR EACH ROW BEGIN
  IF NOT (BINARY NEW.id <=> BINARY OLD.id) OR NOT (BINARY NEW.snapshot_id <=> BINARY OLD.snapshot_id) OR NOT (BINARY NEW.state_version <=> BINARY OLD.state_version) OR NOT (BINARY NEW.workflow_run_id <=> BINARY OLD.workflow_run_id) OR NOT (BINARY NEW.candidate_hash <=> BINARY OLD.candidate_hash) OR NOT (BINARY NEW.actor_id <=> BINARY OLD.actor_id) OR NOT (BINARY NEW.claimed_at <=> BINARY OLD.claimed_at) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'immutable content or state version';
  END IF;
END$$

CREATE TRIGGER trg_integration_outbox_immutable BEFORE UPDATE ON integration_outbox
FOR EACH ROW BEGIN
  IF NOT (BINARY NEW.id <=> BINARY OLD.id) OR NOT (BINARY NEW.event_type <=> BINARY OLD.event_type) OR NOT (BINARY NEW.event_version <=> BINARY OLD.event_version) OR NOT (BINARY NEW.snapshot_id <=> BINARY OLD.snapshot_id) OR NOT (BINARY NEW.patient_id <=> BINARY OLD.patient_id) OR NOT (BINARY NEW.state_version <=> BINARY OLD.state_version) OR NOT (BINARY NEW.canonical_payload <=> BINARY OLD.canonical_payload) OR NOT (BINARY NEW.content_hash <=> BINARY OLD.content_hash) OR NOT (BINARY NEW.created_at <=> BINARY OLD.created_at) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'immutable content or state version';
  END IF;
END$$

CREATE TRIGGER trg_gait_session_revision_positive_insert BEFORE INSERT ON gait_session_revision
FOR EACH ROW BEGIN
  IF NEW.revision < 1 OR NEW.row_count < 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'positive values required';
  END IF;
END$$

CREATE TRIGGER trg_gait_session_revision_positive_update BEFORE UPDATE ON gait_session_revision
FOR EACH ROW BEGIN
  IF NEW.revision < 1 OR NEW.row_count < 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'positive values required';
  END IF;
END$$

CREATE TRIGGER trg_snapshot_build_attempt_positive_insert BEFORE INSERT ON snapshot_build_attempt
FOR EACH ROW BEGIN
  IF NEW.attempt_number < 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'positive values required';
  END IF;
END$$

CREATE TRIGGER trg_snapshot_build_attempt_positive_update BEFORE UPDATE ON snapshot_build_attempt
FOR EACH ROW BEGIN
  IF NEW.attempt_number < 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'positive values required';
  END IF;
END$$

CREATE TRIGGER trg_analysis_snapshot_positive_insert BEFORE INSERT ON analysis_snapshot
FOR EACH ROW BEGIN
  IF NEW.state_version < 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'positive values required';
  END IF;
END$$

CREATE TRIGGER trg_analysis_snapshot_positive_update BEFORE UPDATE ON analysis_snapshot
FOR EACH ROW BEGIN
  IF NEW.state_version < 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'positive values required';
  END IF;
END$$

CREATE TRIGGER trg_snapshot_publication_claim_positive_insert BEFORE INSERT ON snapshot_publication_claim
FOR EACH ROW BEGIN
  IF NEW.state_version < 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'positive values required';
  END IF;
END$$

CREATE TRIGGER trg_snapshot_publication_claim_positive_update BEFORE UPDATE ON snapshot_publication_claim
FOR EACH ROW BEGIN
  IF NEW.state_version < 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'positive values required';
  END IF;
END$$

CREATE TRIGGER trg_integration_outbox_positive_insert BEFORE INSERT ON integration_outbox
FOR EACH ROW BEGIN
  IF NEW.state_version < 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'positive values required';
  END IF;
END$$

CREATE TRIGGER trg_integration_outbox_positive_update BEFORE UPDATE ON integration_outbox
FOR EACH ROW BEGIN
  IF NEW.state_version < 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'positive values required';
  END IF;
END$$

CREATE TRIGGER trg_clinical_audit_event_no_update BEFORE UPDATE ON clinical_audit_event
FOR EACH ROW BEGIN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'append-only clinical audit';
END$$

CREATE TRIGGER trg_clinical_audit_event_no_delete BEFORE DELETE ON clinical_audit_event
FOR EACH ROW BEGIN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'append-only clinical audit';
END$$

DELIMITER ;
