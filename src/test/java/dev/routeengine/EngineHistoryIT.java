package dev.routeengine;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

/** Runs before EngineIT (alphabetical failsafe order) on its dedicated fresh MariaDB. */
class EngineHistoryIT {
 @Test void AC030_legacyIncidentMigrationPreservesHistoryWithoutGuessingAttempt(){
  String url=Objects.requireNonNull(System.getenv("ROUTE_ENGINE_TEST_DB_URL"),"Missing dedicated engine test database URL");
  String user=Objects.requireNonNull(System.getenv("ROUTE_ENGINE_TEST_DB_USER"),"Missing dedicated engine test database USER");
  String password=Objects.requireNonNull(System.getenv("ROUTE_ENGINE_TEST_DB_PASSWORD"),"Missing dedicated engine test database PASSWORD");
  var db=new JdbcTemplate(new DriverManagerDataSource(url,user,password));
  assertEquals(0,db.queryForObject("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()",Integer.class),"Engine history migration requires a fresh isolated database");
  Flyway.configure().dataSource(url,user,password).target("3").load().migrate();
  String execution=UUID.randomUUID().toString(),step=UUID.randomUUID().toString(),other=UUID.randomUUID().toString();
  String open=UUID.randomUUID().toString(),resolved=UUID.randomUUID().toString();
  db.update("INSERT INTO routes(route_id,name) VALUES('demo-history','DEMO historical migration')");
  db.update("INSERT INTO route_versions(route_id,version,status,definition_json,definition_hash,dsl_version,engine_semantics_version,adapter_contract_version,published_at) VALUES('demo-history',1,'PUBLISHED','{}',?,'1','1','1',UTC_TIMESTAMP(6))","0".repeat(64));
  db.update("INSERT INTO executions(id,route_id,route_version,priority,state) VALUES(?,'demo-history',1,'CRITICAL','SUCCEEDED')",execution);
  db.update("INSERT INTO step_runs(id,execution_id,node_id,state) VALUES(?,?,'work','SUCCEEDED'),(?,?,'other','SUCCEEDED')",step,execution,other,execution);
  for(int n=1;n<=2;n++)db.update("INSERT INTO step_attempts(id,step_run_id,attempt_number,direction,state,permit_generation,lease_generation,operation_generation,operation_id) VALUES(?,?,?,'FORWARD','FAILED',1,?,?,?)",UUID.randomUUID().toString(),step,n,n,n,UUID.randomUUID().toString());
  db.update("INSERT INTO engine_incidents(id,execution_id,step_run_id,kind,status) VALUES(?,?,?,'IN_DOUBT','OPEN'),(?,?,?,'IN_DOUBT','RESOLVED')",open,execution,step,resolved,execution,other);
  db.update("INSERT INTO execution_events(execution_id,event_type,actor,reason,request_id) VALUES(?,'LEGACY_PROBE','test','historical audit must remain','migration-test')",execution);
  var before=db.queryForList("SELECT id,execution_id,step_run_id,kind,status,created_at FROM engine_incidents ORDER BY id");
  var audit=db.queryForList("SELECT * FROM execution_events WHERE execution_id=?",execution);
  Flyway.configure().dataSource(url,user,password).load().migrate();
  assertEquals(List.of("1","2","3","4","5","6","7","8"),db.queryForList("SELECT version FROM flyway_schema_history WHERE success=1 ORDER BY installed_rank",String.class));
  assertEquals(0,db.queryForObject("SELECT COUNT(*) FROM route_versions WHERE adapter_bindings IS NOT NULL",Integer.class),"Historical publication bindings must never be invented");
  assertEquals(0,db.queryForObject("SELECT COUNT(*) FROM step_attempts WHERE adapter_plan IS NOT NULL",Integer.class),"Historical adapter plans must not be invented");
  assertEquals(0,db.queryForObject("SELECT COUNT(*) FROM executions WHERE cancel_requested=TRUE",Integer.class));
  assertEquals(0,db.queryForObject("SELECT COUNT(*) FROM step_runs WHERE rollback_input_json IS NOT NULL OR rollback_allowed IS NOT NULL OR recovery_origin_id IS NOT NULL OR retry_base<>0 OR compensated=TRUE",Integer.class),"Historical recovery context must not be invented");
  assertEquals(0,db.queryForObject("SELECT COUNT(*) FROM executions WHERE recovery_target_step_id IS NOT NULL",Integer.class));
  assertEquals(before,db.queryForList("SELECT id,execution_id,step_run_id,kind,status,created_at FROM engine_incidents ORDER BY id"));
  assertEquals(audit,db.queryForList("SELECT * FROM execution_events WHERE execution_id=?",execution));
  assertEquals(2,db.queryForObject("SELECT COUNT(*) FROM engine_incidents WHERE legacy_unbound=TRUE AND attempt_id IS NULL AND operation_id IS NULL AND direction IS NULL AND operation_generation IS NULL AND permit_generation IS NULL",Integer.class));
  assertThrows(org.springframework.dao.DataAccessException.class,()->db.update("UPDATE engine_incidents SET legacy_unbound=FALSE WHERE id=?",open));
 }
}
