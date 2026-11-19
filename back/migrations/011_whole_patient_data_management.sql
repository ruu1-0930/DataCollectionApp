-- Apply after 009 and 010 in a maintenance window before enabling data management.
-- Existing capture operations and immutable-data triggers remain in place.
ALTER TABLE data_management_operation MODIFY COLUMN record_id VARCHAR(128) NULL;

DELIMITER $$
CREATE TRIGGER trg_patients_no_delete BEFORE DELETE ON patients FOR EACH ROW
BEGIN
 IF NOT EXISTS (
   SELECT 1 FROM data_management_item i JOIN data_management_operation o ON o.id=i.operation_id
   WHERE i.table_name='patients' AND i.row_id=CAST(OLD.id AS CHAR)
     AND o.kind='patient' AND o.patient_id=OLD.id AND o.stage='agent_purged' AND o.state='running'
 ) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='scoped management required';
 END IF;
END$$
CREATE TRIGGER trg_patient_pii_no_delete BEFORE DELETE ON patient_pii FOR EACH ROW
BEGIN
 IF NOT EXISTS (
   SELECT 1 FROM data_management_item i JOIN data_management_operation o ON o.id=i.operation_id
   WHERE i.table_name='patient_pii' AND i.row_id=CAST(OLD.patient_id AS CHAR)
     AND o.kind='patient' AND o.patient_id=OLD.patient_id AND o.stage='agent_purged' AND o.state='running'
 ) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='scoped management required';
 END IF;
END$$
CREATE TRIGGER trg_patients_no_reuse AFTER INSERT ON patients FOR EACH ROW
BEGIN
 IF EXISTS (
   SELECT 1 FROM data_management_operation WHERE patient_id=NEW.id
     AND kind='patient' AND stage IN ('backend_purged', 'completed')
 ) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='patient identity retired';
 END IF;
END$$
DELIMITER ;

CREATE INDEX ix_management_item_identity ON data_management_item (table_name, row_id);
