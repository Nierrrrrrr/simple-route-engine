package dev.routeengine.recovery;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import dev.routeengine.adapters.*;
import dev.routeengine.api.ApiProblem;
import dev.routeengine.registry.DefinitionRules;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import java.util.*;

/** Read bound credentials before locking; carry only immutable context/body digests into the mutation. */
@Component
public class OperatorPayloadGuard {
 public record Prepared(String execution,String incident,String step,String operation,String contextHash,String payloadHash){}
 private final JdbcTemplate db;private final ObjectMapper json;private final DefinitionRules rules;private final AdapterCatalog catalog;private final AdapterBindings bindings;
 public OperatorPayloadGuard(JdbcTemplate db,ObjectMapper json,DefinitionRules rules,AdapterCatalog catalog,AdapterBindings bindings){this.db=db;this.json=json;this.rules=rules;this.catalog=catalog;this.bindings=bindings;}
 private JsonNode parse(Object value){try{return value==null?json.createObjectNode():json.readTree(value.toString());}catch(Exception bad){throw ApiProblem.conflict();}}
 private Map<String,Object> snapshot(String execution,String incident,String step,String operation){
  var rows=db.queryForList("SELECT e.route_id,e.route_version,v.adapter_bindings FROM executions e JOIN route_versions v ON v.route_id=e.route_id AND v.version=e.route_version WHERE e.id=?",execution);
  if(rows.isEmpty())throw ApiProblem.missing();var result=new LinkedHashMap<String,Object>();result.put("execution",rows.getFirst());
  if(incident!=null){
   var exact=db.queryForList("SELECT i.id,i.step_run_id,i.attempt_id,i.operation_id,i.direction,i.operation_generation,i.permit_generation,i.legacy_unbound,r.node_json,a.adapter_plan FROM engine_incidents i JOIN step_runs r ON r.id=i.step_run_id AND r.execution_id=i.execution_id JOIN step_attempts a ON a.id=i.attempt_id AND a.step_run_id=r.id AND a.operation_id=i.operation_id AND a.direction=i.direction AND a.operation_generation=i.operation_generation AND a.permit_generation=i.permit_generation WHERE i.execution_id=? AND i.id=? AND r.id=?",execution,incident,step);
   if(exact.size()!=1||RecoveryPolicy.flag(exact.getFirst().get("legacy_unbound"))||exact.getFirst().get("adapter_plan")==null)throw ApiProblem.conflict();
   if(operation!=null&&!operation.equals(exact.getFirst().get("operation_id")))throw ApiProblem.conflict();result.put("incident",exact.getFirst());
  }
  return result;
 }
 private String key(JsonNode n){String type=n.path("type").asText();return type+":"+n.path(type.equals("REST")?"endpointRef":type.equals("ANSIBLE")?"playbookRef":"resourceRef").asText();}
 private String boundCredential(JsonNode published,JsonNode node,JsonNode plan){
  if(!bindings.matches(published,node))throw ApiProblem.conflict();JsonNode bound=published.path("references").path(key(node));
  if(plan!=null&&!bound.has("developmentContract")){
   var fields=bound.fields();while(fields.hasNext()){var field=fields.next();if(!field.getValue().equals(plan.path(field.getKey())))throw ApiProblem.conflict();}
  }
  if(!node.path("type").asText().equals("REST"))return "";
  JsonNode endpoint=catalog.endpoint(node.path("endpointRef").asText());
  if(endpoint.isMissingNode()){if(bound.path("developmentContract").asInt()==1)return "";throw ApiProblem.conflict();}
  try{return catalog.credential(endpoint);}catch(Exception unavailable){throw new ApiProblem(503,"VALIDATION_UNAVAILABLE","Bound credential validation is temporarily unavailable");}
 }
 private JsonNode envelope(JsonNode body,String actor,String key,String requestId){
  var value=json.createObjectNode();value.set("body",body);value.put("actor",actor).put("idempotencyKey",key).put("requestId",requestId);return value;
 }
 public Prepared prepare(String execution,String incident,String step,String operation,JsonNode body,String actor,String key,String requestId){
  if(TransactionSynchronizationManager.isActualTransactionActive())throw new IllegalStateException("Operator credential preparation inside transaction");
  var snapshot=snapshot(execution,incident,step,operation);var executionRow=(Map<?,?>)snapshot.get("execution");var published=parse(executionRow.get("adapter_bindings"));
  if(published.path("contract").asInt()!=1)throw ApiProblem.conflict();var secrets=new LinkedHashSet<String>();
  if(incident!=null){var exact=(Map<?,?>)snapshot.get("incident");secrets.add(boundCredential(published,parse(exact.get("node_json")),parse(exact.get("adapter_plan"))));}
  else{
   // Queue withdrawal/running cancellation has execution scope, so use this exact published version's refs.
   var refs=published.path("references").fields();while(refs.hasNext()){
    var ref=refs.next();String[] parts=ref.getKey().split(":",2);if(parts.length!=2)throw ApiProblem.conflict();
    var node=json.createObjectNode().put("type",parts[0]).put(parts[0].equals("REST")?"endpointRef":parts[0].equals("ANSIBLE")?"playbookRef":"resourceRef",parts[1]);
    secrets.add(boundCredential(published,node,null));
   }
  }
  secrets.add("");var submitted=envelope(body,actor,key,requestId);var checked=submitted.deepCopy();
  // Absent optional outputs are envelope metadata, not user-provided scalar output. Nested nulls are checked.
  if(checked.path("body") instanceof ObjectNode fields)for(String field:List.of("output","replacementOutput"))if(fields.path(field).isNull())fields.remove(field);
  try{for(String secret:secrets)catalog.safeOutput(checked,secret);}catch(IllegalArgumentException unsafe){throw ApiProblem.invalid();}
  return new Prepared(execution,incident,step,operation,rules.hash(json.valueToTree(snapshot)),rules.hash(submitted));
 }
 /** Caller already holds pool -> execution -> incidents. This method performs DB reads and pure checks only. */
 public void recheck(Prepared prepared,JsonNode body,String actor,String key,String requestId){
  if(prepared==null||!prepared.contextHash().equals(rules.hash(json.valueToTree(snapshot(prepared.execution(),prepared.incident(),prepared.step(),prepared.operation()))))||
    !prepared.payloadHash().equals(rules.hash(envelope(body,actor,key,requestId))))throw ApiProblem.conflict();
 }
}
