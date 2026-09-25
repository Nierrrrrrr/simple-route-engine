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
