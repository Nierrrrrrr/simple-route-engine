-- DBA template: REPLACE every CHANGE_ME value before execution.
-- Use a new dedicated database on the existing MariaDB server.
-- This file contains DDL/DCL; no existing schema is dropped or overwritten.
CREATE DATABASE route_engine_sop CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
CREATE USER 're_sop_migrate'@'CHANGE_ME_UBUNTU_EGRESS_IP'
 IDENTIFIED BY 'CHANGE_ME_MIGRATION_PASSWORD' REQUIRE SSL;
CREATE USER 're_sop_app'@'CHANGE_ME_UBUNTU_EGRESS_IP'
 IDENTIFIED BY 'CHANGE_ME_APPLICATION_PASSWORD' REQUIRE SSL;
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES, TRIGGER
 ON route_engine_sop.* TO 're_sop_migrate'@'CHANGE_ME_UBUNTU_EGRESS_IP';
GRANT SELECT, INSERT, UPDATE, DELETE
 ON route_engine_sop.* TO 're_sop_app'@'CHANGE_ME_UBUNTU_EGRESS_IP';
-- No FLUSH PRIVILEGES is needed after CREATE USER / GRANT.
-- The migrations contain triggers: DBA must also check binary-log restrictions
-- and DEFINER policy. Keep the migration account as the trigger DEFINER.
