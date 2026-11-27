-- Existing ids and all collection references remain valid.
-- Verify the single-column UNIQUE index on devices(device_code) is named device_code.
ALTER TABLE devices
  DROP INDEX device_code,
  ADD UNIQUE KEY uq_devices_clinician_code (clinician_id, device_code);
