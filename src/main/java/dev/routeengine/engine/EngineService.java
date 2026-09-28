package dev.routeengine.engine;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import dev.routeengine.admission.AdmissionService;
import dev.routeengine.audit.AuditLog;
import dev.routeengine.registry.DefinitionRules;
import dev.routeengine.api.ApiProblem;
import dev.routeengine.recovery.RecoveryPolicy;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import java.sql.Timestamp;
import java.time.*;
import java.util.*;
import static dev.routeengine.engine.OperationAdapter.*;

/** DB-backed finite tree interpreter. All mutation transactions acquire pool -> execution -> existing incidents -> step/attempt.
 * The database pending rows are the queue; there is no in-memory continuation or event replay. */
@Service
public class EngineService {
 @org.springframework.beans.factory.annotation.Autowired private dev.routeengine.registry.PersistenceGuard persistence;
 @org.springframework.beans.factory.annotation.Autowired private dev.routeengine.engine.ClaimLifecycle lifecycle;
 private boolean stopping(){return lifecycle!=null&&lifecycle.stopping();}

 public record Work(String executionId,String stepId,String attemptId,long permitGeneration,long leaseGeneration,
                    long stepVersion,boolean observe,Request request){}
 private static final Set<String> TERMINAL=Set.of("SUCCEEDED","FAILED","STOPPED","SKIPPED","CANCELLED");
 private final JdbcTemplate db;private final TransactionTemplate tx;private final AuditLog audit;
 private final AdmissionService admission;private final DefinitionRules rules;private final ObjectMapper json;
 private final List<EngineHook> hooks;private final List<OperationAdapter> adapters;private final Clock clock;private final int leaseSeconds,pollSeconds;private final dev.routeengine.adapters.AdapterBindings bindings;
 private final String worker=UUID.randomUUID().toString();
 public EngineService(JdbcTemplate db,TransactionTemplate tx,AuditLog audit,AdmissionService admission,DefinitionRules rules,
    ObjectMapper json,List<OperationAdapter> adapters,List<EngineHook> hooks,Clock clock,dev.routeengine.adapters.AdapterBindings bindings,@Value("${route.engine.lease-seconds:30}") int leaseSeconds,@Value("${route.engine.poll-seconds:1}") int pollSeconds){
  if(leaseSeconds<1||leaseSeconds>300||pollSeconds<1||pollSeconds>60)throw new IllegalArgumentException("Invalid engine timing");
  this.db=db;this.tx=tx;this.audit=audit;this.admission=admission;this.rules=rules;this.json=json;this.adapters=List.copyOf(adapters);this.hooks=List.copyOf(hooks);this.clock=clock;this.leaseSeconds=leaseSeconds;this.pollSeconds=pollSeconds;this.bindings=bindings;
 }
 private JsonNode parse(Object s){try{return s==null?json.createObjectNode():json.readTree(s.toString());}catch(Exception e){throw new IllegalStateException("Invalid persisted engine data");}}
 private long number(Map<String,Object> row,String key){return ((Number)row.get(key)).longValue();}
 private boolean held(Map<String,Object> e){return Boolean.TRUE.equals(e.get("permit_held"))||e.get("permit_held") instanceof Number n&&n.intValue()==1;}
 private boolean notification(Map<String,Object> r){return Boolean.TRUE.equals(r.get("is_notification"))||r.get("is_notification") instanceof Number n&&n.intValue()==1;}
 private void changed(int count){if(count!=1)throw new IllegalStateException("Engine state CAS rejected");}
 private Instant dbNow(){return db.queryForObject("SELECT UTC_TIMESTAMP(6)",LocalDateTime.class).toInstant(ZoneOffset.UTC);}
 private Instant time(Object value){if(value==null)return null;if(value instanceof Timestamp t)return t.toLocalDateTime().toInstant(ZoneOffset.UTC);return ((LocalDateTime)value).toInstant(ZoneOffset.UTC);}
 private LocalDateTime stamp(Instant i){return i==null?null:LocalDateTime.ofInstant(i,ZoneOffset.UTC);}
 private Map<String,Object> execution(String id){
  db.queryForList("SELECT id FROM scheduler_pool WHERE id=1 FOR UPDATE");
  var rows=db.queryForList("SELECT * FROM executions WHERE id=? FOR UPDATE",id);
  if(rows.isEmpty())return null;
  // Lock existing incident history before any claim/result/structural step or attempt mutation.
  // New incident insertion later validates its step/attempt parents; it does not acquire an old incident.
  db.queryForList("SELECT id FROM engine_incidents WHERE execution_id=? ORDER BY id FOR UPDATE",id);
  return rows.getFirst();
 }
 private Map<String,Object> row(String execution,String node){var rows=db.queryForList("SELECT * FROM step_runs WHERE execution_id=? AND node_id=?",execution,node);return rows.isEmpty()?null:rows.getFirst();}
 private void event(Map<String,Object> e,String type,String reason){audit.append((String)e.get("id"),(String)e.get("route_id"),((Number)e.get("route_version")).intValue(),type,"engine",reason,(String)e.get("id"));}
 private JsonNode definition(Map<String,Object> e){return parse(db.queryForObject("SELECT definition_json FROM route_versions WHERE route_id=? AND version=?",String.class,e.get("route_id"),e.get("route_version")));}
 private void add(Map<String,Object> e,JsonNode n,String parent,boolean notice){
  String id=UUID.randomUUID().toString();var retry=n.path("retry");int attempts=retry.path("maxAttempts").asInt(1),elapsed=retry.path("maxElapsedSeconds").asInt(21600),backoff=retry.path("backoffSeconds").asInt(1),max=retry.path("maxBackoffSeconds").asInt(Math.max(backoff,60));
  int order=db.queryForObject("SELECT COUNT(*) FROM step_runs WHERE execution_id=?",Integer.class,e.get("id"));
  changed(db.update("INSERT INTO step_runs(id,execution_id,node_id,state,node_json,parent_node_id,ordinal_number,is_notification,max_attempts,max_elapsed_seconds,backoff_seconds,max_backoff_seconds) VALUES(?,?,?,'PENDING',?,?,?,?,?,?,?,?)",id,e.get("id"),n.path("id").asText(),rules.canonical(n),parent,order,notice,attempts,elapsed,backoff,max));
  event(e,"NODE_PENDING",n.path("id").asText());
 }
 private boolean cancelling(Map<String,Object> e){return Boolean.TRUE.equals(e.get("cancel_requested"))||e.get("cancel_requested") instanceof Number n&&n.intValue()==1;}
 private boolean halt(String id){if(Boolean.TRUE.equals(db.queryForObject("SELECT cancel_requested FROM executions WHERE id=?",Boolean.class,id)))return true;return db.queryForObject("SELECT COUNT(*) FROM step_runs WHERE execution_id=? AND is_notification=FALSE AND state IN ('FAILED','STOPPED','CANCELLED','IN_DOUBT')",Integer.class,id)>0;}
 private boolean knownFailure(String id){return db.queryForObject("SELECT COUNT(*) FROM step_runs WHERE execution_id=? AND is_notification=FALSE AND state IN ('FAILED','STOPPED','CANCELLED')",Integer.class,id)>0;}
 private void updateNode(Map<String,Object> r,String state,JsonNode output){
  changed(db.update("UPDATE step_runs SET state=?,output_json=?,state_version=state_version+1 WHERE id=? AND state_version=?",state,output==null?null:rules.canonical(output),r.get("id"),r.get("state_version")));
 }
 /** Structural advancement is done in the same transaction as the completed leaf result. */
 private void advance(Map<String,Object> e,JsonNode node,boolean stopping){
  String execution=(String)e.get("id"),id=node.path("id").asText(),type=node.path("type").asText();var r=row(execution,id);
  if(r==null||TERMINAL.contains(r.get("state")))return;
  if(stopping&&(knownFailure(execution)||cancelling(e))&&r.get("state").equals("RETRY_WAIT")){updateNode(r,"STOPPED",null);return;}
  if(r.get("state").equals("PENDING")){
   if(stopping){if(knownFailure(execution)||cancelling(e))updateNode(r,"STOPPED",null);return;}
   if(node.has("when")&&r.get("branch_choice")==null){
    boolean choice=compare(e,node.get("when"));changed(db.update("UPDATE step_runs SET branch_choice=?,input_json=?,state_version=state_version+1 WHERE id=? AND state_version=?",Boolean.toString(choice),rules.canonical(resolve(e,node.get("when").get("field").asText())),r.get("id"),r.get("state_version")));
    r=row(execution,id);if(!choice){updateNode(r,"SKIPPED",json.createObjectNode());return;}
   }
   if(Set.of("REST","KUBERNETES","ANSIBLE").contains(type))return;
   changed(db.update("UPDATE step_runs SET state='RUNNING',state_version=state_version+1 WHERE id=? AND state_version=?",r.get("id"),r.get("state_version")));r=row(execution,id);
   if(type.equals("CONDITION")){
    String chosen=compare(e,node.get("condition"))?"then":"else";
    changed(db.update("UPDATE step_runs SET branch_choice=?,input_json=?,state_version=state_version+1 WHERE id=? AND state_version=?",chosen,rules.canonical(resolve(e,node.get("condition").get("field").asText())),r.get("id"),r.get("state_version")));
    add(e,node.get(chosen),id,false);
   }else if(type.equals("PARALLEL"))for(var branch:node.get("branches"))add(e,branch,id,false);
  }
  if(Set.of("REST","KUBERNETES","ANSIBLE").contains(type))return;
  r=row(execution,id);var nodes=new ArrayList<JsonNode>();
  if(type.equals("CONDITION"))nodes.add(node.get((String)r.get("branch_choice")));
  else node.path(type.equals("PARALLEL")?"branches":"children").forEach(nodes::add);
  boolean settled=true,failed=false;ObjectNode outputs=json.createObjectNode();
  for(var child:nodes){
   var cr=row(execution,child.path("id").asText());
   if(cr==null){
    if(stopping||failed){continue;}
    if(type.equals("SEQUENCE")&&!settled)break;
    add(e,child,id,false);cr=row(execution,child.path("id").asText());
   }
   advance(e,child,stopping||failed);cr=row(execution,child.path("id").asText());String state=(String)cr.get("state");
   if(!TERMINAL.contains(state)){settled=false;if(type.equals("SEQUENCE"))break;}
   else if(Set.of("FAILED","STOPPED","CANCELLED").contains(state))failed=true;
   else outputs.set(child.path("id").asText(),parse(cr.get("output_json")));
  }
  // A halted sequence may never have initialized future children; it is safely stopped, not successful.
  if(settled){updateNode(row(execution,id),failed||stopping?"FAILED":"SUCCEEDED",outputs);event(e,"NODE_SETTLED",id);}
 }
 private JsonNode resolve(Map<String,Object> e,String ref){
  String[] parts=ref.split("\\.");JsonNode value;int at;
  if(parts[0].equals("input")){value=parse(e.get("input_json"));at=1;}
  else {var r=row((String)e.get("id"),parts[1]);if(r==null||!Set.of("SUCCEEDED","SKIPPED").contains(r.get("state")))throw new IllegalStateException("Unsettled output reference");value=parse(r.get("output_json"));at=2;}
  for(;at<parts.length;at++)value=value.path(parts[at]);return value.deepCopy();
 }
 private JsonNode bindings(Map<String,Object> e,JsonNode n){
  if(n.isObject()&&n.has("$ref")){var value=resolve(e,n.get("$ref").asText());if(value.isMissingNode())throw new IllegalStateException("Missing required input");return value;}
  if(n.isObject()){ObjectNode out=json.createObjectNode();n.fields().forEachRemaining(x->out.set(x.getKey(),bindings(e,x.getValue())));return out;}
  if(n.isArray()){ArrayNode out=json.createArrayNode();for(var v:n)out.add(bindings(e,v));return out;}return n.deepCopy();
 }
 private boolean compare(Map<String,Object> e,JsonNode c){
  JsonNode a=resolve(e,c.path("field").asText()),b=c.path("value");String op=c.path("operator").asText();
  if(op.equals("EXISTS"))return !a.isMissingNode()&&!a.isNull();
  if(a.isMissingNode())throw new IllegalStateException("Missing comparison input");
  int comparison=a.isNumber()&&b.isNumber()?a.decimalValue().compareTo(b.decimalValue()):0;
  boolean equal=a.isNumber()&&b.isNumber()?comparison==0:a.equals(b);
  return switch(op){case "EQ"->equal;case "NE"->!equal;case "LT"->comparison<0;case "LE"->comparison<=0;case "GT"->comparison>0;case "GE"->comparison>=0;default->throw new IllegalStateException("Invalid comparison");};
 }
 private void resumeDeferred(Map<String,Object> e){
  String id=(String)e.get("id");
  if(db.queryForObject("SELECT COUNT(*) FROM step_runs WHERE execution_id=? AND direction='FORWARD' AND is_notification=FALSE AND attempt_count>0 AND state IN ('FAILED','STOPPED','CANCELLED','IN_DOUBT')",Integer.class,id)!=0)return;
  for(var r:db.queryForList("SELECT * FROM step_runs WHERE execution_id=? AND direction='FORWARD' AND is_notification=FALSE AND attempt_count=0 AND state IN ('FAILED','STOPPED') ORDER BY ordinal_number",id)){
   String type=parse(r.get("node_json")).path("type").asText();
   String state=Set.of("SEQUENCE","PARALLEL","CONDITION").contains(type)&&(!type.equals("CONDITION")||r.get("branch_choice")!=null)?"RUNNING":"PENDING";
   updateNode(r,state,null);
  }
 }
 private void settle(Map<String,Object> e){
  String id=(String)e.get("id");
  if(e.get("recovery_target_step_id")!=null&&!cancelling(e)){
   var target=db.queryForMap("SELECT * FROM step_runs WHERE id=?",e.get("recovery_target_step_id"));
   if(!TERMINAL.contains(target.get("state"))){
    String state=target.get("state").equals("IN_DOUBT")?"RECONCILING":target.get("state").equals("RETRY_WAIT")?"RETRY_WAIT":target.get("direction").equals("ROLLBACK")?"ROLLING_BACK":"RECOVERING";
    changed(db.update("UPDATE executions SET state=?,state_version=state_version+1,updated_at=UTC_TIMESTAMP(6) WHERE id=? AND state_version=?",state,id,e.get("state_version")));return;
   }
   if(target.get("direction").equals("ROLLBACK")){
    long active=db.queryForObject("SELECT COUNT(*) FROM step_runs WHERE execution_id=? AND state NOT IN ('SUCCEEDED','FAILED','STOPPED','SKIPPED','CANCELLED')",Long.class,id);
    if(active>0)return;
    if(target.get("state").equals("SUCCEEDED")){
     changed(db.update("UPDATE step_runs SET compensated=TRUE,state_version=state_version+1 WHERE id=? AND compensated=FALSE",target.get("recovery_origin_id")));
     incident(e,target,"COMPENSATED");
    }
    admission.stop(id,number(e,"permit_generation"),number(e,"state_version"),"MANUAL_WAIT","engine","Compensation settled; explicit operator decision required",id);return;
   }
   changed(db.update("UPDATE executions SET recovery_target_step_id=NULL WHERE id=?",id));resumeDeferred(e);e=db.queryForMap("SELECT * FROM executions WHERE id=?",id);
  }
  if(cancelling(e)&&e.get("recovery_target_step_id")!=null){
   var cancelled=db.queryForMap("SELECT * FROM step_runs WHERE id=?",e.get("recovery_target_step_id"));
   if(Set.of("PENDING","RETRY_WAIT").contains(cancelled.get("state")))updateNode(cancelled,"STOPPED",null);
  }
  if(e.get("state").equals("RECOVERING")&&e.get("recovery_target_step_id")==null&&!cancelling(e))resumeDeferred(e);
  var root=definition(e).get("root");advance(e,root,halt(id));
  // Failure notices are separate leaves, outside the root tree. A cancellation must
  // stop never-started/retry-pending notices while active operations still reconcile.
  if(cancelling(e))for(var notice:db.queryForList("SELECT * FROM step_runs WHERE execution_id=? AND is_notification=TRUE AND state IN ('PENDING','RETRY_WAIT') ORDER BY id FOR UPDATE",id)){
   updateNode(notice,"STOPPED",null);event(e,"NOTIFICATION_STOPPED",(String)notice.get("node_id"));
  }
  var rows=db.queryForList("SELECT state,is_notification FROM step_runs WHERE execution_id=?",id);
  boolean unknown=rows.stream().anyMatch(r->r.get("state").equals("IN_DOUBT"));
  boolean failed=rows.stream().anyMatch(r->!notification(r)&&r.get("state").equals("FAILED"));
  boolean active=rows.stream().anyMatch(r->!TERMINAL.contains(r.get("state")));
  boolean retry=rows.stream().anyMatch(r->r.get("state").equals("RETRY_WAIT"));
  String target=unknown?"RECONCILING":cancelling(e)?"CANCELING":failed?"PAUSING":retry?"RETRY_WAIT":"RUNNING";
  if(!active){
   long unresolved=db.queryForObject("SELECT COUNT(*) FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE r.execution_id=? AND a.state NOT IN ('SUCCEEDED','FAILED','STOPPED','CANCELLED')",Long.class,id);
   if(unresolved!=0)target="RECONCILING";
   else{
    var current=db.queryForMap("SELECT * FROM executions WHERE id=?",id);
    admission.stop(id,number(current,"permit_generation"),number(current,"state_version"),cancelling(e)?"CANCELLED":failed?"MANUAL_WAIT":"SUCCEEDED","engine","All initialized work and notifications settled",id);
    return;
   }
  }
  var current=db.queryForMap("SELECT * FROM executions WHERE id=?",id);
  changed(db.update("UPDATE executions SET state=?,state_version=state_version+1,next_action_at=(SELECT MIN(next_action_at) FROM step_runs WHERE execution_id=?),updated_at=UTC_TIMESTAMP(6) WHERE id=? AND state_version=?",target,id,id,current.get("state_version")));
 }
 public Work claim(String id){
  if(stopping())return null;
  if(hooks.stream().anyMatch(h->!h.allowClaim(id)))return null;
  // Revalidate historical input before any fresh claim or structural snapshot expansion.
  // Adapter binding drift still follows the existing unknown/identity reconciliation path.
  if(db.queryForObject("SELECT COUNT(*) FROM executions WHERE id=?",Long.class,id)==0)return null;
  var protectedInput=persistence.prepareExecution(id);
  return tx.execute(s->{
   var e=execution(id);if(stopping())return null;if(e==null||!held(e)||!Set.of("ADMITTED","RUNNING","WAITING_EXTERNAL","RETRY_WAIT","PAUSING","RECONCILING","CANCELING","RECOVERING","ROLLING_BACK").contains(e.get("state")))return null;
   var d=definition(e);if(!d.path("engineSemanticsVersion").asText().equals("1"))return null;
   persistence.recheckExecution(protectedInput,id);
   if(row(id,d.path("root").path("id").asText())==null)add(e,d.get("root"),null,false);
   settle(e);e=db.queryForMap("SELECT * FROM executions WHERE id=?",id);if(!held(e))return null;
   boolean recovering=e.get("recovery_target_step_id")!=null;boolean stopping=recovering?cancelling(e):halt(id);Instant now=dbNow(),domain=clock.instant();
   var rows=db.queryForList("SELECT * FROM step_runs WHERE execution_id=? ORDER BY ordinal_number",id);
   for(var r:rows){
    if(recovering&&!r.get("id").equals(e.get("recovery_target_step_id"))&&!notification(r))continue;
    var node=parse(r.get("node_json"));if(!Set.of("REST","KUBERNETES","ANSIBLE").contains(node.path("type").asText()))continue;
    String state=(String)r.get("state");boolean fresh=state.equals("PENDING")||state.equals("RETRY_WAIT");
    if(fresh){
     if(stopping&&(!notification(r)||cancelling(e)))continue;
     if(state.equals("RETRY_WAIT")&&time(r.get("next_action_at")).isAfter(domain))continue;
     if(r.get("first_attempt_at")!=null&&!domain.isBefore(time(r.get("first_attempt_at")).plusSeconds(number(r,"max_elapsed_seconds")))){
      fail(e,r,true);settle(e);return null;
     }
    }else if(Set.of("RUNNING","WAITING_EXTERNAL","IN_DOUBT").contains(state)){
     Instant lease=time(r.get("lease_until")),due=time(r.get("next_action_at"));
     if(lease!=null&&lease.isAfter(now)||lease==null&&due!=null&&due.isAfter(now))continue;
    }else continue;
    long generation=number(r,"lease_generation")+1,operation=number(r,"operation_generation")+(fresh?1:0);int attempt=(int)number(r,"attempt_count")+(fresh?1:0);
    String attemptId,operationId,externalUid=null;JsonNode input,adapterPlan;
    JsonNode versionBinding=parse(db.queryForObject("SELECT adapter_bindings FROM route_versions WHERE route_id=? AND version=?",String.class,e.get("route_id"),e.get("route_version")));
    boolean bound=bindings.matches(versionBinding,node);
    if(fresh){
     input=r.get("input_json")==null?bindings(e,node.path("input").isObject()?node.get("input"):json.createObjectNode()):parse(r.get("input_json"));
     // when's evaluated value is not the activity input; resolve once at first actual claim.
     if(attempt==1&&r.get("direction").equals("FORWARD"))input=bindings(e,node.path("input").isObject()?node.get("input"):json.createObjectNode());
     if(r.get("direction").equals("FORWARD")&&node.has("rollback")&&r.get("rollback_input_json")==null)
      changed(db.update("UPDATE step_runs SET rollback_input_json=?,rollback_allowed=? WHERE id=?",rules.canonical(bindings(e,node.get("rollback").path("input").isObject()?node.get("rollback").get("input"):json.createObjectNode())),!node.get("rollback").has("when")||compare(e,node.get("rollback").get("when")),r.get("id")));
     attemptId=UUID.randomUUID().toString();operationId=UUID.randomUUID().toString();
     var plannedRequest=new Request(operationId,operation,attempt,(String)r.get("direction"),node.deepCopy(),input.deepCopy());
     var adapter=adapters.stream().filter(a->a.supports(node)).findFirst();
     adapterPlan=bound&&adapter.isPresent()?adapter.get().plan(plannedRequest):json.createObjectNode().put("bindingUnavailable",true);
     changed(db.update("INSERT INTO step_attempts(id,step_run_id,attempt_number,direction,state,permit_generation,lease_generation,operation_generation,operation_id,adapter_plan) VALUES(?,?,?,?,'INTENT_COMMITTED',?,?,?,?,?)",attemptId,r.get("id"),attempt,r.get("direction"),e.get("permit_generation"),generation,operation,operationId,rules.canonical(adapterPlan)));
    }else{
     var a=db.queryForMap("SELECT * FROM step_attempts WHERE step_run_id=? AND attempt_number=? AND direction=?",r.get("id"),attempt,r.get("direction"));
     attemptId=(String)a.get("id");operationId=(String)a.get("operation_id");input=parse(r.get("input_json"));adapterPlan=parse(a.get("adapter_plan"));externalUid=(String)a.get("external_uid");
     changed(db.update("UPDATE step_attempts SET lease_generation=? WHERE id=? AND lease_generation=?",generation,attemptId,a.get("lease_generation")));
     event(e,"OPERATION_RECONCILING",(String)r.get("node_id"));
     if(!bound)adapterPlan=json.createObjectNode().put("bindingUnavailable",true); // Keep the original durable plan/identity; no new target.
    }
    changed(db.update("UPDATE step_runs SET state='RUNNING',input_json=?,attempt_count=?,first_attempt_at=COALESCE(first_attempt_at,?),operation_generation=?,lease_owner=?,lease_generation=?,lease_until=?,next_action_at=NULL,state_version=state_version+1 WHERE id=? AND state_version=?",rules.canonical(input),attempt,stamp(domain),operation,worker,generation,stamp(now.plusSeconds(leaseSeconds)),r.get("id"),r.get("state_version")));
    changed(db.update("UPDATE executions SET lease_generation=lease_generation+1,state_version=state_version+1 WHERE id=? AND state_version=?",id,e.get("state_version")));
    event(e,fresh?"ATTEMPT_INTENT":"LEASE_RECLAIMED",(String)r.get("node_id"));
    return new Work(id,(String)r.get("id"),attemptId,number(e,"permit_generation"),generation,number(r,"state_version")+1,!fresh,new Request(operationId,operation,attempt,(String)r.get("direction"),node.deepCopy(),input.deepCopy(),adapterPlan.deepCopy(),externalUid,cancelling(e)));
   }
   return null;
  });
 }
 private boolean current(Work w,Map<String,Object> e,Map<String,Object> r){
  return e!=null&&held(e)&&number(e,"permit_generation")==w.permitGeneration()&&r!=null&&number(r,"lease_generation")==w.leaseGeneration()&&number(r,"state_version")==w.stepVersion()&&r.get("state").equals("RUNNING")&&time(r.get("lease_until"))!=null&&time(r.get("lease_until")).isAfter(dbNow())
   &&db.queryForObject("SELECT COUNT(*) FROM step_attempts WHERE id=? AND step_run_id=? AND direction=? AND operation_id=? AND operation_generation=? AND permit_generation=? AND lease_generation=?",Integer.class,w.attemptId(),w.stepId(),w.request().direction(),w.request().operationId(),w.request().operationGeneration(),w.permitGeneration(),w.leaseGeneration())==1;
 }
 /** Fresh dispatch linearizes when claim commits its durable intent under the pool/execution locks.
  * Cancellation prevents later fresh claims; an already claimed request may still submit, then
  * reconciles/cancels under the same operation and held permit until terminal evidence arrives.
  * A second DB check prevents a queued/stale worker from starting I/O after ownership was lost.
  * Fencing cannot revoke an HTTP request already in flight; expiry therefore only observes. */
 public boolean execute(Work w){
  if(w==null)return false;
  boolean valid=Boolean.TRUE.equals(tx.execute(s->{var e=execution(w.executionId());var rows=db.queryForList("SELECT * FROM step_runs WHERE id=?",w.stepId());return current(w,e,rows.isEmpty()?null:rows.getFirst());}));
  if(!valid)return false;
  Outcome result;
  try{
   var adapter=adapters.stream().filter(a->a.supports(w.request().node())).findFirst();
   result=w.request().context().path("bindingUnavailable").asBoolean(false)?Outcome.unknown():adapter.isEmpty()?(w.observe()?Outcome.unknown():new Outcome(Status.FAILED,null,false,null)):(w.request().cancelRequested()?adapter.get().cancel(w.request()):w.observe()?adapter.get().observe(w.request()):adapter.get().submit(w.request()));
   if(result==null)result=Outcome.unknown();
  }catch(Exception ordinary){result=Outcome.unknown();}
  if(result.status()==Status.SUCCEEDED)hooks.forEach(h->h.beforeCompletion(w));
  hooks.forEach(h->h.beforeResult(w));
  boolean committed=complete(w,result);
  if(committed&&result.status()==Status.SUCCEEDED)hooks.forEach(h->h.afterCompletion(w));
  return committed;
 }
 public boolean complete(Work w,Outcome outcome){
  return Boolean.TRUE.equals(tx.execute(s->{
   var e=execution(w.executionId());var rows=db.queryForList("SELECT * FROM step_runs WHERE id=?",w.stepId());var r=rows.isEmpty()?null:rows.getFirst();if(!current(w,e,r))return false;
   Outcome result=outcome;var node=parse(r.get("node_json"));
   if(result.status()==Status.SUCCEEDED){
    try{rules.validateValue(node.path("outputSchema"),result.output()==null?json.createObjectNode():result.output());}
    catch(Exception invalidOutput){result=new Outcome(Status.FAILED,null,false,result.externalUid());}
   }
   String attemptState=switch(result.status()){case WAITING->"SUBMITTED";case UNKNOWN->"IN_DOUBT";default->result.status().name();};
   changed(db.update("UPDATE step_attempts SET state=?,external_uid=COALESCE(?,external_uid),finished_at=? WHERE id=? AND permit_generation=? AND lease_generation=? AND operation_generation=?",attemptState,result.externalUid(),TERMINAL.contains(attemptState)?stamp(dbNow()):null,w.attemptId(),w.permitGeneration(),w.leaseGeneration(),w.request().operationGeneration()));
   if(Set.of(Status.SUCCEEDED,Status.FAILED,Status.STOPPED).contains(result.status())){
    int resolved=db.update("UPDATE engine_incidents SET status='RESOLVED' WHERE step_run_id=? AND attempt_id=? AND operation_id=? AND direction=? AND operation_generation=? AND permit_generation=? AND legacy_unbound=FALSE AND kind='IN_DOUBT' AND status='OPEN'",r.get("id"),w.attemptId(),w.request().operationId(),w.request().direction(),w.request().operationGeneration(),w.permitGeneration());
    if(resolved>1)throw new IllegalStateException("Incident uniqueness violated");
    if(resolved==1)event(e,"INCIDENT_RESOLVED",(String)r.get("node_id")+" attempt="+w.attemptId()+" operation="+w.request().operationId()+" direction="+w.request().direction()+" observed "+attemptState);
   }
   switch(result.status()){
    case SUCCEEDED -> updateNode(r,"SUCCEEDED",result.output()==null?json.createObjectNode():result.output());
    case STOPPED -> {updateNode(r,"STOPPED",json.createObjectNode());if(!cancelling(e)&&!notification(r))incident(e,r,"KNOWN_FAILURE");}
    case FAILED -> {
     long delay=number(r,"backoff_seconds");for(int n=1;n<number(r,"attempt_count")-number(r,"retry_base")&&delay<number(r,"max_backoff_seconds");n++)delay=Math.min(number(r,"max_backoff_seconds"),delay*2);
     Instant next=clock.instant().plusSeconds(delay),end=time(r.get("first_attempt_at")).plusSeconds(number(r,"max_elapsed_seconds"));
     if(result.retryable()&&number(r,"attempt_count")-number(r,"retry_base")<number(r,"max_attempts")&&next.isBefore(end)){
      changed(db.update("UPDATE step_runs SET state='RETRY_WAIT',next_action_at=?,state_version=state_version+1 WHERE id=? AND state_version=?",stamp(next),r.get("id"),r.get("state_version")));event(e,"RETRY_SCHEDULED",(String)r.get("node_id"));
     }else fail(e,r,true);
    }
    case WAITING -> changed(db.update("UPDATE step_runs SET state='WAITING_EXTERNAL',next_action_at=?,state_version=state_version+1 WHERE id=? AND state_version=?",stamp(dbNow().plusSeconds(pollSeconds)),r.get("id"),r.get("state_version")));
    case UNKNOWN -> {
     changed(db.update("UPDATE step_runs SET state='IN_DOUBT',next_action_at=?,state_version=state_version+1 WHERE id=? AND state_version=?",stamp(dbNow().plusSeconds(pollSeconds)),r.get("id"),r.get("state_version")));
     incident(e,r,"IN_DOUBT");event(e,"OPERATION_IN_DOUBT",(String)r.get("node_id"));
    }
   }
   changed(db.update("UPDATE step_runs SET lease_owner=NULL,lease_until=NULL WHERE id=? AND lease_generation=?",r.get("id"),w.leaseGeneration()));
   event(e,"ATTEMPT_RESULT",(String)r.get("node_id")+" "+attemptState);settle(e);return true;
  }));
 }
 private void incident(Map<String,Object> e,Map<String,Object> r,String kind){
  var a=db.queryForMap("SELECT * FROM step_attempts WHERE step_run_id=? AND direction=? AND attempt_number=?",r.get("id"),r.get("direction"),r.get("attempt_count"));
  if(db.queryForObject("SELECT COUNT(*) FROM engine_incidents WHERE attempt_id=? AND kind=?",Integer.class,a.get("id"),kind)==0){
   String incidentId=UUID.randomUUID().toString();
   changed(db.update("INSERT INTO engine_incidents(id,execution_id,step_run_id,kind,attempt_id,operation_id,direction,operation_generation,permit_generation,legacy_unbound) VALUES(?,?,?,?,?,?,?,?,?,FALSE)",incidentId,e.get("id"),r.get("id"),kind,a.get("id"),a.get("operation_id"),a.get("direction"),a.get("operation_generation"),a.get("permit_generation")));
   event(e,"INCIDENT_OPENED",incidentId+" "+kind+" attempt="+a.get("id")+" operation="+a.get("operation_id")+" direction="+a.get("direction"));
  }
 }
 private void fail(Map<String,Object> e,Map<String,Object> r,boolean notify){
  updateNode(r,"FAILED",null);if(notification(r)){event(e,"NOTIFICATION_FAILED",(String)r.get("node_id"));return;}
  incident(e,r,"KNOWN_FAILURE");JsonNode failure=parse(r.get("node_json")).path("onFailure");
  if(notify&&failure.isObject()){
   var n=json.createObjectNode().put("id","_notify_"+r.get("id")+"_"+r.get("operation_generation")).put("type","REST").put("endpointRef",failure.path("endpointRef").asText());
   n.putObject("input").put("failedNode",(String)r.get("node_id"));
   n.putObject("retry").put("maxAttempts",failure.path("maxAttempts").asInt()).put("maxElapsedSeconds",60).put("backoffSeconds",1);
   add(e,n,null,true);
  }
 }
 /** M4 internal cancellation capability; public operator/recovery policy is added in M5. */
 public void requestCancel(String id,String actor,String reason){
  if(actor==null||actor.isBlank()||reason==null||reason.isBlank())throw new IllegalArgumentException("Cancellation requires actor and reason");
  tx.executeWithoutResult(s->{
   var e=execution(id);if(e==null||!held(e))throw new IllegalStateException("Running permit required");
   if(cancelling(e))return;
   changed(db.update("UPDATE executions SET cancel_requested=TRUE,state='CANCELING',state_version=state_version+1 WHERE id=? AND state_version=?",id,e.get("state_version")));
   audit.append(id,(String)e.get("route_id"),((Number)e.get("route_version")).intValue(),"CANCEL_REQUESTED",actor,reason,id);
  });
 }

 public void confirm(String id,String incidentId,String operationId,String stepId,String outcome,JsonNode output,String actor,String reason){
  tx.executeWithoutResult(s->{
   var e=execution(id);if(e==null||!held(e))throw ApiProblem.conflict();
   var found=db.queryForList("SELECT * FROM engine_incidents WHERE id=? AND execution_id=? AND kind='IN_DOUBT' AND status='OPEN' AND legacy_unbound=FALSE",incidentId,id);
   if(found.isEmpty())throw ApiProblem.conflict();var i=found.getFirst();
   if(!stepId.equals(i.get("step_run_id"))||!operationId.equals(i.get("operation_id"))||number(e,"permit_generation")!=number(i,"permit_generation"))throw ApiProblem.conflict();
   var r=db.queryForMap("SELECT * FROM step_runs WHERE id=? FOR UPDATE",stepId);
   if(!Set.of("RUNNING","IN_DOUBT").contains(r.get("state"))||number(r,"operation_generation")!=number(i,"operation_generation"))throw ApiProblem.conflict();
   var node=parse(r.get("node_json"));var value=output==null?json.createObjectNode():output;
   if(outcome.equals("SUCCEEDED"))rules.validateValue(node.path("outputSchema"),value);
   long generation=number(r,"lease_generation")+1,version=number(r,"state_version")+1;
   changed(db.update("UPDATE step_runs SET state='RUNNING',lease_generation=?,lease_until=?,state_version=? WHERE id=? AND state_version=?",generation,stamp(dbNow().plusSeconds(leaseSeconds)),version,stepId,r.get("state_version")));
   changed(db.update("UPDATE step_attempts SET lease_generation=? WHERE id=? AND operation_id=?",generation,i.get("attempt_id"),operationId));
   var request=new Request(operationId,number(i,"operation_generation"),(int)number(r,"attempt_count"),(String)i.get("direction"),node,parse(r.get("input_json")));
   var work=new Work(id,stepId,(String)i.get("attempt_id"),number(e,"permit_generation"),generation,version,true,request);
   if(!complete(work,new Outcome(Status.valueOf(outcome),value,false,null)))throw ApiProblem.conflict();
   audit.append(id,(String)e.get("route_id"),((Number)e.get("route_version")).intValue(),"OPERATOR_RESOLVED",actor,reason,incidentId);
  });
 }
 public void tick(String execution){execute(claim(execution));}
 public List<String> candidates(int limit){if(limit<1||limit>1000)throw new IllegalArgumentException();return db.queryForList("SELECT id FROM executions WHERE permit_held=TRUE AND state IN ('ADMITTED','RUNNING','WAITING_EXTERNAL','RETRY_WAIT','PAUSING','RECONCILING','CANCELING','RECOVERING','ROLLING_BACK') ORDER BY updated_at,id LIMIT ?",String.class,limit);}
}
