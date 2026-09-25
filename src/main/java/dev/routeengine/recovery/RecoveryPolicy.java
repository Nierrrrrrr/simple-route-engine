package dev.routeengine.recovery;

import com.fasterxml.jackson.databind.*;
import dev.routeengine.api.ApiProblem;
import dev.routeengine.audit.AuditLog;
import dev.routeengine.registry.DefinitionRules;
import jakarta.validation.constraints.*;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** Transaction-local recovery policy. Caller holds pool -> execution -> all incidents/admissions before steps. */
@Component
public class RecoveryPolicy {
 public record Request(@NotBlank String incidentId,@NotBlank String stepId,
  @NotNull @Pattern(regexp="RETRY|SKIP|ROLLBACK|CANCEL") String action,
  @NotNull @Pattern(regexp="QUEUE|NOW_OR_REJECT") String admissionMode,
  @NotBlank @Size(max=500) String reason,JsonNode replacementOutput){
  public Request {if(replacementOutput!=null&&replacementOutput.isNull())replacementOutput=null;}
 }
 private final JdbcTemplate db;private final DefinitionRules rules;private final ObjectMapper json;private final AuditLog audit;private final dev.routeengine.adapters.AdapterCatalog catalog;
 public RecoveryPolicy(JdbcTemplate db,DefinitionRules rules,ObjectMapper json,AuditLog audit,dev.routeengine.adapters.AdapterCatalog catalog){this.catalog=catalog;this.db=db;this.rules=rules;this.json=json;this.audit=audit;}
 public JsonNode parse(Object value){try{return value==null?json.createObjectNode():json.readTree(value.toString());}catch(Exception error){throw new IllegalStateException("Invalid persisted recovery payload");}}
 public Request request(Object value){try{return json.treeToValue(parse(value),Request.class);}catch(Exception error){throw new IllegalStateException("Invalid persisted recovery request");}}
 public static boolean flag(Object value){return Boolean.TRUE.equals(value)||value instanceof Number n&&n.intValue()==1;}
 public static void changed(int n){if(n!=1)throw ApiProblem.conflict();}
 public void lockIncidents(String id){db.queryForList("SELECT id FROM engine_incidents WHERE execution_id=? ORDER BY id FOR UPDATE",id);}
 public Map<String,Object> validate(Map<String,Object> e,Request q,String queuedRequest){
  if(flag(e.get("permit_held"))||!e.get("state").equals(queuedRequest==null?"MANUAL_WAIT":"RECOVERY_QUEUED"))throw ApiProblem.conflict();
  var incidents=db.queryForList("SELECT * FROM engine_incidents WHERE id=? AND execution_id=?",q.incidentId(),e.get("id"));
  if(incidents.isEmpty())throw ApiProblem.conflict();var i=incidents.getFirst();
  if(!i.get("status").equals("OPEN")||flag(i.get("legacy_unbound"))||!q.stepId().equals(i.get("step_run_id"))||
    !Objects.equals(queuedRequest,i.get("pending_recovery_id"))||i.get("kind").equals("IN_DOUBT"))throw ApiProblem.conflict();
  var r=db.queryForMap("SELECT * FROM step_runs WHERE id=? AND execution_id=?",q.stepId(),e.get("id"));
  if(!Set.of("FAILED","STOPPED","SUCCEEDED").contains(r.get("state"))||
    !r.get("operation_generation").equals(i.get("operation_generation"))||!r.get("direction").equals(i.get("direction")))throw ApiProblem.conflict();
  if(i.get("kind").equals("COMPENSATED")&&!q.action().equals("CANCEL"))throw ApiProblem.invalid();
  if(q.replacementOutput()!=null&&!q.action().equals("SKIP"))throw ApiProblem.invalid();
  var node=parse(r.get("node_json"));
  switch(q.action()){
   case "CANCEL" -> {}
   case "RETRY" -> {if(!Set.of("FAILED","STOPPED").contains(r.get("state")))throw ApiProblem.invalid();}
   case "SKIP" -> {
    if(!r.get("direction").equals("FORWARD")||!r.get("state").equals("FAILED"))throw ApiProblem.invalid();
    var out=q.replacementOutput()==null?json.createObjectNode():q.replacementOutput();
    safeOutput(out);rules.validateValue(node.path("outputSchema"),out);
   }
   case "ROLLBACK" -> {
    if(!r.get("direction").equals("FORWARD")||!r.get("state").equals("FAILED")||flag(r.get("compensated"))||
      !node.path("rollback").isObject()||r.get("rollback_input_json")==null||!flag(r.get("rollback_allowed")))throw ApiProblem.invalid();
    // The only legal target is the exact current failed operation, never a successful/consumed prior step.
   }
   default -> throw ApiProblem.invalid();
  }
  return r;
 }
 public void safeOutput(JsonNode output){
  if(output==null||output.isNull()||rules.canonical(output).length()>262144)throw ApiProblem.invalid();
  try{catalog.safeOutput(output,"");}catch(IllegalArgumentException unsafe){throw ApiProblem.invalid();}
 }
 private void reopen(Map<String,Object> r,String execution){
  Object parent=r.get("parent_node_id");
  while(parent!=null){
   var p=db.queryForMap("SELECT * FROM step_runs WHERE execution_id=? AND node_id=?",execution,parent);
   changed(db.update("UPDATE step_runs SET state='RUNNING',output_json=NULL,state_version=state_version+1 WHERE id=? AND state_version=?",p.get("id"),p.get("state_version")));
   parent=p.get("parent_node_id");
  }
 }
 public void apply(Map<String,Object> e,Request q,String admissionId){
  // The incident is consumed in the same commit as acquisition; its operation identity is never rewritten.
  var r=db.queryForMap("SELECT * FROM step_runs WHERE id=? FOR UPDATE",q.stepId());var node=parse(r.get("node_json"));
  String target=null;
  switch(q.action()){
   case "CANCEL" -> changed(db.update("UPDATE executions SET cancel_requested=TRUE WHERE id=?",e.get("id")));
   case "SKIP" -> {
    changed(db.update("UPDATE step_runs SET state='SKIPPED',output_json=?,state_version=state_version+1 WHERE id=? AND state_version=?",rules.canonical(q.replacementOutput()==null?json.createObjectNode():q.replacementOutput()),r.get("id"),r.get("state_version")));
    reopen(r,(String)e.get("id"));
   }
   case "RETRY" -> {
    changed(db.update("UPDATE step_runs SET state='PENDING',retry_base=attempt_count,first_attempt_at=NULL,next_action_at=NULL,lease_owner=NULL,lease_until=NULL,state_version=state_version+1 WHERE id=? AND state_version=?",r.get("id"),r.get("state_version")));
    target=(String)r.get("id");if(r.get("direction").equals("FORWARD"))reopen(r,(String)e.get("id"));
   }
   case "ROLLBACK" -> {
    var n=node.get("rollback");var retry=n.path("retry");target=UUID.randomUUID().toString();
    changed(db.update("INSERT INTO step_runs(id,execution_id,node_id,state,direction,node_json,input_json,ordinal_number,max_attempts,max_elapsed_seconds,backoff_seconds,max_backoff_seconds,recovery_origin_id) VALUES(?,?,?,'PENDING','ROLLBACK',?,?,?,?,?,?,?,?)",
     target,e.get("id"),n.path("id").asText(),rules.canonical(n),r.get("rollback_input_json"),
     db.queryForObject("SELECT COUNT(*) FROM step_runs WHERE execution_id=?",Integer.class,e.get("id")),
     retry.path("maxAttempts").asInt(1),retry.path("maxElapsedSeconds").asInt(21600),retry.path("backoffSeconds").asInt(1),retry.path("maxBackoffSeconds").asInt(Math.max(60,retry.path("backoffSeconds").asInt(1))),r.get("id")));
   }
  }
  changed(db.update("UPDATE engine_incidents SET status='RESOLVED',pending_recovery_id=NULL WHERE id=? AND status='OPEN'",q.incidentId()));
  changed(db.update("UPDATE executions SET recovery_target_step_id=? WHERE id=?",target,e.get("id")));
  audit.append((String)e.get("id"),(String)e.get("route_id"),((Number)e.get("route_version")).intValue(),"RECOVERY_APPLIED","scheduler","request="+admissionId+" action="+q.action()+" incident="+q.incidentId(),admissionId);
 }
 public boolean rollback(Request q,Map<String,Object> r){return q.action().equals("ROLLBACK")||q.action().equals("RETRY")&&r.get("direction").equals("ROLLBACK");}
}
