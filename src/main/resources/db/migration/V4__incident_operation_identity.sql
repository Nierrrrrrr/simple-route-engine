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
