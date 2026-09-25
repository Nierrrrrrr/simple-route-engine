CREATE TABLE routes (
 route_id VARCHAR(64) COLLATE utf8mb4_bin PRIMARY KEY,
 name VARCHAR(160) NOT NULL,
 enabled BOOLEAN NOT NULL DEFAULT TRUE,
 deleted_at DATETIME(6) NULL,
 max_version INT NOT NULL DEFAULT 0,
 latest_published_version INT NULL,
 state_version BIGINT NOT NULL DEFAULT 0,
 created_at DATETIME(6) NOT NULL DEFAULT UTC_TIMESTAMP(6),
 updated_at DATETIME(6) NOT NULL DEFAULT UTC_TIMESTAMP(6),
 CHECK(max_version >= 0), CHECK(state_version >= 0)
) ENGINE=InnoDB;

CREATE TABLE route_versions (
 route_id VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
 version INT NOT NULL,
 status VARCHAR(16) NOT NULL,
 definition_json JSON NOT NULL,
 definition_hash CHAR(64) NOT NULL,
 dsl_version VARCHAR(16) NOT NULL,
 engine_semantics_version VARCHAR(16) NOT NULL,
 adapter_contract_version VARCHAR(16) NOT NULL,
 state_version BIGINT NOT NULL DEFAULT 0,
 created_at DATETIME(6) NOT NULL DEFAULT UTC_TIMESTAMP(6),
 published_at DATETIME(6) NULL,
 PRIMARY KEY(route_id,version),
 FOREIGN KEY(route_id) REFERENCES routes(route_id),
 CHECK(version > 0), CHECK(state_version >= 0),
 CHECK(status IN ('DRAFT','PUBLISHED')),
 CHECK((status='PUBLISHED') = (published_at IS NOT NULL))
) ENGINE=InnoDB;
ALTER TABLE routes ADD CONSTRAINT fk_route_default_version FOREIGN KEY(route_id,latest_published_version) REFERENCES route_versions(route_id,version);

CREATE TABLE scheduler_pool (
 id INT PRIMARY KEY,
 total_slots INT NOT NULL DEFAULT 100,
 critical_reserved INT NOT NULL DEFAULT 20,
 high_weight INT NOT NULL DEFAULT 6,
 normal_weight INT NOT NULL DEFAULT 3,
 low_weight INT NOT NULL DEFAULT 1,
 wrr_cursor INT NOT NULL DEFAULT 0,
 config_version BIGINT NOT NULL DEFAULT 0,
 admission_enabled BOOLEAN NOT NULL DEFAULT TRUE,
 CHECK(id=1), CHECK(total_slots>0), CHECK(critical_reserved>=0 AND critical_reserved<=total_slots),
 CHECK(high_weight>0 AND normal_weight>0 AND low_weight>0), CHECK(wrr_cursor>=0)
) ENGINE=InnoDB;
INSERT INTO scheduler_pool(id) VALUES(1);

CREATE TABLE executions (
 id CHAR(36) COLLATE utf8mb4_bin PRIMARY KEY,
 route_id VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
 route_version INT NOT NULL,
 priority VARCHAR(16) NOT NULL,
 state VARCHAR(24) NOT NULL,
 state_version BIGINT NOT NULL DEFAULT 0,
 permit_held BOOLEAN NOT NULL DEFAULT FALSE,
 permit_generation BIGINT NOT NULL DEFAULT 0,
 lease_owner VARCHAR(128) NULL,
 lease_generation BIGINT NOT NULL DEFAULT 0,
 lease_until DATETIME(6) NULL,
 next_action_at DATETIME(6) NULL,
 input_json JSON NOT NULL DEFAULT '{}',
 created_at DATETIME(6) NOT NULL DEFAULT UTC_TIMESTAMP(6),
 updated_at DATETIME(6) NOT NULL DEFAULT UTC_TIMESTAMP(6),
 FOREIGN KEY(route_id,route_version) REFERENCES route_versions(route_id,version),
 CHECK(priority IN ('CRITICAL','HIGH','NORMAL','LOW')),
 CHECK(state IN ('QUEUED','ADMITTED','RUNNING','WAITING_EXTERNAL','RETRY_WAIT','PAUSING','RECONCILING','CANCELING','MANUAL_WAIT','RECOVERY_QUEUED','RECOVERING','ROLLING_BACK','SUCCEEDED','FAILED','CANCELLED')),
 CHECK(state_version>=0 AND permit_generation>=0 AND lease_generation>=0),
 CHECK(state NOT IN ('QUEUED','MANUAL_WAIT','RECOVERY_QUEUED','SUCCEEDED','FAILED','CANCELLED') OR permit_held=FALSE),
 INDEX idx_execution_due(state,next_action_at), INDEX idx_execution_permit(permit_held,priority)
) ENGINE=InnoDB;

CREATE TABLE admission_requests (
 id CHAR(36) COLLATE utf8mb4_bin PRIMARY KEY,
 principal VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
 operation_scope VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
 idempotency_key VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
 request_hash CHAR(64) NOT NULL,
 execution_id CHAR(36) COLLATE utf8mb4_bin NULL,
 decision VARCHAR(24) NOT NULL,
 priority VARCHAR(16) NOT NULL,
 admission_mode VARCHAR(24) NOT NULL,
 enqueued_at DATETIME(6) NOT NULL DEFAULT UTC_TIMESTAMP(6),
 response_json JSON NULL,
 state_version BIGINT NOT NULL DEFAULT 0,
 UNIQUE KEY uq_admission_identity(principal,operation_scope,idempotency_key),
 FOREIGN KEY(execution_id) REFERENCES executions(id),
 CHECK(decision IN ('QUEUED','ADMITTED','REJECTED','WITHDRAWN')),
 CHECK(priority IN ('CRITICAL','HIGH','NORMAL','LOW')),
 CHECK(admission_mode IN ('QUEUE','NOW_OR_REJECT')),
 INDEX idx_admission_queue(decision,priority,enqueued_at,id)
) ENGINE=InnoDB;

CREATE TABLE step_runs (
 id CHAR(36) COLLATE utf8mb4_bin PRIMARY KEY,
 execution_id CHAR(36) COLLATE utf8mb4_bin NOT NULL,
 node_id VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
 state VARCHAR(24) NOT NULL,
 state_version BIGINT NOT NULL DEFAULT 0,
 direction VARCHAR(16) NOT NULL DEFAULT 'FORWARD',
 input_json JSON NULL, output_json JSON NULL, branch_choice VARCHAR(128) NULL,
 next_action_at DATETIME(6) NULL,
 lease_owner VARCHAR(128) NULL, lease_generation BIGINT NOT NULL DEFAULT 0, lease_until DATETIME(6) NULL,
 UNIQUE KEY uq_execution_node(execution_id,node_id),
 FOREIGN KEY(execution_id) REFERENCES executions(id),
 CHECK(direction IN ('FORWARD','ROLLBACK'))
) ENGINE=InnoDB;

CREATE TABLE step_attempts (
 id CHAR(36) COLLATE utf8mb4_bin PRIMARY KEY,
 step_run_id CHAR(36) COLLATE utf8mb4_bin NOT NULL,
 attempt_number INT NOT NULL,
 direction VARCHAR(16) NOT NULL,
 state VARCHAR(24) NOT NULL,
 permit_generation BIGINT NOT NULL,
 lease_generation BIGINT NOT NULL,
 operation_generation BIGINT NOT NULL,
 operation_id VARCHAR(200) COLLATE utf8mb4_bin NOT NULL,
 external_uid VARCHAR(200) NULL,
 started_at DATETIME(6) NOT NULL DEFAULT UTC_TIMESTAMP(6),
 finished_at DATETIME(6) NULL,
 UNIQUE KEY uq_step_attempt(step_run_id,direction,attempt_number),
 UNIQUE KEY uq_operation(operation_id),
 FOREIGN KEY(step_run_id) REFERENCES step_runs(id),
 CHECK(direction IN ('FORWARD','ROLLBACK')),
 CHECK(attempt_number>0 AND operation_generation>0)
) ENGINE=InnoDB;

CREATE TABLE execution_events (
 id BIGINT AUTO_INCREMENT PRIMARY KEY,
 execution_id CHAR(36) COLLATE utf8mb4_bin NULL,
 route_id VARCHAR(64) COLLATE utf8mb4_bin NULL,
 route_version INT NULL,
 event_type VARCHAR(64) NOT NULL,
 actor VARCHAR(128) NOT NULL,
 reason VARCHAR(500) NOT NULL,
 request_id VARCHAR(128) NOT NULL,
 created_at DATETIME(6) NOT NULL DEFAULT UTC_TIMESTAMP(6),
 FOREIGN KEY(execution_id) REFERENCES executions(id),
 FOREIGN KEY(route_id) REFERENCES routes(route_id),
 INDEX idx_event_execution(execution_id,id), INDEX idx_event_route(route_id,id)
) ENGINE=InnoDB;

DELIMITER //
CREATE TRIGGER route_version_immutable_update BEFORE UPDATE ON route_versions FOR EACH ROW
BEGIN
 IF OLD.status='PUBLISHED' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Published version is immutable'; END IF;
END//
CREATE TRIGGER route_version_immutable_delete BEFORE DELETE ON route_versions FOR EACH ROW
BEGIN
 IF OLD.status='PUBLISHED' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Published version is immutable'; END IF;
END//
CREATE TRIGGER execution_published_version BEFORE INSERT ON executions FOR EACH ROW
BEGIN
 IF NOT EXISTS (SELECT 1 FROM route_versions WHERE route_id=NEW.route_id AND version=NEW.route_version AND status='PUBLISHED') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Execution requires published version';
 END IF;
END//
CREATE TRIGGER execution_identity_immutable BEFORE UPDATE ON executions FOR EACH ROW
BEGIN
 IF OLD.route_id<>NEW.route_id OR OLD.route_version<>NEW.route_version OR OLD.priority<>NEW.priority THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Execution binding and priority are immutable';
 END IF;
END//
CREATE TRIGGER event_append_only_update BEFORE UPDATE ON execution_events FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Audit is append only'; END//
CREATE TRIGGER event_append_only_delete BEFORE DELETE ON execution_events FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Audit is append only'; END//
DELIMITER ;
