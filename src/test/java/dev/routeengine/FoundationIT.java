package dev.routeengine;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import dev.routeengine.audit.AuditLog;
import dev.routeengine.registry.RouteRegistry;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;
import java.net.URI;
import java.net.http.*;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT,properties={"route.scheduler.enabled=false","route.engine.enabled=false"})
class FoundationIT {
 @LocalServerPort int port;
 @Autowired ObjectMapper json;
 @Autowired JdbcTemplate db;
 @Autowired RouteRegistry routes;
 @Autowired AuditLog audit;
 @Autowired TransactionTemplate tx;
 final HttpClient http=HttpClient.newHttpClient();
 final String token=Objects.requireNonNull(System.getenv("ROUTE_TEST_TOKEN"),"Real isolated test token is mandatory");
 String id(){return "demo-"+UUID.randomUUID().toString().substring(0,8);}
 ObjectNode object(String text)throws Exception{return (ObjectNode)json.readTree(text);}
 ObjectNode definition(String id,int version) {
   var d=json.createObjectNode();d.put("routeId",id);d.put("version",version);d.put("dslVersion","1");d.put("engineSemanticsVersion","1");d.put("adapterContractVersion","1");
   var root=d.putObject("root");root.put("id","root");root.put("type","SEQUENCE");root.putArray("children");return d;
 }
 HttpResponse<String> call(String method,String path,JsonNode body)throws Exception{
  var b=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+path)).header("Authorization","Bearer "+token).header("Content-Type","application/json").header("X-Request-ID","test-request-123");
  return http.send(b.method(method,body==null?HttpRequest.BodyPublishers.noBody():HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body))).build(),HttpResponse.BodyHandlers.ofString());
 }
 JsonNode success(HttpResponse<String> r,int status)throws Exception{assertEquals(status,r.statusCode(),r.body());assertEquals("test-request-123",r.headers().firstValue("X-Request-ID").orElseThrow());return json.readTree(r.body());}
 String create()throws Exception{String id=id();success(call("POST","/routes",object("{\"routeId\":\""+id+"\",\"name\":\"DEMO fixture\"}")),201);return id;}
 JsonNode draft(String id,int v)throws Exception{var b=json.createObjectNode().set("definition",definition(id,v));return success(call("POST","/routes/"+id+"/versions",b),201);}
 JsonNode publish(String id,int v,long state)throws Exception{return success(call("POST","/routes/"+id+"/versions/"+v+"/publish",object("{\"stateVersion\":"+state+"}")),200);}
 @Test void AC006_emptyDatabaseFlywayUsesRealMariaDbInnoDb(){
   assertTrue(db.queryForObject("SELECT VERSION()",String.class).contains("MariaDB"));
   assertEquals(0,db.queryForObject("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_type='BASE TABLE' AND engine <> 'InnoDB'",Integer.class));
   assertEquals(List.of("1","2","3","4","5","6","7","8"),db.queryForList("SELECT version FROM flyway_schema_history WHERE success=1 ORDER BY installed_rank",String.class));
   for(String table:List.of("routes","route_versions","executions","admission_requests","step_runs","step_attempts","execution_events","scheduler_pool"))
    assertEquals(1,db.queryForObject("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=?",Integer.class,table));
 }
 @Test void AC007_draftPublishImmutableSoftDeleteKeepsExecutionVersion()throws Exception{
   String id=create();var v=draft(id,1);assertEquals("DRAFT",v.path("status").asText());
   var b=json.createObjectNode();b.put("stateVersion",0);b.set("definition",definition(id,1));
   v=success(call("PUT","/routes/"+id+"/versions/1",b),200);assertEquals(1,v.path("stateVersion").asLong());
   success(call("PUT","/routes/"+id+"/versions/1",b),409);
   v=publish(id,1,1);String hash=v.path("definitionHash").asText();assertEquals(64,hash.length());
   success(call("PUT","/routes/"+id+"/versions/1",b),409);
   assertThrows(DataAccessException.class,()->db.update("UPDATE route_versions SET definition_json='{}' WHERE route_id=? AND version=1",id));
   assertThrows(DataAccessException.class,()->db.update("DELETE FROM route_versions WHERE route_id=? AND version=1",id));
   String execution=UUID.randomUUID().toString();
   db.update("INSERT INTO executions(id,route_id,route_version,priority,state) VALUES(?,?,1,'NORMAL','QUEUED')",execution,id);
   draft(id,2);publish(id,2,0);
   assertEquals(1,db.queryForObject("SELECT route_version FROM executions WHERE id=?",Integer.class,execution));
   var route=success(call("GET","/routes/"+id,null),200);long state=route.path("stateVersion").asLong();
   success(call("PATCH","/routes/"+id,object("{\"stateVersion\":"+state+",\"enabled\":false,\"name\":\"DEMO disabled\"}")),200);
   assertThrows(dev.routeengine.api.ApiProblem.class,()->routes.resolveForNewExecution(id,null));
   assertEquals(hash,routes.getVersion(id,1).definitionHash());
   route=success(call("GET","/routes/"+id,null),200);
   success(call("DELETE","/routes/"+id+"?stateVersion="+route.path("stateVersion").asLong(),null),200);
   assertThrows(dev.routeengine.api.ApiProblem.class,()->routes.resolveForNewExecution(id,1));
   assertEquals(hash,success(call("GET","/routes/"+id+"/versions/1",null),200).path("definitionHash").asText());
   assertEquals(1,db.queryForObject("SELECT COUNT(*) FROM executions WHERE id=? AND route_version=1",Integer.class,execution));
 }
 @Test void AC007_uniqueMonotonicVersionAndDraftWithdrawal()throws Exception{
   String id=create();draft(id,1);draft(id,2);
   success(call("DELETE","/routes/"+id+"/versions/2?stateVersion=0",null),200);
   draft(id,3);
   assertThrows(DataAccessException.class,()->db.update("INSERT INTO route_versions(route_id,version,status,definition_json,definition_hash,dsl_version,engine_semantics_version,adapter_contract_version) SELECT route_id,version,status,definition_json,definition_hash,dsl_version,engine_semantics_version,adapter_contract_version FROM route_versions WHERE route_id=? AND version=1",id));
   success(call("POST","/routes",object("{\"routeId\":\""+id+"\",\"name\":\"duplicate\"}")),409);
 }
 @Test void AC008_validationErrorsRequestIdUtcAndActualOpenApi()throws Exception{
   var r=call("POST","/routes",object("{\"routeId\":\"BAD\",\"name\":\"bad\"}"));var err=success(r,422);
   assertEquals("INVALID_REQUEST",err.path("code").asText());assertEquals("test-request-123",err.path("requestId").asText());Instant.parse(err.path("timestamp").asText());
   success(call("POST","/routes",object("{\"routeId\":\"valid\",\"name\":\"ok\",\"unknown\":true}")),422);
   String id=create();var route=success(call("GET","/routes/"+id,null),200);Instant.parse(route.path("createdAt").asText());assertTrue(route.path("createdAt").asText().endsWith("Z"));
   success(call("GET","/routes/absent",null),404);
   var api=json.readTree(Files.readString(Path.of("docs/api/openapi.yaml")));
   assertEquals("RouteCreate",api.path("paths").path("/routes").path("post").path("requestBody").path("content").path("application/json").path("schema").path("$ref").asText().replace("#/components/schemas/",""));
   Set<String> required=new HashSet<>();api.path("components").path("schemas").path("Error").path("required").forEach(n->required.add(n.asText()));
   assertEquals(Set.of("code","message","requestId","timestamp"),required);
   assertTrue(api.path("paths").path("/routes").path("post").path("responses").has("201"));
   var documentedErrors=api.path("paths").path("/routes").path("post").path("responses");
   for(String status:List.of("404","405","415"))assertEquals("#/components/schemas/Error",documentedErrors.path(status).path("content").path("application/json").path("schema").path("$ref").asText());
   assertTrue(documentedErrors.path("405").path("headers").has("Allow"));
 }
 @Test void AC008_invalidAdmissionAndRecoveryNeverCreateWorkAndUnauthenticatedRequestsFail()throws Exception{
   var before=new LinkedHashMap<String,Long>();
   for(String table:List.of("executions","admission_requests","operator_commands","step_runs","step_attempts","execution_events"))
    before.put(table,db.queryForObject("SELECT COUNT(*) FROM "+table,Long.class));
   for(String path:List.of("/executions","/executions/future/recoveries")){
    var error=success(call("POST",path,object("{}")),422);
    assertEquals("INVALID_REQUEST",error.path("code").asText());assertEquals("test-request-123",error.path("requestId").asText());
    assertFalse(error.path("message").asText().isBlank());Instant.parse(error.path("timestamp").asText());assertTrue(error.path("timestamp").asText().endsWith("Z"));
   }
   var valid=object("{\"incidentId\":\"absent\",\"stepId\":\"absent\",\"action\":\"RETRY\",\"admissionMode\":\"NOW_OR_REJECT\",\"reason\":\"verify missing execution\"}");
   var missing=http.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+"/executions/future/recoveries"))
    .header("Authorization","Bearer "+token).header("Content-Type","application/json").header("X-Request-ID","test-request-123").header("Idempotency-Key","missing-recovery")
    .POST(HttpRequest.BodyPublishers.ofString(valid.toString())).build(),HttpResponse.BodyHandlers.ofString());
   var error=success(missing,404);assertEquals("NOT_FOUND",error.path("code").asText());assertEquals("test-request-123",error.path("requestId").asText());Instant.parse(error.path("timestamp").asText());
   for(String path:List.of("/routes","/executions/future/recoveries")){
    var request=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+path)).header("Content-Type","application/json");
    var r=http.send((path.equals("/routes")?request.GET():request.POST(HttpRequest.BodyPublishers.ofString(valid.toString()))).build(),HttpResponse.BodyHandlers.ofString());
    assertEquals(401,r.statusCode());assertTrue(json.readTree(r.body()).hasNonNull("requestId"));
   }
   for(var entry:before.entrySet())assertEquals(entry.getValue(),db.queryForObject("SELECT COUNT(*) FROM "+entry.getKey(),Long.class),entry.getKey()+" must not create work or commands");
 }
 @Test void AC009_fkStateCasAndEventsCommitOrRollbackTogether()throws Exception{
   String id=create();draft(id,1);publish(id,1,0);String execution=UUID.randomUUID().toString();
   assertThrows(DataAccessException.class,()->db.update("INSERT INTO executions(id,route_id,route_version,priority,state) VALUES(?,?,99,'NORMAL','QUEUED')",execution,id));
   db.update("INSERT INTO executions(id,route_id,route_version,priority,state) VALUES(?,?,1,'NORMAL','QUEUED')",execution,id);
   long before=db.queryForObject("SELECT COUNT(*) FROM execution_events WHERE execution_id=?",Long.class,execution);
   assertThrows(IllegalStateException.class,()->tx.executeWithoutResult(s->{
    assertEquals(1,db.update("UPDATE executions SET state_version=state_version+1 WHERE id=? AND state_version=0",execution));
    audit.append(execution,id,1,"FOUNDATION_FIXTURE","tester","atomic-test","test-request-123");
    throw new IllegalStateException("rollback fixture");
   }));
   assertEquals(0,db.queryForObject("SELECT state_version FROM executions WHERE id=?",Integer.class,execution));
   assertEquals(before,db.queryForObject("SELECT COUNT(*) FROM execution_events WHERE execution_id=?",Long.class,execution));
   tx.executeWithoutResult(s->{assertEquals(1,db.update("UPDATE executions SET state_version=state_version+1 WHERE id=? AND state_version=0",execution));audit.append(execution,id,1,"FOUNDATION_FIXTURE","tester","commit-test","test-request-123");});
   assertEquals(0,db.update("UPDATE executions SET state_version=state_version+1 WHERE id=? AND state_version=0",execution));
   assertEquals(before+1,db.queryForObject("SELECT COUNT(*) FROM execution_events WHERE execution_id=?",Long.class,execution));
   assertThrows(DataAccessException.class,()->db.update("DELETE FROM execution_events WHERE execution_id=?",execution));
   assertThrows(DataAccessException.class,()->db.update("UPDATE execution_events SET reason='edited' WHERE execution_id=?",execution));
 }
 @Test void AC009_admissionIdentityScopeAndAuditRequireTransaction(){
   String principal="fixture-"+UUID.randomUUID();
   String sql="INSERT INTO admission_requests(id,principal,operation_scope,idempotency_key,request_hash,decision,priority,admission_mode) VALUES(?,?,?,?,'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','REJECTED','NORMAL','NOW_OR_REJECT')";
   db.update(sql,UUID.randomUUID().toString(),principal,"POST /executions","same-key");
   assertThrows(DataAccessException.class,()->db.update(sql,UUID.randomUUID().toString(),principal,"POST /executions","same-key"));
   assertEquals(1,db.update(sql,UUID.randomUUID().toString(),principal+"-other","POST /executions","same-key"));
   assertThrows(org.springframework.transaction.IllegalTransactionStateException.class,()->audit.append(null,null,null,"FIXTURE","tester","must not commit alone","request"));
   assertThrows(DataAccessException.class,()->db.update("INSERT INTO step_runs(id,execution_id,node_id,state) VALUES(?,?, 'fixture','PENDING')",UUID.randomUUID().toString(),UUID.randomUUID().toString()));
 }
 @Test void AC009_routeMutationRollsBackWhenAuditCannotBeWritten()throws Exception{
   String id=id();
   assertThrows(RuntimeException.class,()->routes.create(id,"DEMO rollback","x".repeat(129),"request"));
   assertEquals(0,db.queryForObject("SELECT COUNT(*) FROM routes WHERE route_id=?",Integer.class,id));
   assertEquals(0,db.queryForObject("SELECT COUNT(*) FROM execution_events WHERE route_id=?",Integer.class,id));
 }

 @org.junit.jupiter.params.ParameterizedTest(name="{0} rejects {1}={2}")
 @org.junit.jupiter.params.provider.MethodSource("invalidScalars")
 void AC008_scalarCoercionNeverMutatesRegistry(String action,String field,String literal)throws Exception{
   String id=id();
   var body=json.createObjectNode();
   if(action.equals("create")){
     body.put("routeId",id);body.put("name","DEMO scalar fixture");body.set(field,json.readTree(literal));
     var response=call("POST","/routes",body);
     assertAll("invalid create must never persist",
       ()->assertEquals(422,response.statusCode(),response.body()),
       ()->assertEquals(0,db.queryForObject("SELECT COUNT(*) FROM routes WHERE route_id=?",Integer.class,id)),
       ()->assertEquals(0,db.queryForObject("SELECT COUNT(*) FROM route_versions WHERE route_id=?",Integer.class,id)),
       ()->assertEquals(0,db.queryForObject("SELECT COUNT(*) FROM execution_events WHERE route_id=?",Integer.class,id)));
     assertError(response,422,"INVALID_REQUEST");return;
   }
   success(call("POST","/routes",object("{\"routeId\":\""+id+"\",\"name\":\"DEMO unchanged\"}")),201);
   if(!action.equals("patch"))draft(id,1);
   var beforeRoute=success(call("GET","/routes/"+id,null),200);
   var beforeVersions=success(call("GET","/routes/"+id+"/versions",null),200);
   long beforeAudit=db.queryForObject("SELECT COUNT(*) FROM execution_events WHERE route_id=?",Long.class,id);
   String method,path;
   if(action.equals("patch")){
     method="PATCH";path="/routes/"+id;body.put("name","must not be persisted");body.put("enabled",false);body.put("stateVersion",beforeRoute.path("stateVersion").asLong());
   }else if(action.equals("edit")){
     method="PUT";path="/routes/"+id+"/versions/1";var changed=definition(id,1);((ObjectNode)changed.get("root")).put("id","mustNotBePersisted");body.set("definition",changed);body.put("stateVersion",0);
   }else{
     method="POST";path="/routes/"+id+"/versions/1/publish";body.put("stateVersion",0);
   }
   body.set(field,json.readTree(literal));
   var response=call(method,path,body);
   assertAll("invalid mutation must leave all persisted state unchanged",
     ()->assertEquals(422,response.statusCode(),response.body()),
     ()->assertEquals(beforeRoute,success(call("GET","/routes/"+id,null),200),"route including stateVersion changed"),
     ()->assertEquals(beforeVersions,success(call("GET","/routes/"+id+"/versions",null),200),"version/status/hash/stateVersion changed"),
     ()->assertEquals(beforeAudit,db.queryForObject("SELECT COUNT(*) FROM execution_events WHERE route_id=?",Long.class,id),"mutation audit was written"));
   assertError(response,422,"INVALID_REQUEST");
 }
 static java.util.stream.Stream<org.junit.jupiter.params.provider.Arguments> invalidScalars(){
   return java.util.stream.Stream.of(
     org.junit.jupiter.params.provider.Arguments.of("create","name","42"),
     org.junit.jupiter.params.provider.Arguments.of("create","name","true"),
     org.junit.jupiter.params.provider.Arguments.of("patch","name","42"),
     org.junit.jupiter.params.provider.Arguments.of("patch","name","true"),
     org.junit.jupiter.params.provider.Arguments.of("patch","enabled","\"false\""),
     org.junit.jupiter.params.provider.Arguments.of("patch","enabled","0"),
     org.junit.jupiter.params.provider.Arguments.of("patch","stateVersion","-0.9"),
     org.junit.jupiter.params.provider.Arguments.of("patch","stateVersion","0.9"),
     org.junit.jupiter.params.provider.Arguments.of("patch","stateVersion","0.0"),
     org.junit.jupiter.params.provider.Arguments.of("patch","stateVersion","\"0\""),
     org.junit.jupiter.params.provider.Arguments.of("patch","stateVersion","false"),
     org.junit.jupiter.params.provider.Arguments.of("patch","stateVersion","-1"),
     org.junit.jupiter.params.provider.Arguments.of("patch","stateVersion","9223372036854775808"),
     org.junit.jupiter.params.provider.Arguments.of("edit","stateVersion","-0.9"),
     org.junit.jupiter.params.provider.Arguments.of("edit","stateVersion","0.9"),
     org.junit.jupiter.params.provider.Arguments.of("edit","stateVersion","\"0\""),
     org.junit.jupiter.params.provider.Arguments.of("edit","stateVersion","false"),
     org.junit.jupiter.params.provider.Arguments.of("publish","stateVersion","-0.9"),
     org.junit.jupiter.params.provider.Arguments.of("publish","stateVersion","0.9"),
     org.junit.jupiter.params.provider.Arguments.of("publish","stateVersion","\"0\""),
     org.junit.jupiter.params.provider.Arguments.of("publish","stateVersion","false"));
 }
 @org.junit.jupiter.params.ParameterizedTest(name="{0} {1} returns {3}")
 @org.junit.jupiter.params.provider.CsvSource({
   "POST,/routes,text/plain,415,UNSUPPORTED_MEDIA_TYPE",
   "PUT,/routes,application/json,405,METHOD_NOT_ALLOWED",
   "GET,/missing-review-path,application/json,404,NOT_FOUND"
 })
 void AC008_frameworkClientErrorsKeepStatusHeadersAndEnvelope(String method,String path,String contentType,int expected,String code)throws Exception{
   long beforeRoutes=db.queryForObject("SELECT COUNT(*) FROM routes",Long.class);
   long beforeAudit=db.queryForObject("SELECT COUNT(*) FROM execution_events",Long.class);
   var request=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+path))
     .header("Authorization","Bearer "+token).header("Content-Type",contentType).header("X-Request-ID","test-request-123")
     .method(method,method.equals("GET")?HttpRequest.BodyPublishers.noBody():HttpRequest.BodyPublishers.ofString("{\"routeId\":\"must-not-create\",\"name\":\"DEMO\"}")).build();
   var response=http.send(request,HttpResponse.BodyHandlers.ofString());
   assertError(response,expected,code);
   if(expected==405){
     Set<String> allow=new HashSet<>();response.headers().allValues("Allow").forEach(value->Arrays.stream(value.split(",")).map(String::trim).forEach(allow::add));
     assertTrue(allow.containsAll(Set.of("GET","POST")),"Allow must retain supported methods: "+allow);
   }
   assertEquals(beforeRoutes,db.queryForObject("SELECT COUNT(*) FROM routes",Long.class));
   assertEquals(beforeAudit,db.queryForObject("SELECT COUNT(*) FROM execution_events",Long.class));
 }
 void assertError(HttpResponse<String> response,int expected,String code)throws Exception{
   var body=success(response,expected);Set<String> fields=new HashSet<>();body.fieldNames().forEachRemaining(fields::add);
   assertEquals(Set.of("code","message","requestId","timestamp"),fields);
   assertEquals(code,body.path("code").asText());assertEquals("test-request-123",body.path("requestId").asText());
   assertTrue(response.headers().firstValue("Content-Type").orElseThrow().startsWith("application/json"));
   assertTrue(body.path("timestamp").asText().endsWith("Z"));Instant.parse(body.path("timestamp").asText());
 }


 record MutationCase(String id,String method,String path,String body,int successStatus){}
 MutationCase mutationFixture(String action)throws Exception{
   String id=id();
   if(action.equals("create"))return new MutationCase(id,"POST","/routes","{\"routeId\":\""+id+"\",\"name\":\"DEMO HTTP boundary\"}",201);
   success(call("POST","/routes",object("{\"routeId\":\""+id+"\",\"name\":\"DEMO unchanged\"}")),201);
   if(Set.of("edit","publish","withdraw").contains(action))draft(id,1);
   long routeState=db.queryForObject("SELECT state_version FROM routes WHERE route_id=?",Long.class,id);
   var body=json.createObjectNode();
   return switch(action){
     case "patch"->new MutationCase(id,"PATCH","/routes/"+id,"{\"name\":\"must only persist on success\",\"enabled\":false,\"stateVersion\":"+routeState+"}",200);
     case "draft"->{body.set("definition",definition(id,1));yield new MutationCase(id,"POST","/routes/"+id+"/versions",body.toString(),201);}
     case "edit"->{var changed=definition(id,1);((ObjectNode)changed.get("root")).put("id","changedOnSuccess");body.set("definition",changed);body.put("stateVersion",0);yield new MutationCase(id,"PUT","/routes/"+id+"/versions/1",body.toString(),200);}
     case "publish"->new MutationCase(id,"POST","/routes/"+id+"/versions/1/publish","{\"stateVersion\":0}",200);
     case "delete"->new MutationCase(id,"DELETE","/routes/"+id+"?stateVersion="+routeState,null,200);
     case "withdraw"->new MutationCase(id,"DELETE","/routes/"+id+"/versions/1?stateVersion=0",null,200);
     default->throw new IllegalArgumentException(action);
   };
 }
 // Read complete persisted rows, including timestamps, state versions, definition hashes and audit contents.
 JsonNode persistedSnapshot(String id){
   var snapshot=json.createObjectNode();
   snapshot.set("route",json.valueToTree(db.queryForList("SELECT * FROM routes WHERE route_id=?",id)));
   snapshot.set("versions",json.valueToTree(db.queryForList("SELECT * FROM route_versions WHERE route_id=? ORDER BY version",id)));
   snapshot.set("audit",json.valueToTree(db.queryForList("SELECT * FROM execution_events WHERE route_id=? ORDER BY id",id)));
   return snapshot;
 }
 HttpResponse<String> rawCall(MutationCase mutation,String rawBody,String accept)throws Exception{
   var request=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+mutation.path()))
     .header("Authorization","Bearer "+token).header("Content-Type","application/json")
     .header("Accept",accept).header("X-Request-ID","test-request-123")
     .method(mutation.method(),rawBody==null?HttpRequest.BodyPublishers.noBody():HttpRequest.BodyPublishers.ofString(rawBody)).build();
   return http.send(request,HttpResponse.BodyHandlers.ofString());
 }
 @org.junit.jupiter.params.ParameterizedTest(name="{0} rejects trailing {1}")
 @org.junit.jupiter.params.provider.MethodSource("trailingJsonBodies")
 void AC008_singleJsonBodyRequiredBeforeMutation(String action,String suffix)throws Exception{
   var mutation=mutationFixture(action);var before=persistedSnapshot(mutation.id());
   // Append directly to HTTP bytes: never parse/re-serialize the malformed body through JsonNode.
   var response=rawCall(mutation,mutation.body()+suffix,"application/json");
   assertAll("a second root or trailing garbage must never commit",
     ()->assertError(response,422,"INVALID_REQUEST"),
     ()->assertEquals(before,persistedSnapshot(mutation.id()),"route/version/stateVersion/audit changed"));
 }
 static java.util.stream.Stream<org.junit.jupiter.params.provider.Arguments> trailingJsonBodies(){
   return java.util.stream.Stream.of("create","patch","draft","edit","publish").flatMap(action->
     java.util.stream.Stream.of("garbage"," {}").map(suffix->org.junit.jupiter.params.provider.Arguments.of(action,suffix)));
 }
 @org.junit.jupiter.params.ParameterizedTest(name="{0} negotiates Accept before any mutation")
 @org.junit.jupiter.params.provider.ValueSource(strings={"create","patch","draft","edit","publish","delete","withdraw"})
 void AC008_unacceptableResponseTypeNeverMutates(String action)throws Exception{
   var mutation=mutationFixture(action);var before=persistedSnapshot(mutation.id());
   var response=rawCall(mutation,mutation.body(),"image/png");
   assertAll("unacceptable representation must be rejected before transaction dispatch",
     ()->assertError(response,406,"NOT_ACCEPTABLE"),
     ()->assertEquals(before,persistedSnapshot(mutation.id()),"406 committed route/version/stateVersion/audit"));
 }
 @org.junit.jupiter.params.ParameterizedTest(name="all mutations accept {0}")
 @org.junit.jupiter.params.provider.ValueSource(strings={"application/json","application/*","*/*"})
 void AC008_jsonAndWildcardAcceptCommitNormally(String accept)throws Exception{
   for(String action:List.of("create","patch","draft","edit","publish","delete","withdraw")){
     var mutation=mutationFixture(action);var before=persistedSnapshot(mutation.id());
     String body=mutation.body()==null?null:mutation.body()+" \r\n\t";
     var response=rawCall(mutation,body,accept);
     success(response,mutation.successStatus());
     assertTrue(response.headers().firstValue("Content-Type").orElseThrow().startsWith("application/json"));
     var after=persistedSnapshot(mutation.id());
     assertNotEquals(before,after,action+" successful request did not mutate");
     assertEquals(before.path("audit").size()+1,after.path("audit").size(),action+" must commit exactly one audit event");
     switch(action){
       case "create"->assertEquals(1,after.path("route").size());
       case "patch"->{assertFalse(after.path("route").get(0).path("enabled").asBoolean());assertEquals(1,after.path("route").get(0).path("state_version").asLong());}
       case "draft"->assertEquals("DRAFT",after.path("versions").get(0).path("status").asText());
       case "edit"->assertEquals(1,after.path("versions").get(0).path("state_version").asLong());
       case "publish"->assertEquals("PUBLISHED",after.path("versions").get(0).path("status").asText());
       case "delete"->assertFalse(after.path("route").get(0).path("deleted_at").isNull());
       case "withdraw"->assertEquals(0,after.path("versions").size());
     }
   }
 }

}
