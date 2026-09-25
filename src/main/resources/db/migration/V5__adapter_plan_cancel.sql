ALTER TABLE step_attempts ADD adapter_plan JSON NULL;
ALTER TABLE executions ADD cancel_requested BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE adapter_stops (
 operation_id VARCHAR(128) COLLATE utf8mb4_bin PRIMARY KEY,
 resource_uid VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
 reason VARCHAR(16) NOT NULL,
 created_at DATETIME(6) NOT NULL DEFAULT UTC_TIMESTAMP(6),
 CHECK(reason IN ('CANCEL','FAILED'))
) ENGINE=InnoDB;
