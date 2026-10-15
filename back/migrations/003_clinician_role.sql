-- Forward-only; apply once after confirming the target database and a backup.
-- Existing identities remain ordinary clinicians. No account is elevated here.
ALTER TABLE `clinicians` ADD COLUMN `role` ENUM('clinician','admin_readonly')
  NOT NULL DEFAULT 'clinician';
