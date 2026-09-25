package dev.routeengine.audit;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.*;

@Component
public class AuditLog {
 private final JdbcTemplate db;
 public AuditLog(JdbcTemplate db){this.db=db;}
 @Transactional(propagation=Propagation.MANDATORY)
 public void append(String executionId,String routeId,Integer version,String type,String actor,String reason,String requestId){
  db.update("INSERT INTO execution_events(execution_id,route_id,route_version,event_type,actor,reason,request_id) VALUES(?,?,?,?,?,?,?)",executionId,routeId,version,type,actor,reason,requestId);
 }
}
