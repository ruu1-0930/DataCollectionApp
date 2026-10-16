-- Maintenance window: stop B and the workbench before changing role semantics.
-- Inspect existing account IDs; this step grants no account new permissions.
ALTER TABLE `clinicians` MODIFY COLUMN `role`
  ENUM('clinician','admin_readonly','admin') NOT NULL DEFAULT 'clinician';
