-- Fresh empty database only. Stop on the first SQL error. Do not use --force.
SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- BEGIN SOURCE V1__foundation.sql
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
-- END SOURCE V1__foundation.sql

-- BEGIN SOURCE V2__admission.sql
-- The pool lock serializes creation. AUTO_INCREMENT supplies FIFO even for equal DB timestamps.
ALTER TABLE admission_requests ADD COLUMN queue_sequence BIGINT NOT NULL AUTO_INCREMENT UNIQUE;
CREATE INDEX idx_admission_fifo ON admission_requests(decision,priority,queue_sequence);
CREATE TABLE pool_config_history (
 config_version BIGINT PRIMARY KEY,
 total_slots INT NOT NULL, critical_reserved INT NOT NULL,
 high_weight INT NOT NULL, normal_weight INT NOT NULL, low_weight INT NOT NULL,
 admission_enabled BOOLEAN NOT NULL,
 actor VARCHAR(128) NOT NULL, reason VARCHAR(500) NOT NULL, request_id VARCHAR(128) NOT NULL,
 created_at DATETIME(6) NOT NULL DEFAULT UTC_TIMESTAMP(6)
) ENGINE=InnoDB;
DELIMITER //
CREATE TRIGGER config_append_only_update BEFORE UPDATE ON pool_config_history FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Config history is append only'; END//
CREATE TRIGGER config_append_only_delete BEFORE DELETE ON pool_config_history FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Config history is append only'; END//
DELIMITER ;
-- END SOURCE V2__admission.sql

-- BEGIN SOURCE V3__engine.sql
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
-- END SOURCE V3__engine.sql

-- BEGIN SOURCE V4__incident_operation_identity.sql
-- V3 incidents did not record which attempt caused them. Preserve history without guessing.
ALTER TABLE step_attempts ADD UNIQUE KEY uq_attempt_identity
 (id,step_run_id,direction,operation_id,operation_generation,permit_generation);
ALTER TABLE engine_incidents
 DROP INDEX uq_engine_incident,
 ADD INDEX idx_incident_step(step_run_id),
 ADD attempt_id CHAR(36) COLLATE utf8mb4_bin NULL,
 ADD operation_id VARCHAR(200) COLLATE utf8mb4_bin NULL,
 ADD direction VARCHAR(16) NULL,
 ADD operation_generation BIGINT NULL,
 ADD permit_generation BIGINT NULL,
 ADD legacy_unbound BOOLEAN NOT NULL DEFAULT TRUE,
 ADD UNIQUE KEY uq_incident_attempt_kind(attempt_id,kind),
 ADD CONSTRAINT fk_incident_attempt_identity FOREIGN KEY
 (attempt_id,step_run_id,direction,operation_id,operation_generation,permit_generation)
 REFERENCES step_attempts(id,step_run_id,direction,operation_id,operation_generation,permit_generation),
 ADD CONSTRAINT ck_incident_identity CHECK(
  (legacy_unbound=TRUE AND attempt_id IS NULL AND operation_id IS NULL AND direction IS NULL
   AND operation_generation IS NULL AND permit_generation IS NULL) OR
  (legacy_unbound=FALSE AND attempt_id IS NOT NULL AND operation_id IS NOT NULL AND direction IS NOT NULL
   AND operation_generation IS NOT NULL AND permit_generation IS NOT NULL));
DELIMITER //
CREATE TRIGGER incident_identity_immutable BEFORE UPDATE ON engine_incidents FOR EACH ROW
BEGIN
 IF NOT (OLD.execution_id<=>NEW.execution_id) OR NOT (OLD.step_run_id<=>NEW.step_run_id)
 OR NOT (OLD.kind<=>NEW.kind) OR NOT (OLD.attempt_id<=>NEW.attempt_id)
 OR NOT (OLD.operation_id<=>NEW.operation_id) OR NOT (OLD.direction<=>NEW.direction)
 OR NOT (OLD.operation_generation<=>NEW.operation_generation)
 OR NOT (OLD.permit_generation<=>NEW.permit_generation) OR OLD.legacy_unbound<>NEW.legacy_unbound THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Incident identity is immutable';
 END IF;
END//
DELIMITER ;
-- END SOURCE V4__incident_operation_identity.sql

-- BEGIN SOURCE V5__adapter_plan_cancel.sql
ALTER TABLE step_attempts ADD adapter_plan JSON NULL;
ALTER TABLE executions ADD cancel_requested BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE adapter_stops (
 operation_id VARCHAR(128) COLLATE utf8mb4_bin PRIMARY KEY,
 resource_uid VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
 reason VARCHAR(16) NOT NULL,
 created_at DATETIME(6) NOT NULL DEFAULT UTC_TIMESTAMP(6),
 CHECK(reason IN ('CANCEL','FAILED'))
) ENGINE=InnoDB;
-- END SOURCE V5__adapter_plan_cancel.sql

-- BEGIN SOURCE V6__published_adapter_bindings.sql
-- The existing published-version triggers protect this column with the full immutable row.
-- Historical versions stay NULL: do not infer their external semantics from today's catalog.
ALTER TABLE route_versions ADD COLUMN adapter_bindings JSON NULL;
-- END SOURCE V6__published_adapter_bindings.sql

-- BEGIN SOURCE V7__recovery.sql
-- Historical intent/attempt/incident identities remain unchanged.
ALTER TABLE admission_requests
 ADD recovery_incident_id CHAR(36) COLLATE utf8mb4_bin NULL,
 ADD recovery_step_id CHAR(36) COLLATE utf8mb4_bin NULL,
 ADD recovery_payload JSON NULL,
 ADD FOREIGN KEY(recovery_incident_id) REFERENCES engine_incidents(id),
 ADD FOREIGN KEY(recovery_step_id) REFERENCES step_runs(id);
ALTER TABLE engine_incidents
 DROP CONSTRAINT CONSTRAINT_1,
 ADD CONSTRAINT ck_incident_kind CHECK(kind IN ('KNOWN_FAILURE','IN_DOUBT','COMPENSATED')),
 ADD pending_recovery_id CHAR(36) COLLATE utf8mb4_bin NULL,
 ADD FOREIGN KEY(pending_recovery_id) REFERENCES admission_requests(id);
ALTER TABLE step_runs
 ADD retry_base INT NOT NULL DEFAULT 0,
 ADD rollback_input_json JSON NULL,
 ADD rollback_allowed BOOLEAN NULL,
 ADD recovery_origin_id CHAR(36) COLLATE utf8mb4_bin NULL,
 ADD compensated BOOLEAN NOT NULL DEFAULT FALSE,
 ADD FOREIGN KEY(recovery_origin_id) REFERENCES step_runs(id);
ALTER TABLE executions ADD recovery_target_step_id CHAR(36) COLLATE utf8mb4_bin NULL,
 ADD FOREIGN KEY(recovery_target_step_id) REFERENCES step_runs(id);
CREATE TABLE operator_commands (
 id CHAR(36) COLLATE utf8mb4_bin PRIMARY KEY,
 execution_id CHAR(36) COLLATE utf8mb4_bin NOT NULL,
 principal VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
 operation_scope VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
 idempotency_key VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
 request_hash CHAR(64) NOT NULL,
 response_json JSON NOT NULL,
 created_at DATETIME(6) NOT NULL DEFAULT UTC_TIMESTAMP(6),
 UNIQUE KEY uq_operator_identity(principal,operation_scope,idempotency_key),
 FOREIGN KEY(execution_id) REFERENCES executions(id)
) ENGINE=InnoDB;
DELIMITER //
CREATE TRIGGER operator_command_immutable BEFORE UPDATE ON operator_commands FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Operator decision is immutable'; END//
CREATE TRIGGER operator_command_no_delete BEFORE DELETE ON operator_commands FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Operator decision is immutable'; END//
DELIMITER ;
-- END SOURCE V7__recovery.sql

-- BEGIN SOURCE V8__operations_indexes.sql
-- Additive only: preserves all published definitions, attempts and pending decisions.
CREATE INDEX ix_execution_operations ON executions(permit_held, updated_at);
CREATE INDEX ix_step_reconcile ON step_runs(state, lease_until);
-- END SOURCE V8__operations_indexes.sql
