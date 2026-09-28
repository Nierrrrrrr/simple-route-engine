package dev.routeengine.registry;

import com.fasterxml.jackson.databind.*;
import dev.routeengine.adapters.*;
import dev.routeengine.api.ApiProblem;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/** Credential reads happen before locks; only immutable context and payload digests cross the transaction boundary. */
@Component
public class PersistenceGuard {
 public record Prepared(String contextHash,String payloadHash){}
 private final AdapterCatalog catalog;private final AdapterBindings bindings;private final DefinitionRules rules;private final ObjectMapper json;private final JdbcTemplate db;
 public PersistenceGuard(AdapterCatalog catalog,AdapterBindings bindings,DefinitionRules rules,ObjectMapper json,JdbcTemplate db){this.catalog=catalog;this.bindings=bindings;this.rules=rules;this.json=json;this.db=db;}
 private String context(JsonNode definition,JsonNode bound){var c=json.createObjectNode();c.set("definition",definition);c.set("bindings",bound);return rules.hash(c);}
 private void refs(JsonNode node,Set<String> result){
  if(node.path("type").asText().equals("REST"))result.add(node.path("endpointRef").asText());
  if(node.has("onFailure"))result.add(node.path("onFailure").path("endpointRef").asText());
  for(String field:List.of("children","branches"))for(JsonNode child:node.path(field))refs(child,result);
  for(String field:List.of("then","else","rollback"))if(node.has(field))refs(node.get(field),result);
 }
 private void check(JsonNode n,String secret){
  if(n==null||secret.isEmpty())return;
  if(n.isValueNode()){String value=n.isTextual()?n.textValue():n.toString();if(value.contains(secret))throw ApiProblem.unsafe();}
  else if(n.isObject()){var fields=n.fields();while(fields.hasNext()){var f=fields.next();if(f.getKey().contains(secret))throw ApiProblem.unsafe();check(f.getValue(),secret);}}
  else if(n.isArray())for(JsonNode child:n)check(child,secret);
 }
 /** Typed DSL metadata and deployed reference identifiers are not credential literals. */
 private void literals(JsonNode node,String secret){
  check(node.get("input"),secret);
  check(node.path("when").get("value"),secret);check(node.path("condition").get("value"),secret);
  for(String field:List.of("children","branches"))for(JsonNode child:node.path(field))literals(child,secret);
  for(String field:List.of("then","else","rollback"))if(node.has(field))literals(node.get(field),secret);
 }
 /** Values only: fixed envelope field names and absent optional values are metadata. */
 public JsonNode envelope(JsonNode payload,String... values){var result=json.createArrayNode();if(payload!=null)result.add(payload);for(String value:values)if(value!=null)result.add(value);return result;}
 public Prepared prepare(JsonNode definition,JsonNode bound,JsonNode payload){
  return prepare(definition,bound,payload,true);
 }
 private Prepared prepare(JsonNode definition,JsonNode bound,JsonNode payload,boolean requireBinding){
  var refs=new LinkedHashSet<String>();refs(definition.path("root"),refs);
  for(String ref:refs){
   var node=json.createObjectNode().put("type","REST").put("endpointRef",ref);
   if(requireBinding&&bound!=null&&!bindings.matches(bound,node))throw ApiProblem.conflict();
   var endpoint=catalog.endpoint(ref);
   // Drafts may name references that are not yet deployed; publication still requires a supported binding.
   if(endpoint.isMissingNode()||!endpoint.has("credentialRef"))continue;
   // Credential-free development/boundary adapters need only pure digest checks,
   // including callers exercising the lock protocol inside an existing transaction.
   if(TransactionSynchronizationManager.isActualTransactionActive())throw new IllegalStateException("Credential preparation inside transaction");
   String secret;try{secret=catalog.credential(endpoint);}catch(Exception unavailable){throw new ApiProblem(503,"VALIDATION_UNAVAILABLE","Credential validation is temporarily unavailable").withoutRequestId();}
   literals(definition.path("root"),secret);check(payload,secret);
  }
  return new Prepared(context(definition,bound),rules.hash(payload));
 }
 public void recheck(Prepared prepared,JsonNode definition,JsonNode bound,JsonNode payload){
  if(prepared==null||!prepared.contextHash().equals(context(definition,bound))||!prepared.payloadHash().equals(rules.hash(payload)))throw ApiProblem.conflict();
 }
 private JsonNode parse(Object value){try{return value==null?null:json.readTree(value.toString());}catch(Exception invalid){throw ApiProblem.conflict();}}
 public JsonNode bound(String route,int version){return parse(db.queryForObject("SELECT adapter_bindings FROM route_versions WHERE route_id=? AND version=?",String.class,route,version));}
 private Map<String,Object> execution(String id){var rows=db.queryForList("SELECT e.input_json,v.definition_json,v.adapter_bindings FROM executions e JOIN route_versions v ON v.route_id=e.route_id AND v.version=e.route_version WHERE e.id=?",id);if(rows.isEmpty())throw ApiProblem.missing();return rows.getFirst();}
 public Prepared prepareExecution(String id){var e=execution(id);return prepare(parse(e.get("definition_json")),parse(e.get("adapter_bindings")),parse(e.get("input_json")),false);}
 /** Caller holds pool then execution; no file or external I/O. */
 public void recheckExecution(Prepared p,String id){var e=execution(id);recheck(p,parse(e.get("definition_json")),parse(e.get("adapter_bindings")),parse(e.get("input_json")));}
}
