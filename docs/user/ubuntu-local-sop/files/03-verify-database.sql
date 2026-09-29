SELECT VERSION() AS mariadb_version, DATABASE() AS current_database;
SHOW SESSION STATUS LIKE 'Ssl_cipher';
SELECT COUNT(*) AS engine_tables FROM information_schema.tables
 WHERE table_schema=DATABASE() AND table_type='BASE TABLE';
SELECT table_name,engine FROM information_schema.tables
 WHERE table_schema=DATABASE() AND table_type='BASE TABLE' AND engine<>'InnoDB';
SELECT id,total_slots,critical_reserved,high_weight,normal_weight,low_weight,
 wrr_cursor,config_version,admission_enabled FROM scheduler_pool;
SELECT trigger_name FROM information_schema.triggers
 WHERE trigger_schema=DATABASE() ORDER BY trigger_name;
-- Manual SQL mode: 12 engine tables, 11 triggers, one scheduler_pool row.
-- No flyway_schema_history table: startup explicitly disables Flyway.
