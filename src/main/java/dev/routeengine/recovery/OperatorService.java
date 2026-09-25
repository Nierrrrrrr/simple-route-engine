package dev.routeengine.recovery;

import com.fasterxml.jackson.databind.*;
import dev.routeengine.admission.AdmissionService;
import dev.routeengine.api.ApiProblem;
import dev.routeengine.audit.AuditLog;
import dev.routeengine.engine.EngineService;
import dev.routeengine.registry.DefinitionRules;
import jakarta.validation.constraints.*;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import static dev.routeengine.recovery.RecoveryPolicy.*;

@Service
public class OperatorService {
 public record Cancel(@NotBlank @Size(max=500) String reason){}
 public record Resolve(@NotBlank String stepId,@NotBlank String operationId,
  @NotNull @Pattern(regexp="SUCCEEDED|FAILED|STOPPED") String outcome,
  @NotBlank @Size(max=200) String reason,@NotBlank @Size(max=200) String evidence,JsonNode output){
  public Resolve {if(output!=null&&output.isNull())output=null;}
 }
 private final JdbcTemplate db;private final TransactionTemplate tx;private final ObjectMapper json;
 private final DefinitionRules rules;private final RecoveryPolicy policy;private final EngineService engine;private final AuditLog audit;private final OperatorPayloadGuard guard;
 public OperatorService(JdbcTemplate db,TransactionTemplate tx,ObjectMapper json,DefinitionRules rules,RecoveryPolicy policy,EngineService engine,AuditLog audit,OperatorPayloadGuard guard){this.guard=guard;
  this.db=db;this.tx=tx;this.json=json;this.rules=rules;this.policy=policy;this.engine=engine;this.audit=audit;
 }
 public JsonNode incidents(String id){return tx.execute(s->{
  db.queryForList("SELECT id FROM scheduler_pool WHERE id=1 FOR UPDATE");
  var executions=db.queryForList("SELECT * FROM executions WHERE id=? FOR UPDATE",id);if(executions.isEmpty())throw ApiProblem.missing();var e=executions.getFirst();
  policy.lockIncidents(id);var out=json.createObjectNode().put("executionId",id).put("state",(String)e.get("state"));var entries=out.putArray("incidents");
  for(var i:db.queryForList("SELECT * FROM engine_incidents WHERE execution_id=? AND status='OPEN' ORDER BY created_at,id",id)){
   var r=db.queryForMap("SELECT * FROM step_runs WHERE id=?",i.get("step_run_id"));var item=entries.addObject();
   item.put("incidentId",(String)i.get("id")).put("stepId",(String)i.get("step_run_id")).put("nodeId",(String)r.get("node_id")).put("kind",(String)i.get("kind"))
    .put("direction",(String)i.get("direction")).put("operationId",(String)i.get("operation_id")).put("attemptId",(String)i.get("attempt_id"))
    .put("pendingRecoveryId",(String)i.get("pending_recovery_id")).put("legacyUnbound",flag(i.get("legacy_unbound")));
   if(i.get("operation_generation") instanceof Number n)item.put("operationGeneration",n.longValue());
   if(i.get("permit_generation") instanceof Number n)item.put("permitGeneration",n.longValue());
   var actions=item.putArray("actions");
   if(!flag(i.get("legacy_unbound"))&&i.get("pending_recovery_id")==null){
    if(i.get("kind").equals("IN_DOUBT"))actions.add("RESOLVE");
    else if(e.get("state").equals("MANUAL_WAIT")){
     actions.add("CANCEL");
     if(!i.get("kind").equals("COMPENSATED")){
      actions.add("RETRY");
      if(r.get("direction").equals("FORWARD")&&r.get("state").equals("FAILED")){
       actions.add("SKIP");if(policy.parse(r.get("node_json")).has("rollback")&&r.get("rollback_input_json")!=null&&flag(r.get("rollback_allowed"))&&!flag(r.get("compensated")))actions.add("ROLLBACK");
      }
     }
    }
   }
  }
  return out;
 });}
 public JsonNode cancel(String id,String actor,String key,Cancel q,String requestId){
  return command(id,actor,key,"POST /executions/"+id+"/cancel",json.valueToTree(q),requestId,()->guard.prepare(id,null,null,null,json.valueToTree(q),actor,key,requestId),e->{
   String state=(String)e.get("state");
   if(Set.of("QUEUED","RECOVERY_QUEUED").contains(state)){
    db.queryForList("SELECT id FROM admission_requests WHERE execution_id=? AND decision='QUEUED' ORDER BY id FOR UPDATE",id);
    db.update("UPDATE admission_requests SET decision='WITHDRAWN',state_version=state_version+1 WHERE execution_id=? AND decision='QUEUED'",id);
    db.update("UPDATE engine_incidents SET pending_recovery_id=NULL WHERE execution_id=?",id);
    changed(db.update("UPDATE executions SET state=?,state_version=state_version+1,updated_at=UTC_TIMESTAMP(6) WHERE id=? AND state_version=?",state.equals("QUEUED")?"CANCELLED":"MANUAL_WAIT",id,e.get("state_version")));
    audit.append(id,(String)e.get("route_id"),((Number)e.get("route_version")).intValue(),"QUEUE_WITHDRAWN",actor,q.reason(),requestId);
   }else if(flag(e.get("permit_held")))engine.requestCancel(id,actor,q.reason());
   else throw ApiProblem.conflict();
   return json.createObjectNode().put("executionId",id).put("code",Set.of("QUEUED","RECOVERY_QUEUED").contains(state)?"QUEUE_WITHDRAWN":"CANCEL_REQUESTED");
  });
 }
 public JsonNode resolve(String id,String incident,String actor,String key,Resolve q,String requestId){
  return command(id,actor,key,"POST /executions/"+id+"/incidents/"+incident+"/resolve",json.valueToTree(q),requestId,()->guard.prepare(id,incident,q.stepId(),q.operationId(),json.valueToTree(q),actor,key,requestId),e->{
   if(q.output()!=null)policy.safeOutput(q.output());
   if(!q.outcome().equals("SUCCEEDED")&&q.output()!=null)throw ApiProblem.invalid();
   engine.confirm(id,incident,q.operationId(),q.stepId(),q.outcome(),q.output(),actor,q.reason()+" | evidence: "+q.evidence());
   return json.createObjectNode().put("executionId",id).put("incidentId",incident).put("operationId",q.operationId()).put("outcome",q.outcome()).put("code","OPERATION_RESOLVED");
  });
 }
 private JsonNode command(String id,String actor,String key,String scope,JsonNode body,String requestId,java.util.function.Supplier<OperatorPayloadGuard.Prepared> prepare,java.util.function.Function<Map<String,Object>,JsonNode> action){
  if(actor==null||actor.isBlank()||key==null||!key.matches("[A-Za-z0-9._:-]{1,128}")||rules.canonical(body).length()>262144)throw ApiProblem.invalid();
  String commandId=AdmissionService.identity(actor,scope,key),hash=rules.hash(body);
  var prepared=db.queryForList("SELECT id FROM operator_commands WHERE id=?",commandId).isEmpty()?prepare.get():null;
  return tx.execute(s->{
   db.queryForList("SELECT id FROM scheduler_pool WHERE id=1 FOR UPDATE");
   var rows=db.queryForList("SELECT * FROM executions WHERE id=? FOR UPDATE",id);if(rows.isEmpty())throw ApiProblem.missing();
   policy.lockIncidents(id);
   var previous=db.queryForList("SELECT * FROM operator_commands WHERE id=? FOR UPDATE",commandId);
   if(!previous.isEmpty()){
    if(!previous.getFirst().get("request_hash").equals(hash))throw new ApiProblem(409,"IDEMPOTENCY_CONFLICT","Idempotency key belongs to different request content");
    return policy.parse(previous.getFirst().get("response_json"));
   }
   guard.recheck(prepared,body,actor,key,requestId);
   var response=action.apply(rows.getFirst());
   changed(db.update("INSERT INTO operator_commands(id,execution_id,principal,operation_scope,idempotency_key,request_hash,response_json) VALUES(?,?,?,?,?,?,?)",commandId,id,actor,scope,key,hash,rules.canonical(response)));
   return response;
  });
 }
}
