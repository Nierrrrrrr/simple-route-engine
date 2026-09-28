package dev.routeengine;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import dev.routeengine.registry.*;
import dev.routeengine.admission.AdmissionService;
import dev.routeengine.engine.EngineService;
import dev.routeengine.api.ApiProblem;
import java.nio.file.*;
import java.net.*;
import java.net.http.*;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;
import static org.junit.jupiter.api.Assertions.*;

/** Real HTTP and MariaDB: no mocked database or credential provider. */
@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT,properties={"route.scheduler.enabled=false","route.engine.enabled=false"})
class PersistenceGuardIT {
 static final String SECRET="synthetic-persistence-guard-917523";
 static final Path dir,credential,config;
 static {try{
  dir=Files.createTempDirectory(Path.of("target"),"persistence-guard-");credential=dir.resolve("credential");config=dir.resolve("catalog.json");
  Files.writeString(credential,SECRET);
  var j=new ObjectMapper();var c=j.createObjectNode();c.putObject("credentials").put("bound",credential.toAbsolutePath().toString()).put("unrelated",dir.resolve("unavailable-unrelated").toString());
  var endpoints=c.putObject("endpoints");for(String ref:List.of("guard","unrelated"))endpoints.putObject(ref).put("baseUri","http://127.0.0.1:9/operations").put("allowedHost","127.0.0.1").put("allowLoopbackHttp",true).put("timeoutMillis",100).put("maxResponseBytes",1024).put("credentialRef",ref.equals("guard")?"bound":"unrelated").put("query",true).put("cancel",true);
  Files.writeString(config,c.toString());
 }catch(Exception e){throw new ExceptionInInitializerError(e);}}
 @org.springframework.test.context.DynamicPropertySource static void properties(org.springframework.test.context.DynamicPropertyRegistry p){p.add("route.adapters.config",()->config.toAbsolutePath().toString());}
 @LocalServerPort int port;@Autowired ObjectMapper json;@Autowired JdbcTemplate db;@Autowired RouteRegistry registry;@Autowired PersistenceGuard guard;@Autowired TransactionTemplate tx;@Autowired AdmissionService admission;@Autowired EngineService engine;
 String route;final HttpClient client=HttpClient.newHttpClient();
 @BeforeEach void setup()throws Exception{Files.writeString(credential,SECRET);route="demo-protect-"+UUID.randomUUID().toString().substring(0,8);call("POST","/routes",json.createObjectNode().put("routeId",route).put("name","DEMO credential regression"),null,201);tx.executeWithoutResult(s->{db.queryForList("SELECT id FROM scheduler_pool WHERE id=1 FOR UPDATE");db.update("UPDATE admission_requests SET decision='WITHDRAWN' WHERE decision='QUEUED' AND recovery_payload IS NULL");db.update("UPDATE executions SET state='CANCELLED' WHERE state='QUEUED' AND permit_held=FALSE");db.update("UPDATE scheduler_pool SET total_slots=100000,critical_reserved=0,admission_enabled=TRUE WHERE id=1");});}
 @AfterEach void cleanup()throws Exception{Files.writeString(credential,SECRET);tx.executeWithoutResult(s->{db.queryForList("SELECT id FROM scheduler_pool WHERE id=1 FOR UPDATE");db.update("UPDATE admission_requests SET decision='WITHDRAWN' WHERE execution_id IN (SELECT id FROM executions WHERE route_id=?) AND decision='QUEUED'",route);db.update("UPDATE executions SET state='CANCELLED',permit_held=FALSE WHERE route_id=? AND NOT EXISTS (SELECT 1 FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE r.execution_id=executions.id)",route);});}
 @AfterAll static void files()throws Exception{Files.deleteIfExists(credential);Files.deleteIfExists(config);Files.deleteIfExists(dir);}
 ObjectNode definition(){var d=json.createObjectNode().put("routeId",route).put("version",1).put("dslVersion","1").put("engineSemanticsVersion","1").put("adapterContractVersion","1");d.putObject("root").put("id","root").put("type","SEQUENCE").putArray("children").addObject().put("id","send").put("type","REST").put("endpointRef","guard").putObject("input").put("value","business");return d;}
 ObjectNode input(ObjectNode d){return (ObjectNode)d.path("root").path("children").get(0).path("input");}
 String versions(){return "/routes/"+route+"/versions";}
 JsonNode call(String method,String path,JsonNode body,String key,int status)throws Exception{
  return envelopeCall(method,path,body,key,null,status);
 }
 JsonNode envelopeCall(String method,String path,JsonNode body,String key,String requestId,int status)throws Exception{
  var b=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+path)).header("Authorization","Bearer "+Objects.requireNonNull(System.getenv("ROUTE_TEST_TOKEN"))).header("Content-Type","application/json");if(key!=null)b.header("Idempotency-Key",key);if(requestId!=null)b.header("X-Request-ID",requestId);
  var result=client.send(b.method(method,body==null?HttpRequest.BodyPublishers.noBody():HttpRequest.BodyPublishers.ofString(body.toString())).build(),HttpResponse.BodyHandlers.ofString());
  assertEquals(status,result.statusCode(),"Unexpected API status; payload deliberately omitted");assertFalse(result.body().contains(SECRET));assertFalse(result.headers().map().toString().contains(SECRET));return json.readTree(result.body());
 }
 void draft(ObjectNode d)throws Exception{call("POST",versions(),json.createObjectNode().set("definition",d),null,201);}
 void publish()throws Exception{draft(definition());call("POST",versions()+"/1/publish",json.createObjectNode().put("stateVersion",0),null,200);}
 ObjectNode request(String mode,JsonNode value){return json.createObjectNode().put("routeId",route).put("priority","NORMAL").put("admissionMode",mode).set("input",value);}
 List<Object> snapshot(){return List.of(db.queryForList("SELECT * FROM routes WHERE route_id=?",route),db.queryForList("SELECT * FROM route_versions WHERE route_id=?",route),db.queryForList("SELECT * FROM executions WHERE route_id=?",route),db.queryForList("SELECT * FROM admission_requests"),db.queryForList("SELECT * FROM execution_events"),db.queryForList("SELECT * FROM scheduler_pool"));}
 @Test void AC041_draftAndEditRejectDecodedNestedCredentialWithoutMutation()throws Exception{
  var d=definition();input(d).putArray("value").addObject().put("inner",SECRET);var before=snapshot();call("POST",versions(),json.createObjectNode().set("definition",d),null,422);assertEquals(before,snapshot());
  input(d).put("value",SECRET);call("POST",versions(),json.createObjectNode().set("definition",d),null,422);assertEquals(before,snapshot());
  draft(definition());before=snapshot();var body=json.createObjectNode().put("stateVersion",0);body.set("definition",d);call("PUT",versions()+"/1",body,null,422);assertEquals(before,snapshot());
 }
 @Test void AC041_initialQueueAndNowRejectNestedAndScalarCredentialsWithoutMutation()throws Exception{
  publish();for(String mode:List.of("QUEUE","NOW_OR_REJECT")){var before=snapshot();var value=json.createObjectNode();value.putArray("value").addObject().put("inner",SECRET);call("POST","/executions",request(mode,value),UUID.randomUUID().toString(),422);assertEquals(before,snapshot());}
  var exact=snapshot();call("POST","/executions",request("QUEUE",json.createObjectNode().put("value",SECRET)),"exact-"+route,422);assertEquals(exact,snapshot());
  Files.writeString(credential,"917523");var before=snapshot();call("POST","/executions",request("QUEUE",json.createObjectNode().put("value",917523)),"numeric-"+route,422);assertEquals(before,snapshot());
  Files.writeString(credential,"true");before=snapshot();call("POST","/executions",request("NOW_OR_REJECT",json.createObjectNode().put("value",true)),"boolean-"+route,422);assertEquals(before,snapshot());
 }
 @Test void AC041_publishAndReadsFailClosedAfterCredentialRotationWithoutRewritingDraft()throws Exception{
  var d=definition();input(d).put("value","future-bound-value");draft(d);Files.writeString(credential,"future-bound-value");var before=snapshot();call("POST",versions()+"/1/publish",json.createObjectNode().put("stateVersion",0),null,422);call("GET",versions()+"/1",null,null,422);call("GET",versions(),null,null,422);assertEquals(before,snapshot());
 }
 @Test void AC041_unavailableDraftEditPublishAndPublishedReadFailClosed()throws Exception{
  draft(definition());Files.delete(credential);var before=snapshot();var edit=json.createObjectNode().put("stateVersion",0);edit.set("definition",definition());call("PUT",versions()+"/1",edit,null,503);call("POST",versions()+"/1/publish",json.createObjectNode().put("stateVersion",0),null,503);assertEquals(before,snapshot());
  Files.writeString(credential,SECRET);call("POST",versions()+"/1/publish",json.createObjectNode().put("stateVersion",0),null,200);call("GET",versions()+"/1",null,null,200);Files.delete(credential);before=snapshot();call("GET",versions()+"/1",null,null,503);assertEquals(before,snapshot());
  Files.writeString(credential,"business");before=snapshot();call("GET",versions()+"/1",null,null,422);call("POST","/executions",request("QUEUE",json.createObjectNode()),"unsafe-version-"+route,422);assertEquals(before,snapshot());
 }
 @Test void AC041_unavailableRelevantCredentialRejectsWritesButOriginalDecisionReplays()throws Exception{
  publish();var req=request("QUEUE",json.createObjectNode().put("value","business"));var accepted=call("POST","/executions",req,"replay-"+route,202);Files.delete(credential);var before=snapshot();
  call("POST","/executions",req,"new-"+route,503);assertEquals(accepted,call("POST","/executions",req,"replay-"+route,202));assertEquals(before,snapshot());
  var d=definition().put("version",2);call("POST",versions(),json.createObjectNode().set("definition",d),null,503);assertEquals(before,snapshot());
 }
 @Test void AC041_originalRejectedDecisionReplaysWithoutCredentialAndContentMismatchConflicts()throws Exception{
  publish();tx.executeWithoutResult(s->{db.queryForList("SELECT id FROM scheduler_pool WHERE id=1 FOR UPDATE");db.update("UPDATE scheduler_pool SET admission_enabled=FALSE WHERE id=1");});
  var req=request("NOW_OR_REJECT",json.createObjectNode().put("value","business"));var rejected=call("POST","/executions",req,"rejected-"+route,409);assertEquals("ADMISSION_REJECTED",rejected.path("code").asText());Files.delete(credential);var before=snapshot();
  assertEquals(rejected,call("POST","/executions",req,"rejected-"+route,409));req.put("priority","HIGH");assertEquals("IDEMPOTENCY_CONFLICT",call("POST","/executions",req,"rejected-"+route,409).path("code").asText());assertEquals(before,snapshot());
 }
 @Test void AC041_latestVersionRaceRechecksUnderPoolLockAndRetryUsesNewContext()throws Exception{
  publish();var req=request("QUEUE",json.createObjectNode().put("value","business"));
  try(var lock=db.getDataSource().getConnection();var executor=java.util.concurrent.Executors.newVirtualThreadPerTaskExecutor()){
   lock.setAutoCommit(false);lock.createStatement().executeQuery("SELECT id FROM scheduler_pool WHERE id=1 FOR UPDATE").close();
   var response=executor.submit(()->call("POST","/executions",req,"latest-race-"+route,409));
   long end=System.nanoTime()+java.time.Duration.ofSeconds(10).toNanos();boolean waiting=false;
   while(System.nanoTime()<end){waiting=db.queryForObject("SELECT COUNT(*) FROM information_schema.PROCESSLIST WHERE LOCATE('scheduler_pool',INFO)>0 AND LOCATE('FOR UPDATE',INFO)>0 AND LOCATE('PROCESSLIST',INFO)=0",Integer.class)>0;if(waiting)break;Thread.sleep(10);}
   assertTrue(waiting,"Submission must reach the real pool lock before publishing a new default; response finished="+response.isDone());
   var d=definition().put("version",2);registry.draft(route,d,"test","race");registry.publish(route,2,0,"test","race");var before=snapshot();lock.commit();response.get(15,java.util.concurrent.TimeUnit.SECONDS);assertEquals(before,snapshot());
  }
  assertEquals(2,call("POST","/executions",req,"latest-race-"+route,202).path("routeVersion").asInt());
 }
 @Test void AC041_typedBusinessInputsAndUnrelatedUnavailableCredentialRemainValid()throws Exception{
  var d=definition();d.set("inputSchema",json.readTree("{\"type\":\"object\",\"properties\":{\"value\":{\"type\":\"integer\"},\"flag\":{\"type\":\"boolean\"}},\"required\":[\"value\",\"flag\"]}"));draft(d);call("POST",versions()+"/1/publish",json.createObjectNode().put("stateVersion",0),null,200);
  var value=json.createObjectNode().put("value",42).put("flag",true);var result=call("POST","/executions",request("NOW_OR_REJECT",value),"typed-"+route,202);assertEquals("ADMITTED",result.path("decision").asText());assertEquals(value,json.readTree(db.queryForObject("SELECT input_json FROM executions WHERE id=?",String.class,result.path("executionId").asText())));
 }
 @Test void AC041_exactContextRecheckRejectsChangedDefinitionAndPayload()throws Exception{
  draft(definition());var d=registry.getVersion(route,1).definition();var empty=json.createObjectNode();var prepared=guard.prepare(d,null,empty);var replacement=definition();input(replacement).put("value","different");registry.edit(route,1,replacement,0,"test","context-race");var before=snapshot();
  assertThrows(ApiProblem.class,()->tx.executeWithoutResult(s->{db.queryForList("SELECT route_id FROM routes WHERE route_id=? FOR UPDATE",route);guard.recheck(prepared,registry.getVersion(route,1).definition(),null,empty);}));assertEquals(before,snapshot());
  assertThrows(ApiProblem.class,()->guard.recheck(prepared,d,null,json.createObjectNode().put("value","changed")));
 }
 @Test void AC041_credentialBearingPreparationInsideTransactionIsForbidden()throws Exception{
  var before=snapshot();assertThrows(IllegalStateException.class,()->tx.executeWithoutResult(s->guard.prepare(definition(),null,json.createObjectNode())));assertEquals(before,snapshot());
 }
 @Test void AC041_rollbackAndNotificationCredentialsAreRelevant()throws Exception{
  var d=definition();var leaf=(ObjectNode)d.path("root").path("children").get(0);leaf.put("endpointRef","not-yet-deployed");leaf.putObject("rollback").put("id","undo").put("type","REST").put("endpointRef","guard");input(d).put("value",SECRET);var before=snapshot();call("POST",versions(),json.createObjectNode().set("definition",d),null,422);assertEquals(before,snapshot());
  leaf.remove("rollback");leaf.putObject("onFailure").put("endpointRef","guard").put("maxAttempts",1);call("POST",versions(),json.createObjectNode().set("definition",d),null,422);assertEquals(before,snapshot());
 }
 @Test void AC041_historicalUnsafeQueueAndClaimHoldStateWithoutCopyingOrRelease()throws Exception{
  publish();var value=json.createObjectNode().put("value","future-input-value");var queued=call("POST","/executions",request("QUEUE",value),"history-queue-"+route,202);Files.writeString(credential,"future-input-value");var before=snapshot();assertThrows(ApiProblem.class,()->admission.tick());assertEquals(before,snapshot());
  Files.writeString(credential,SECRET);tx.executeWithoutResult(s->{db.queryForList("SELECT id FROM scheduler_pool WHERE id=1 FOR UPDATE");db.update("UPDATE admission_requests SET decision='WITHDRAWN' WHERE execution_id=?",queued.path("executionId").asText());db.update("UPDATE executions SET state='CANCELLED' WHERE id=?",queued.path("executionId").asText());});
  var started=call("POST","/executions",request("NOW_OR_REJECT",value),"history-claim-"+route,202);Files.writeString(credential,"future-input-value");before=snapshot();String id=started.path("executionId").asText();assertThrows(ApiProblem.class,()->engine.claim(id));assertEquals(before,snapshot());assertEquals(0,db.queryForObject("SELECT COUNT(*) FROM step_runs WHERE execution_id=?",Integer.class,id));assertEquals(1,db.queryForObject("SELECT permit_held FROM executions WHERE id=?",Integer.class,id));
 }
 @Test void AC041_alreadyInitializedHistoricalInputCannotAdvanceAfterCredentialRotation()throws Exception{
  publish();var started=call("POST","/executions",request("NOW_OR_REJECT",json.createObjectNode().put("value","future-running-value")),"history-running-"+route,202);String id=started.path("executionId").asText();assertNotNull(engine.claim(id));
  Files.writeString(credential,"future-running-value");var before=snapshot();var steps=db.queryForList("SELECT * FROM step_runs WHERE execution_id=?",id);assertThrows(ApiProblem.class,()->engine.claim(id));assertEquals(before,snapshot());assertEquals(steps,db.queryForList("SELECT * FROM step_runs WHERE execution_id=?",id));assertEquals(1,db.queryForObject("SELECT permit_held FROM executions WHERE id=?",Integer.class,id));
 }

 @Test void AC041_initialEnvelopeRejectsKeyAndRequestIdBeforeQueueAdmittedOrRejectedDecision()throws Exception{
  publish();for(boolean enabled:List.of(true,false)){
   db.update("UPDATE scheduler_pool SET admission_enabled=? WHERE id=1",enabled);
   for(String mode:List.of("QUEUE","NOW_OR_REJECT"))for(boolean key:List.of(true,false)){
    var before=snapshot();envelopeCall("POST","/executions",request(mode,json.createObjectNode().put("value","business")),key?SECRET:"safe-"+UUID.randomUUID(),key?"safe-request":SECRET,422);assertEquals(before,snapshot());
   }
  }
 }
 @Test void AC041_versionEnvelopeRejectsEveryMutationAndOldEditContext()throws Exception{
  var draftBody=json.createObjectNode().set("definition",definition());var before=snapshot();envelopeCall("POST",versions(),draftBody,null,SECRET,422);assertEquals(before,snapshot());
  draft(definition());var edit=json.createObjectNode().put("stateVersion",0);var replacement=definition();((ObjectNode)replacement.path("root").path("children").get(0)).put("endpointRef","not-yet-deployed");edit.set("definition",replacement);before=snapshot();
  envelopeCall("PUT",versions()+"/1",edit,null,SECRET,422);assertEquals(before,snapshot());
  envelopeCall("POST",versions()+"/1/publish",json.createObjectNode().put("stateVersion",0),null,SECRET,422);assertEquals(before,snapshot());
  envelopeCall("DELETE",versions()+"/1?stateVersion=0",null,null,SECRET,422);assertEquals(before,snapshot());
  envelopeCall("DELETE",versions()+"/1?stateVersion=0",null,null,"safe-withdraw",200);
 }
 @Test void AC041_routeMetadataEnvelopeUsesExistingVersionContextAndProtectsName()throws Exception{
  publish();long state=registry.get(route).stateVersion();var update=json.createObjectNode().put("name","safe name").put("enabled",true).put("stateVersion",state);var before=snapshot();
  envelopeCall("PATCH","/routes/"+route,update,null,SECRET,422);assertEquals(before,snapshot());
  envelopeCall("DELETE","/routes/"+route+"?stateVersion="+state,null,null,SECRET,422);assertEquals(before,snapshot());
  update.put("name",SECRET);envelopeCall("PATCH","/routes/"+route,update,null,"safe-request",422);assertEquals(before,snapshot());
  update.put("name","safe name");envelopeCall("PATCH","/routes/"+route,update,null,"safe-update",200);
  envelopeCall("DELETE","/routes/"+route+"?stateVersion="+(state+1),null,null,"safe-delete",200);
 }
 @Test void AC041_envelopeUnavailableContextFailsClosedAndDurableReplayIgnoresNewHeaders()throws Exception{
  publish();var req=request("QUEUE",json.createObjectNode());var accepted=envelopeCall("POST","/executions",req,"safe-original-"+route,"safe-request",202);Files.delete(credential);var before=snapshot();
  envelopeCall("POST","/executions",req,"safe-new-"+route,SECRET,503);assertEquals(before,snapshot());
  // Replay neither persists nor validates a new envelope; use a normal request correlation header.
  assertEquals(accepted,envelopeCall("POST","/executions",req,"safe-original-"+route,"new-safe-request",202));assertEquals(before,snapshot());
  long state=registry.get(route).stateVersion();envelopeCall("DELETE","/routes/"+route+"?stateVersion="+state,null,null,SECRET,503);assertEquals(before,snapshot());
 }
 @Test void AC041_routeEnvelopeContextRaceRejectsNewVersionSetUnderRouteLock()throws Exception{
  draft(definition());long state=registry.get(route).stateVersion();var update=json.createObjectNode().put("name","race safe").put("enabled",true).put("stateVersion",state);
  try(var lock=db.getDataSource().getConnection();var executor=java.util.concurrent.Executors.newVirtualThreadPerTaskExecutor()){
   lock.setAutoCommit(false);try(var ps=lock.prepareStatement("SELECT route_id FROM routes WHERE route_id=? FOR UPDATE")){ps.setString(1,route);ps.executeQuery().close();}
   var response=executor.submit(()->envelopeCall("PATCH","/routes/"+route,update,null,"safe-race",409));long end=System.nanoTime()+java.time.Duration.ofSeconds(10).toNanos();boolean waiting=false;
   while(System.nanoTime()<end){waiting=db.queryForObject("SELECT COUNT(*) FROM information_schema.PROCESSLIST WHERE LOCATE('FROM routes',INFO)>0 AND LOCATE('FOR UPDATE',INFO)>0 AND LOCATE('PROCESSLIST',INFO)=0",Integer.class)>0;if(waiting)break;Thread.sleep(10);}assertTrue(waiting);
   // A concurrent committed draft edit changes credential context without changing route metadata CAS.
   var changed=definition();input(changed).put("value","changed business");try(var ps=lock.prepareStatement("UPDATE route_versions SET definition_json=?,state_version=state_version+1 WHERE route_id=? AND version=1")){ps.setString(1,changed.toString());ps.setString(2,route);assertEquals(1,ps.executeUpdate());}lock.commit();
   response.get(15,java.util.concurrent.TimeUnit.SECONDS);assertEquals("DEMO credential regression",registry.get(route).name());assertEquals(state,registry.get(route).stateVersion());
  }
  envelopeCall("PATCH","/routes/"+route,update,null,"safe-retry",200);
 }
}
