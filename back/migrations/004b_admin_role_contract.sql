-- Execute only after explicitly migrating approved account IDs while B is stopped.
-- Verify COUNT(*) WHERE role='admin_readonly' is zero before this statement.
-- Start only the new role-aware B after contraction; do not roll back to old B.
ALTER TABLE `clinicians` MODIFY COLUMN `role`
  ENUM('clinician','admin') NOT NULL DEFAULT 'clinician';
