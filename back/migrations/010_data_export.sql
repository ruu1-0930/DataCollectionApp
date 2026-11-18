CREATE TABLE data_export_inventory (
    id VARCHAR(36) PRIMARY KEY,
    actor_id INT NOT NULL,
    patient_id INT NOT NULL,
    request_json TEXT NOT NULL,
    inventory_json MEDIUMTEXT NOT NULL,
    scope_hash CHAR(64) NOT NULL,
    state VARCHAR(16) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    lease_until DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    INDEX ix_export_patient (patient_id),
    INDEX ix_export_expiry (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE data_export_grant (
    token_hash CHAR(64) PRIMARY KEY,
    export_id VARCHAR(36) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    INDEX ix_export_grant (export_id),
    FOREIGN KEY (export_id) REFERENCES data_export_inventory(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
