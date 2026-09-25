package dev.routeengine.admission;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import dev.routeengine.api.ApiProblem;
import dev.routeengine.audit.AuditLog;
import dev.routeengine.registry.*;
import dev.routeengine.recovery.RecoveryPolicy;
import dev.routeengine.recovery.OperatorPayloadGuard;
import jakarta.validation.constraints.*;
import java.nio.charset.StandardCharsets;
import java.sql.*;
import java.time.*;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

/** All permit/config/queue mutations serialize on the database pool row, never JVM locks. */
@Service
public class AdmissionService {
 public static final String SCOPE="POST /executions";
 public record Request(@NotBlank @Pattern(regexp="[a-z][a-z0-9-]{0,63}") String routeId,
   @Min(1) Integer routeVersion,@NotNull @Pattern(regexp="CRITICAL|HIGH|NORMAL|LOW") String priority,
   @NotNull @Pattern(regexp="QUEUE|NOW_OR_REJECT") String admissionMode,@NotNull JsonNode input){}
 public record Config(@NotNull @Min(1) @Max(100000) Integer totalSlots,@NotNull @Min(0) Integer criticalReserved,
   @NotNull @Min(1) @Max(100) Integer highWeight,@NotNull @Min(1) @Max(100) Integer normalWeight,
   @NotNull @Min(1) @Max(100) Integer lowWeight,@NotNull Boolean admissionEnabled,
   @NotNull @Min(0) Long configVersion,@NotBlank @Size(max=500) String reason){}
 private record Pool(int total,int reserved,int high,int normal,int low,int cursor,long version,boolean enabled){}
 private record Head(String requestId,String executionId,String priority){}
 private record Choice(Head head,int nextCursor){}
 public record Result(int status,JsonNode body){}
 private final JdbcTemplate db;private final TransactionTemplate tx;private final AuditLog audit;
 private final RecoveryPolicy recovery;private final OperatorPayloadGuard guard;
 private final RouteRegistry routes;private final DefinitionRules canonical;private final ObjectMapper json;
 public AdmissionService(JdbcTemplate db,TransactionTemplate tx,AuditLog audit,RouteRegistry routes,DefinitionRules canonical,ObjectMapper json,RecoveryPolicy recovery,OperatorPayloadGuard guard){this.guard=guard;this.recovery=recovery;this.db=db;this.tx=tx;this.audit=audit;this.routes=routes;this.canonical=canonical;this.json=json;}
 public static String identity(String actor,String key){return identity(actor,SCOPE,key);}
 public static String identity(String actor,String scope,String key){return UUID.nameUUIDFromBytes((actor+"\0"+scope+"\0"+key).getBytes(StandardCharsets.UTF_8)).toString();}
 public static String recoveryScope(String execution){return "POST /executions/"+execution+"/recoveries";}
 private Pool lockPool(){return readPool(true);}
 private Pool readPool(boolean lock){return db.queryForObject("SELECT * FROM scheduler_pool WHERE id=1"+(lock?" FOR UPDATE":""),(r,n)->new Pool(r.getInt("total_slots"),r.getInt("critical_reserved"),r.getInt("high_weight"),r.getInt("normal_weight"),r.getInt("low_weight"),r.getInt("wrr_cursor"),r.getLong("config_version"),r.getBoolean("admission_enabled")));}
 private long count(String where){return db.queryForObject("SELECT COUNT(*) FROM executions WHERE "+where,Long.class);}
 private Instant now(){return db.queryForObject("SELECT UTC_TIMESTAMP(6)",LocalDateTime.class).toInstant(ZoneOffset.UTC);}
 private JsonNode parse(String value){try{return json.readTree(value);}catch(Exception e){throw new IllegalStateException("Invalid persisted admission response",e);}}
 private void changed(int n){if(n!=1)throw ApiProblem.conflict();}
 private List<String> cycle(Pool p){var result=new ArrayList<String>();for(int i=0;i<p.high;i++)result.add("HIGH");for(int i=0;i<p.normal;i++)result.add("NORMAL");for(int i=0;i<p.low;i++)result.add("LOW");return result;}
 private Head head(String priority){var rows=db.query("SELECT id,execution_id,priority FROM admission_requests WHERE decision='QUEUED' AND priority=? ORDER BY queue_sequence LIMIT 1",(r,n)->new Head(r.getString(1),r.getString(2),r.getString(3)),priority);return rows.isEmpty()?null:rows.getFirst();}
 /** A NOW candidate participates behind every existing same-class request, without creating a latent row. */
 private Choice choose(Pool p,Head candidate){
  if(!p.enabled||count("permit_held=TRUE")>=p.total)return null;
  var critical=head("CRITICAL");if(critical==null&&candidate!=null&&candidate.priority.equals("CRITICAL"))critical=candidate;
  if(critical!=null)return new Choice(critical,p.cursor);
  if(count("permit_held=TRUE AND priority<>'CRITICAL'")>=p.total-p.reserved)return null;
  var sequence=cycle(p);
  for(int offset=0;offset<sequence.size();offset++){
   int at=(p.cursor+offset)%sequence.size();String priority=sequence.get(at);var h=head(priority);
   if(h==null&&candidate!=null&&candidate.priority.equals(priority))h=candidate;
   if(h!=null)return new Choice(h,(at+1)%sequence.size());
  }
  return null;
 }
 public Result submit(String actor,String key,Request request,String requestId){
  if(key==null||!key.matches("[A-Za-z0-9._:-]{1,128}")||request.input()==null||!request.input().isObject())throw ApiProblem.invalid();
  String serialized=canonical.canonical(json.valueToTree(request));if(serialized.getBytes(StandardCharsets.UTF_8).length>262144)throw ApiProblem.invalid();
  String hash=canonical.hash(json.valueToTree(request));String id=identity(actor,key);
  return tx.execute(s->{
   Pool pool=lockPool();
   var replay=db.queryForList("SELECT request_hash,response_json FROM admission_requests WHERE principal=? AND operation_scope=? AND idempotency_key=?",actor,SCOPE,key);
   if(!replay.isEmpty()){
    if(!hash.equals(replay.getFirst().get("request_hash")))throw new ApiProblem(409,"IDEMPOTENCY_CONFLICT","Idempotency key belongs to different request content");
    var original=parse((String)replay.getFirst().get("response_json"));return new Result(original.path("decision").asText().equals("REJECTED")?409:202,original);
   }
   // Registry mutation only locks route and never subsequently takes pool: pool -> route is acyclic.
   var version=routes.lockForNewExecution(request.routeId(),request.routeVersion());
   canonical.validateValue(version.definition().path("inputSchema"),request.input());
   String execution=UUID.randomUUID().toString();boolean queue=request.admissionMode().equals("QUEUE");
   Choice chosen=queue?null:choose(pool,new Head(id,execution,request.priority()));
   boolean admitted=chosen!=null&&chosen.head.requestId.equals(id);
   String decision=queue?"QUEUED":admitted?"ADMITTED":"REJECTED";
   if(queue||admitted){
    changed(db.update("INSERT INTO executions(id,route_id,route_version,priority,state,permit_held,permit_generation,input_json) VALUES(?,?,?,?,?,?,?,?)",execution,request.routeId(),version.version(),request.priority(),decision,admitted,admitted?1:0,canonical.canonical(request.input())));
   }else execution=null;
   ObjectNode response=json.createObjectNode();response.put("admissionRequestId",id).put("decision",decision).put("code",decision.equals("REJECTED")?"ADMISSION_REJECTED":"ADMISSION_"+decision).put("executionId",execution).put("routeId",request.routeId()).put("routeVersion",version.version()).put("priority",request.priority()).put("configVersion",pool.version).put("decidedAt",now().toString());
   changed(db.update("INSERT INTO admission_requests(id,principal,operation_scope,idempotency_key,request_hash,execution_id,decision,priority,admission_mode,response_json) VALUES(?,?,?,?,?,?,?,?,?,?)",id,actor,SCOPE,key,hash,execution,decision,request.priority(),request.admissionMode(),response.toString()));
   if(admitted)changed(db.update("UPDATE scheduler_pool SET wrr_cursor=? WHERE id=1 AND config_version=?",chosen.nextCursor,pool.version));
   audit.append(execution,request.routeId(),version.version(),"ADMISSION_"+decision,actor,"initial admission "+id,requestId);
   if(admitted)audit.append(execution,request.routeId(),version.version(),"PERMIT_ACQUIRED",actor,"permit generation 1",requestId);
   return new Result(decision.equals("REJECTED")?409:202,parse(response.toString()));
  });
 }
 /** One bounded transaction per admitted request; queue order and cursor survive any process restart. */
 private record QueueProtection(String id,OperatorPayloadGuard.Prepared prepared,ApiProblem rejected){}
 private QueueProtection prepareQueue(){
  Choice choice=choose(readPool(false),null);if(choice==null)return new QueueProtection(null,null,null);
  var rows=db.queryForList("SELECT * FROM admission_requests WHERE id=?",choice.head.requestId);if(rows.isEmpty()||rows.getFirst().get("recovery_payload")==null)return new QueueProtection(null,null,null);
  var request=rows.getFirst();var q=recovery.request(request.get("recovery_payload"));
  try{return new QueueProtection(choice.head.requestId,guard.prepare(choice.head.executionId,q.incidentId(),q.stepId(),null,json.valueToTree(q),(String)request.get("principal"),(String)request.get("idempotency_key"),choice.head.requestId),null);}
  catch(ApiProblem invalid){if(invalid.status()>=500)throw invalid;return new QueueProtection(choice.head.requestId,null,invalid);}
 }
 public String tick(){var protection=prepareQueue();return tx.execute(s->{
  Pool p=lockPool();Choice chosen=choose(p,null);if(chosen==null)return null;Head h=chosen.head;
  var rows=db.queryForList("SELECT * FROM executions WHERE id=? FOR UPDATE",h.executionId);if(rows.isEmpty())throw new IllegalStateException("Queue execution missing");var e=rows.getFirst();
  recovery.lockIncidents(h.executionId);
  var requests=db.queryForList("SELECT * FROM admission_requests WHERE id=? FOR UPDATE",h.requestId);var request=requests.getFirst();
  if(request.get("recovery_payload")!=null){
   var q=recovery.request(request.get("recovery_payload"));Map<String,Object> r;
   if(!h.requestId.equals(protection.id()))return null; // Another transaction chose a different candidate; no cursor or permit mutation.
   try{
    if(protection.rejected()!=null)throw protection.rejected();
    guard.recheck(protection.prepared(),json.valueToTree(q),(String)request.get("principal"),(String)request.get("idempotency_key"),h.requestId);
    r=recovery.validate(e,q,h.requestId);
   }catch(ApiProblem stale){
    changed(db.update("UPDATE admission_requests SET decision='WITHDRAWN',state_version=state_version+1 WHERE id=? AND decision='QUEUED'",h.requestId));
    db.update("UPDATE engine_incidents SET pending_recovery_id=NULL WHERE id=? AND pending_recovery_id=?",q.incidentId(),h.requestId);
    if(e.get("state").equals("RECOVERY_QUEUED"))changed(db.update("UPDATE executions SET state='MANUAL_WAIT',state_version=state_version+1 WHERE id=? AND state_version=?",h.executionId,e.get("state_version")));
    audit.append(h.executionId,(String)e.get("route_id"),((Number)e.get("route_version")).intValue(),"RECOVERY_WITHDRAWN","scheduler","Stale incident before admission",h.requestId);return null;
   }
   acquireRecovery(e,q,h.requestId,r);
   changed(db.update("UPDATE admission_requests SET decision='ADMITTED',state_version=state_version+1 WHERE id=? AND decision='QUEUED'",h.requestId));
   changed(db.update("UPDATE scheduler_pool SET wrr_cursor=? WHERE id=1 AND config_version=?",chosen.nextCursor,p.version));return h.executionId;
  }
  if(!e.get("state").equals("QUEUED")||((Number)e.get("permit_generation")).longValue()!=0)throw new IllegalStateException("Queue execution incompatible");
  db.queryForList("SELECT id FROM admission_requests WHERE id=? FOR UPDATE",h.requestId);
  changed(db.update("UPDATE executions SET state='ADMITTED',permit_held=TRUE,permit_generation=permit_generation+1,state_version=state_version+1,updated_at=UTC_TIMESTAMP(6) WHERE id=? AND state='QUEUED' AND permit_held=FALSE AND state_version=?",h.executionId,e.get("state_version")));
  changed(db.update("UPDATE admission_requests SET decision='ADMITTED',state_version=state_version+1 WHERE id=? AND decision='QUEUED'",h.requestId));
  changed(db.update("UPDATE scheduler_pool SET wrr_cursor=? WHERE id=1 AND config_version=?",chosen.nextCursor,p.version));
  audit.append(h.executionId,(String)e.get("route_id"),((Number)e.get("route_version")).intValue(),"PERMIT_ACQUIRED","scheduler","queued permit generation 1",h.requestId);
  return h.executionId;
 });}

 public Result recover(String execution,String actor,String key,RecoveryPolicy.Request q,String requestId){
  if(key==null||!key.matches("[A-Za-z0-9._:-]{1,128}"))throw ApiProblem.invalid();
  String scope=recoveryScope(execution),id=identity(actor,scope,key),hash=canonical.hash(json.valueToTree(q));
  if(canonical.canonical(json.valueToTree(q)).length()>262144)throw ApiProblem.invalid();
  var prepared=db.queryForList("SELECT id FROM admission_requests WHERE id=?",id).isEmpty()?guard.prepare(execution,q.incidentId(),q.stepId(),null,json.valueToTree(q),actor,key,requestId):null;
  return tx.execute(s->{
   var pool=lockPool();var rows=db.queryForList("SELECT * FROM executions WHERE id=? FOR UPDATE",execution);if(rows.isEmpty())throw ApiProblem.missing();var e=rows.getFirst();
   recovery.lockIncidents(execution);
   var previous=db.queryForList("SELECT request_hash,response_json FROM admission_requests WHERE id=? FOR UPDATE",id);
   if(!previous.isEmpty()){
    if(!hash.equals(previous.getFirst().get("request_hash")))throw new ApiProblem(409,"IDEMPOTENCY_CONFLICT","Idempotency key belongs to different request content");
    var original=parse((String)previous.getFirst().get("response_json"));return new Result(original.path("decision").asText().equals("REJECTED")?409:202,original);
   }
   guard.recheck(prepared,json.valueToTree(q),actor,key,requestId);
   var r=recovery.validate(e,q,null);String priority=(String)e.get("priority");
   boolean queue=q.admissionMode().equals("QUEUE");var chosen=queue?null:choose(pool,new Head(id,execution,priority));
   boolean admitted=chosen!=null&&chosen.head.requestId.equals(id);String decision=queue?"QUEUED":admitted?"ADMITTED":"REJECTED";
   var out=json.createObjectNode().put("admissionRequestId",id).put("executionId",execution).put("incidentId",q.incidentId()).put("stepId",q.stepId())
    .put("action",q.action()).put("decision",decision).put("code",decision.equals("REJECTED")?"ADMISSION_REJECTED":"ADMISSION_"+decision)
    .put("priority",priority).put("routeVersion",((Number)e.get("route_version")).intValue()).put("configVersion",pool.version).put("decidedAt",now().toString());
   changed(db.update("INSERT INTO admission_requests(id,principal,operation_scope,idempotency_key,request_hash,execution_id,decision,priority,admission_mode,response_json,recovery_incident_id,recovery_step_id,recovery_payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
    id,actor,scope,key,hash,execution,decision,priority,q.admissionMode(),out.toString(),q.incidentId(),q.stepId(),canonical.canonical(json.valueToTree(q))));
   if(queue){
    changed(db.update("UPDATE engine_incidents SET pending_recovery_id=? WHERE id=? AND status='OPEN' AND pending_recovery_id IS NULL",id,q.incidentId()));
    changed(db.update("UPDATE executions SET state='RECOVERY_QUEUED',state_version=state_version+1,updated_at=UTC_TIMESTAMP(6) WHERE id=? AND state_version=?",execution,e.get("state_version")));
   }else if(admitted){
    acquireRecovery(e,q,id,r);changed(db.update("UPDATE scheduler_pool SET wrr_cursor=? WHERE id=1 AND config_version=?",chosen.nextCursor,pool.version));
   }
   audit.append(execution,(String)e.get("route_id"),((Number)e.get("route_version")).intValue(),"RECOVERY_"+decision,actor,q.reason(),requestId);
   return new Result(decision.equals("REJECTED")?409:202,parse(out.toString()));
  });
 }
 private void acquireRecovery(Map<String,Object> e,RecoveryPolicy.Request q,String id,Map<String,Object> r){
  changed(db.update("UPDATE executions SET state=?,permit_held=TRUE,permit_generation=permit_generation+1,state_version=state_version+1,cancel_requested=FALSE,updated_at=UTC_TIMESTAMP(6) WHERE id=? AND permit_held=FALSE AND state_version=?",
   recovery.rollback(q,r)?"ROLLING_BACK":"RECOVERING",e.get("id"),e.get("state_version")));
  recovery.apply(e,q,id);
  audit.append((String)e.get("id"),(String)e.get("route_id"),((Number)e.get("route_version")).intValue(),"PERMIT_ACQUIRED","scheduler","recovery permit generation "+(((Number)e.get("permit_generation")).longValue()+1),id);
 }
 private ObjectNode snapshot(Pool p){var result=json.createObjectNode();result.put("totalSlots",p.total).put("criticalReserved",p.reserved).put("highWeight",p.high).put("normalWeight",p.normal).put("lowWeight",p.low).put("wrrCursor",p.cursor).put("configVersion",p.version).put("admissionEnabled",p.enabled).put("used",count("permit_held=TRUE")).put("nonCriticalUsed",count("permit_held=TRUE AND priority<>'CRITICAL'")).put("observedAt",now().toString());result.put("queued",db.queryForObject("SELECT COUNT(*) FROM admission_requests WHERE decision='QUEUED'",Long.class));return result;}
 public JsonNode capacity(){return tx.execute(s->snapshot(lockPool()));}
 public JsonNode configure(Config c,String actor,String requestId){
  if(c.criticalReserved()>c.totalSlots())throw ApiProblem.invalid();
  return tx.execute(s->{Pool p=lockPool();if(c.configVersion()!=p.version||count("permit_held=TRUE")>c.totalSlots()||count("permit_held=TRUE AND priority<>'CRITICAL'")>c.totalSlots()-c.criticalReserved())throw ApiProblem.conflict();
   changed(db.update("UPDATE scheduler_pool SET total_slots=?,critical_reserved=?,high_weight=?,normal_weight=?,low_weight=?,admission_enabled=?,config_version=config_version+1,wrr_cursor=? WHERE id=1 AND config_version=?",c.totalSlots(),c.criticalReserved(),c.highWeight(),c.normalWeight(),c.lowWeight(),c.admissionEnabled(),c.highWeight()!=p.high||c.normalWeight()!=p.normal||c.lowWeight()!=p.low?0:p.cursor,p.version));
   // Audit values, not free-form request bodies or input. Keep operator reason with the versioned config.
   audit.append(null,null,null,"POOL_CONFIG_UPDATED",actor,c.reason(),requestId);
   changed(db.update("INSERT INTO pool_config_history(config_version,total_slots,critical_reserved,high_weight,normal_weight,low_weight,admission_enabled,actor,reason,request_id) VALUES(?,?,?,?,?,?,?,?,?,?)",p.version+1,c.totalSlots(),c.criticalReserved(),c.highWeight(),c.normalWeight(),c.lowWeight(),c.admissionEnabled(),actor,c.reason(),requestId));
   return snapshot(lockPool());
  });
 }
 public JsonNode lookup(String actor,String id){var rows=db.queryForList("SELECT response_json FROM admission_requests WHERE id=? AND principal=?",id,actor);if(rows.isEmpty())throw ApiProblem.missing();return parse((String)rows.getFirst().get("response_json"));}
 public JsonNode execution(String actor,String id){
  var rows=db.queryForList("SELECT e.id,e.route_id,e.route_version,e.priority,e.state,e.state_version,e.permit_held,e.permit_generation,e.lease_generation,v.definition_hash FROM executions e JOIN route_versions v ON v.route_id=e.route_id AND v.version=e.route_version JOIN admission_requests a ON a.execution_id=e.id WHERE e.id=? AND a.principal=? AND a.operation_scope=?",id,actor,SCOPE);
  if(rows.isEmpty())throw ApiProblem.missing();var r=rows.getFirst();var o=json.createObjectNode();o.put("executionId",id).put("routeId",(String)r.get("route_id")).put("routeVersion",((Number)r.get("route_version")).intValue()).put("priority",(String)r.get("priority")).put("state",(String)r.get("state")).put("stateVersion",((Number)r.get("state_version")).longValue()).put("permitHeld",Boolean.TRUE.equals(r.get("permit_held"))||r.get("permit_held") instanceof Number n&&n.intValue()==1).put("permitGeneration",((Number)r.get("permit_generation")).longValue()).put("leaseGeneration",((Number)r.get("lease_generation")).longValue()).put("definitionHash",(String)r.get("definition_hash"));return o;
 }
 /** Internal engine seam, never a REST force-release. Current DB work must have converged. */
 public String stop(String id,long generation,long stateVersion,String target,String actor,String reason,String requestId){
  if(!Set.of("MANUAL_WAIT","SUCCEEDED","FAILED","CANCELLED").contains(target))throw ApiProblem.invalid();
  return tx.execute(s->{lockPool();var rows=db.queryForList("SELECT * FROM executions WHERE id=? FOR UPDATE",id);if(rows.isEmpty())throw ApiProblem.missing();var e=rows.getFirst();
   if(((Number)e.get("permit_generation")).longValue()!=generation)return "STALE";
   boolean held=Boolean.TRUE.equals(e.get("permit_held"))||e.get("permit_held") instanceof Number n&&n.intValue()==1;
   if(!held)return e.get("state").equals(target)?"ALREADY_RELEASED":"STALE";
   if(((Number)e.get("state_version")).longValue()!=stateVersion)return "STALE";
   long active=db.queryForObject("SELECT COUNT(*) FROM step_runs WHERE execution_id=? AND state NOT IN ('SUCCEEDED','FAILED','STOPPED','SKIPPED','CANCELLED')",Long.class,id);
   active+=db.queryForObject("SELECT COUNT(*) FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE r.execution_id=? AND a.state NOT IN ('SUCCEEDED','FAILED','STOPPED','CANCELLED')",Long.class,id);
   if(active!=0)throw new ApiProblem(409,"WORK_NOT_STOPPED","Persisted work has not safely converged");
   changed(db.update("UPDATE executions SET state=?,permit_held=FALSE,state_version=state_version+1,updated_at=UTC_TIMESTAMP(6) WHERE id=? AND permit_generation=? AND state_version=? AND permit_held=TRUE",target,id,generation,stateVersion));
   audit.append(id,(String)e.get("route_id"),((Number)e.get("route_version")).intValue(),"PERMIT_RELEASED",actor,reason,requestId);return "RELEASED";
  });
 }
}