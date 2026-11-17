-- 007: additive collection registration metadata and current patient body fields.
-- MySQL 5.7+; rehearse on a reviewed isolated database before manual production use.
-- DDL commits implicitly. Do not replay the destructive greenfield schema.
-- Keep legacy metadata NULL: no guessed test types, registrations or hashes.
ALTER TABLE patient_pii MODIFY COLUMN phone VARCHAR(20) NULL;
ALTER TABLE patients
  ADD COLUMN height_cm DOUBLE NULL,
  ADD COLUMN weight_kg DOUBLE NULL,
  ADD COLUMN shoe_size_eu DOUBLE NULL;
ALTER TABLE collection_sessions
  ADD COLUMN metadata_schema_version INT NULL,
  ADD COLUMN test_type VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
  ADD COLUMN registration_json LONGTEXT COLLATE utf8mb4_bin NULL,
  ADD COLUMN registration_hash VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  ADD COLUMN final_counts_json LONGTEXT COLLATE utf8mb4_bin NULL,
  ADD COLUMN finalization_state VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
  ADD KEY idx_collection_patient_type_started (patient_id, test_type, mobile_started_at);
