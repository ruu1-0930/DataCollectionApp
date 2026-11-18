-- Append an enum member so existing MySQL enum ordinals remain unchanged.
-- Frozen capture provenance, frame membership and stop evidence live in the
-- revision's immutable closure_evidence_canonical; historical rows need no update.
ALTER TABLE gait_session_revision
    MODIFY state ENUM('collecting','closed_by_inactivity','superseded','closed_by_capture_stop') NOT NULL;
