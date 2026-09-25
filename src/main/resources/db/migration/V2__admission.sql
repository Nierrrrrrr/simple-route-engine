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