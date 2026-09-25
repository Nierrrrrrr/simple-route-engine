ALTER TABLE step_runs
 ADD node_json JSON NULL,
 ADD parent_node_id VARCHAR(128) COLLATE utf8mb4_bin NULL,
 ADD ordinal_number INT NOT NULL DEFAULT 0,
 ADD is_notification BOOLEAN NOT NULL DEFAULT FALSE,
 ADD attempt_count INT NOT NULL DEFAULT 0,
 ADD max_attempts INT NOT NULL DEFAULT 1,
 ADD max_elapsed_seconds INT NOT NULL DEFAULT 21600,
 ADD backoff_seconds INT NOT NULL DEFAULT 1,
 ADD max_backoff_seconds INT NOT NULL DEFAULT 60,
 ADD first_attempt_at DATETIME(6) NULL,
 ADD operation_generation BIGINT NOT NULL DEFAULT 0,
 ADD CONSTRAINT ck_retry_budget CHECK(attempt_count>=0 AND max_attempts BETWEEN 1 AND 100 AND max_elapsed_seconds BETWEEN 1 AND 604800),
 ADD INDEX idx_step_due(execution_id,state,next_action_at,lease_until);
CREATE TABLE engine_incidents (
 id CHAR(36) COLLATE utf8mb4_bin PRIMARY KEY,
 execution_id CHAR(36) COLLATE utf8mb4_bin NOT NULL,
 step_run_id CHAR(36) COLLATE utf8mb4_bin NOT NULL,
 kind VARCHAR(24) NOT NULL,
 status VARCHAR(16) NOT NULL DEFAULT 'OPEN',
 created_at DATETIME(6) NOT NULL DEFAULT UTC_TIMESTAMP(6),
 UNIQUE KEY uq_engine_incident(step_run_id,kind),
 FOREIGN KEY(execution_id) REFERENCES executions(id),
 FOREIGN KEY(step_run_id) REFERENCES step_runs(id),
 CHECK(kind IN ('KNOWN_FAILURE','IN_DOUBT')), CHECK(status IN ('OPEN','RESOLVED'))
) ENGINE=InnoDB;