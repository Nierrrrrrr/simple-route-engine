package dev.routeengine;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import dev.routeengine.admission.AdmissionService;
import dev.routeengine.engine.EngineService;
import dev.routeengine.registry.RouteRegistry;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import java.util.*;
import java.net.*;
import java.net.http.*;
import java.time.Duration;
import java.util.function.BooleanSupplier;
import static org.junit.jupiter.api.Assertions.*;
/** Explicit M4 suite, invoked by adapter gate with a fresh real MariaDB and HTTP fixture. */
@SpringBootTest(properties={"route.scheduler.enabled=false","route.engine.enabled=false"})
class RestEngineAcceptance {
 @Autowired ObjectMapper json;@Autowired JdbcTemplate db;@Autowired RouteRegistry routes;@Autowired AdmissionService admission;@Autowired EngineService engine;
 String leaf(String id,String ref){return "{\"id\":\""+id+"\",\"type\":\"REST\",\"endpointRef\":\""+ref+"\"}";}
 String start(String children)throws Exception{
  String route="demo-adapter-"+UUID.randomUUID().toString().substring(0,8);routes.create(route,"DEMO M4","test","m4");
  var d=json.readTree("{\"routeId\":\""+route+"\",\"version\":1,\"dslVersion\":\"1\",\"engineSemanticsVersion\":\"1\",\"adapterContractVersion\":\"1\",\"root\":{\"id\":\"root\",\"type\":\"SEQUENCE\",\"children\":"+children+"}}");
  routes.draft(route,d,"test","m4");routes.publish(route,1,0,"test","m4");
  var result=admission.submit("test",UUID.randomUUID().toString(),new AdmissionService.Request(route,1,"CRITICAL","NOW_OR_REJECT",json.createObjectNode()),"m4");
  assertEquals(202,result.status());assertEquals("ADMITTED",result.body().path("decision").asText());return result.body().path("executionId").asText();
 }
 String state(String id){return db.queryForObject("SELECT CONCAT(state,':',permit_held) FROM executions WHERE id=?",String.class,id);}
 String op(String id,String node){return db.queryForObject("SELECT a.operation_id FROM step_attempts a JOIN step_runs s ON s.id=a.step_run_id WHERE s.execution_id=? AND s.node_id=? ORDER BY attempt_number DESC LIMIT 1",String.class,id,node);}
 void waitState(String id,String expected)throws Exception{long end=System.nanoTime()+Duration.ofSeconds(25).toNanos();while(System.nanoTime()<end){engine.tick(id);if(state(id).equals(expected))return;Thread.sleep(60);}assertEquals(expected,state(id));}
 JsonNode remote(String path)throws Exception{return json.readTree(HttpClient.newHttpClient().send(HttpRequest.newBuilder(URI.create(Objects.requireNonNull(System.getenv("ROUTE_HTTP_FIXTURE"))+path)).GET().build(),HttpResponse.BodyHandlers.ofString()).body());}
 @Test void AC032_intentPlanCommitsBeforeRealHttpAndAcceptedPollKeepsPermit()throws Exception{
  String id=start("["+leaf("work","async")+"]");var work=engine.claim(id);assertNotNull(work);
  assertEquals(work.request().operationId(),op(id,"work"));assertFalse(work.request().context().path("catalogHash").asText().isBlank());
  assertEquals(0,remote("/stats").path("effects").path(work.request().operationId()).asInt());
  assertTrue(engine.execute(work));assertTrue(state(id).endsWith(":1"));assertEquals("WAITING_EXTERNAL",db.queryForObject("SELECT state FROM step_runs WHERE id=?",String.class,work.stepId()));
  remote("/complete/"+work.request().operationId());waitState(id,"SUCCEEDED:0");
  assertEquals(1,remote("/stats").path("effects").path(work.request().operationId()).asInt());
 }
 @Test void AC034_unknownWithoutQueryKeepsPermitIncidentAndNeverResubmits()throws Exception{
  String id=start("["+leaf("unknown","unsafe")+","+leaf("unsafeNext","sync")+"]");engine.tick(id);String operation=op(id,"unknown");
  for(int i=0;i<3;i++){Thread.sleep(1050);engine.tick(id);}
  assertEquals("RECONCILING:1",state(id));
  assertEquals(1,db.queryForObject("SELECT COUNT(*) FROM engine_incidents WHERE execution_id=? AND kind='IN_DOUBT' AND status='OPEN'",Integer.class,id));
  assertEquals(0,db.queryForObject("SELECT COUNT(*) FROM step_runs WHERE execution_id=? AND node_id='unsafeNext'",Integer.class,id));
  assertEquals(1,remote("/stats").path("effects").path(operation).asInt());
  assertEquals(1,db.queryForObject("SELECT attempt_count FROM step_runs WHERE execution_id=? AND node_id='unknown'",Integer.class,id));
 }
 @Test void AC039_businessRetryGetsNewGenerationAndOperation()throws Exception{
  var node=(ObjectNode)json.readTree(leaf("work","flaky"));node.putObject("retry").put("maxAttempts",2).put("maxElapsedSeconds",60).put("backoffSeconds",0);
  String id=start("["+node+"]");waitState(id,"SUCCEEDED:0");
  var attempts=db.queryForList("SELECT a.* FROM step_attempts a JOIN step_runs s ON s.id=a.step_run_id WHERE s.execution_id=? ORDER BY attempt_number",id);
  assertEquals(2,attempts.size());assertNotEquals(attempts.get(0).get("operation_id"),attempts.get(1).get("operation_id"));
  assertEquals(List.of(1L,2L),attempts.stream().map(a->((Number)a.get("operation_generation")).longValue()).toList());
  for(var a:attempts)assertEquals(1,remote("/stats").path("effects").path(a.get("operation_id").toString()).asInt());
 }
 @Test void AC040_notificationRetriesAreFiniteAndDoNotReplaceMainIncident()throws Exception{
  var node=(ObjectNode)json.readTree(leaf("work","failure"));node.putObject("onFailure").put("endpointRef","notify-fail").put("maxAttempts",3);
  String id=start("["+node+","+leaf("never","sync")+"]");engine.tick(id);
  assertEquals("PAUSING:1",state(id));assertEquals(1,db.queryForObject("SELECT COUNT(*) FROM engine_incidents WHERE execution_id=? AND kind='KNOWN_FAILURE'",Integer.class,id));
  waitState(id,"MANUAL_WAIT:0");
  assertEquals(1,db.queryForObject("SELECT COUNT(*) FROM step_runs WHERE execution_id=? AND is_notification=TRUE",Integer.class,id));
  assertEquals(3,db.queryForObject("SELECT attempt_count FROM step_runs WHERE execution_id=? AND is_notification=TRUE",Integer.class,id));
  assertEquals(1,db.queryForObject("SELECT COUNT(*) FROM engine_incidents WHERE execution_id=?",Integer.class,id));
  assertEquals(0,db.queryForObject("SELECT COUNT(*) FROM step_runs WHERE execution_id=? AND node_id='never'",Integer.class,id));
 }
 @Test void AC038_cancelPendingNotificationBeforeItStarts()throws Exception{
  var node=(ObjectNode)json.readTree(leaf("work","failure"));node.putObject("onFailure").put("endpointRef","notify-ok").put("maxAttempts",2);
  String id=start("["+node+"]");engine.tick(id);assertEquals("PAUSING:1",state(id));
  String notice=db.queryForObject("SELECT id FROM step_runs WHERE execution_id=? AND is_notification=TRUE",String.class,id);
  assertEquals("PENDING",db.queryForObject("SELECT state FROM step_runs WHERE id=?",String.class,notice));
  engine.requestCancel(id,"test-operator","Cancel not-yet-dispatched notification");
  waitState(id,"CANCELLED:0");
  assertEquals("STOPPED",db.queryForObject("SELECT state FROM step_runs WHERE id=?",String.class,notice));
  assertEquals(0,db.queryForObject("SELECT COUNT(*) FROM step_attempts WHERE step_run_id=?",Integer.class,notice));
 }
 @Test void AC040_notificationSuccessConvergesBeforePermitRelease()throws Exception{
  var node=(ObjectNode)json.readTree(leaf("work","failure"));node.putObject("onFailure").put("endpointRef","notify-ok").put("maxAttempts",2);
  String id=start("["+node+"]");engine.tick(id);assertEquals("PAUSING:1",state(id));waitState(id,"MANUAL_WAIT:0");
  assertEquals("SUCCEEDED",db.queryForObject("SELECT state FROM step_runs WHERE execution_id=? AND is_notification=TRUE",String.class,id));
 }
}
