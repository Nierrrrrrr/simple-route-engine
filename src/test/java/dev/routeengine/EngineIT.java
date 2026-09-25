package dev.routeengine;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import dev.routeengine.admission.AdmissionService;
import dev.routeengine.registry.RouteRegistry;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties={"route.scheduler.enabled=false","route.engine.enabled=false","route.engine.development=true","route.engine.fixture-directory=target/engine-fixture"})
@org.springframework.test.context.ActiveProfiles("engine-development")
class EngineIT {
 @org.springframework.test.context.DynamicPropertySource
 static void engineDatabase(org.springframework.test.context.DynamicPropertyRegistry properties){
  for(String key:List.of("URL","USER","PASSWORD")){
   String value=Objects.requireNonNull(System.getenv("ROUTE_ENGINE_TEST_DB_"+key),"Missing dedicated engine test database "+key);
   properties.add("spring.datasource."+switch(key){case "URL"->"url";case "USER"->"username";default->"password";},()->value);
  }
 }
 @Autowired ObjectMapper json; @Autowired JdbcTemplate db; @Autowired RouteRegistry routes;
 @Autowired AdmissionService admission; @Autowired ApplicationContext context;
 @Autowired org.springframework.transaction.support.TransactionTemplate transaction;
 @Autowired TestClock domainClock;
 static class TestClock extends java.time.Clock {
  volatile java.time.Instant now=java.time.Instant.now();
  public java.time.ZoneId getZone(){return java.time.ZoneOffset.UTC;}
  public java.time.Clock withZone(java.time.ZoneId zone){return this;}
  public java.time.Instant instant(){return now;}
 }
 @org.springframework.boot.test.context.TestConfiguration
 static class ClockConfiguration {
  @org.springframework.context.annotation.Bean @org.springframework.context.annotation.Primary
  TestClock testClock(){return new TestClock();}
 }
 @BeforeEach void resetClock(){domainClock.now=java.time.Instant.now();}
 @AfterEach void retireOnlyEngineTestFixtures(){
  transaction.executeWithoutResult(s->{
   db.queryForList("SELECT id FROM scheduler_pool WHERE id=1 FOR UPDATE");
   db.update("UPDATE step_attempts a JOIN step_runs r ON r.id=a.step_run_id JOIN executions e ON e.id=r.execution_id SET a.state='STOPPED' WHERE e.route_id LIKE 'demo-engine-%' AND a.state NOT IN ('SUCCEEDED','FAILED','STOPPED','CANCELLED')");
   db.update("UPDATE step_runs r JOIN executions e ON e.id=r.execution_id SET r.state='STOPPED' WHERE e.route_id LIKE 'demo-engine-%' AND r.state NOT IN ('SUCCEEDED','FAILED','STOPPED','SKIPPED','CANCELLED')");
   db.update("UPDATE executions SET permit_held=FALSE,state='CANCELLED' WHERE route_id LIKE 'demo-engine-%' AND permit_held=TRUE");
  });
 }
 Object engine(){return context.getBean("engineService");}
 Object invoke(String method,String id)throws Exception{return engine().getClass().getMethod(method,String.class).invoke(engine(),id);}
 JsonNode parse(String s)throws Exception{return json.readTree(s);}
 long count(String q,Object... a){return db.queryForObject(q,Long.class,a);}
 String state(String id){return db.queryForObject("SELECT state FROM executions WHERE id=?",String.class,id);}
 String start(String children)throws Exception{
  String route="demo-engine-"+UUID.randomUUID().toString().substring(0,8);
  routes.create(route,"DEMO engine","tester","engine-test");
  var d=parse("{\"routeId\":\""+route+"\",\"version\":1,\"dslVersion\":\"1\",\"engineSemanticsVersion\":\"1\",\"adapterContractVersion\":\"1\",\"root\":{\"id\":\"root\",\"type\":\"SEQUENCE\",\"children\":"+children+"}}");
  routes.draft(route,d,"tester","test");routes.publish(route,1,0,"tester","test");
  var result=admission.submit("tester",UUID.randomUUID().toString(),new AdmissionService.Request(route,1,"CRITICAL","NOW_OR_REJECT",json.createObjectNode()),"test");
  assertEquals(202,result.status(),()->"Engine fixture admission failed: "+result.body());
  assertEquals("ADMITTED",result.body().path("decision").asText(),()->"Engine fixture admission: "+result.body());
  assertTrue(result.body().path("executionId").isTextual(),()->"Missing engine execution: "+result.body());
  assertFalse(result.body().path("executionId").asText().isBlank());
  return result.body().path("executionId").asText();
 }
 String leaf(String id,String ref){return "{\"id\":\""+id+"\",\"type\":\"REST\",\"endpointRef\":\""+ref+"\",\"input\":{\"value\":\""+id+"\"}}";}
 void tick(String id)throws Exception{invoke("tick",id);}
 @Test void AC023_resultAndNextPendingAtomicAndInitializationUnique()throws Exception{
  String id=start("["+leaf("one","dev.success")+","+leaf("two","dev.success")+"]");
  tick(id);assertEquals("SUCCEEDED",db.queryForObject("SELECT state FROM step_runs WHERE execution_id=? AND node_id='one'",String.class,id));
  assertEquals("PENDING",db.queryForObject("SELECT state FROM step_runs WHERE execution_id=? AND node_id='two'",String.class,id));
  tick(id);tick(id);assertEquals("SUCCEEDED",state(id));assertEquals(0,count("SELECT permit_held FROM executions WHERE id=?",id));
  assertEquals(3,count("SELECT COUNT(*) FROM step_runs WHERE execution_id=?",id));assertEquals(2,count("SELECT COUNT(*) FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE execution_id=?",id));
 }
 @Test void AC025_AC027_failureWaitsForStartedSiblingAndStopsFollowingStep()throws Exception{
  String id=start("[{\"id\":\"parallel\",\"type\":\"PARALLEL\",\"join\":\"ALL_SETTLED\",\"branches\":["+leaf("slow","dev.pending")+","+leaf("bad","dev.fail")+"]},"+leaf("later","dev.success")+"]");
  tick(id);tick(id);assertEquals(1,count("SELECT permit_held FROM executions WHERE id=?",id));
  assertNotEquals("MANUAL_WAIT",state(id));assertEquals(0,count("SELECT COUNT(*) FROM step_runs WHERE execution_id=? AND node_id='later'",id));
 }
 @Test void AC026_retryDuePolicyPersistedAndPermitHeld()throws Exception{
  var n=(ObjectNode)parse(leaf("retry","dev.flaky"));n.set("retry",parse("{\"maxAttempts\":2,\"maxElapsedSeconds\":21600,\"backoffSeconds\":10}"));
  String id=start("["+n+"]");tick(id);assertEquals("RETRY_WAIT",state(id));
  assertEquals(1,count("SELECT permit_held FROM executions WHERE id=?",id));
  assertEquals(2,count("SELECT max_attempts FROM step_runs WHERE execution_id=? AND node_id='retry'",id));
  tick(id);assertEquals(1,count("SELECT COUNT(*) FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE execution_id=?",id));
 }
 @Test void AC030_unknownRetainsPermitAndNeverResubmits()throws Exception{
  String id=start("["+leaf("unknown","dev.unknown")+","+leaf("later","dev.success")+"]");
  tick(id);for(int i=0;i<4;i++)tick(id);assertEquals("RECONCILING",state(id));
  assertEquals(1,count("SELECT permit_held FROM executions WHERE id=?",id));
  assertEquals(1,count("SELECT COUNT(*) FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE execution_id=?",id));
  assertEquals(0,count("SELECT COUNT(*) FROM step_runs WHERE execution_id=? AND node_id='later'",id));
 }
 @Test void AC029_exceptionInOneExecutionDoesNotStopOtherExecution()throws Exception{
  String bad=start("["+leaf("throws","dev.throw")+"]"),good=start("["+leaf("ok","dev.success")+"]");
  assertDoesNotThrow(()->tick(bad));tick(good);assertEquals("SUCCEEDED",state(good));assertEquals("RECONCILING",state(bad));
 }
 @Test void AC028_twoExecutionsKeepIndependentResolvedInputAndOutput()throws Exception{
  String a=start("["+leaf("a","dev.success")+"]"),b=start("["+leaf("b","dev.success")+"]");tick(a);tick(b);
  assertEquals("a",parse(db.queryForObject("SELECT output_json FROM step_runs WHERE execution_id=? AND node_id='a'",String.class,a)).path("value").asText());
  assertEquals("b",parse(db.queryForObject("SELECT output_json FROM step_runs WHERE execution_id=? AND node_id='b'",String.class,b)).path("value").asText());
 }

 dev.routeengine.engine.EngineService service(){return (dev.routeengine.engine.EngineService)engine();}
 void finishPending(String id,String node)throws Exception{
  String operation=db.queryForObject("SELECT a.operation_id FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE r.execution_id=? AND r.node_id=? ORDER BY a.attempt_number DESC LIMIT 1",String.class,id,node);
  java.nio.file.Files.writeString(java.nio.file.Path.of("target/engine-fixture",operation+".result.json"),"{\"status\":\"SUCCEEDED\",\"output\":{\"done\":true}}");
  db.update("UPDATE step_runs SET next_action_at=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE execution_id=? AND node_id=?",id,node);
 }
 @Test void AC023_completionRollbackLeavesNeitherResultNextPendingNorEvent()throws Exception{
  String id=start("["+leaf("a","dev.success")+","+leaf("b","dev.success")+"]");
  var work=service().claim(id);assertNotNull(work);
  var outcome=new dev.routeengine.engine.OperationAdapter.Outcome(dev.routeengine.engine.OperationAdapter.Status.SUCCEEDED,parse("{\"value\":\"a\"}"),false,null);
  long events=count("SELECT COUNT(*) FROM execution_events WHERE execution_id=?",id);
  assertThrows(IllegalStateException.class,()->transaction.executeWithoutResult(s->{assertTrue(service().complete(work,outcome));throw new IllegalStateException("test rollback");}));
  assertEquals("RUNNING",db.queryForObject("SELECT state FROM step_runs WHERE id=?",String.class,work.stepId()));
  assertEquals(0,count("SELECT COUNT(*) FROM step_runs WHERE execution_id=? AND node_id='b'",id));
  assertEquals(events,count("SELECT COUNT(*) FROM execution_events WHERE execution_id=?",id));
  assertTrue(service().complete(work,outcome));assertEquals(1,count("SELECT COUNT(*) FROM step_runs WHERE execution_id=? AND node_id='b' AND state='PENDING'",id));
 }
 @Test void AC024_choicesInputsAndTypedOutputsRemainDurable()throws Exception{
  String producer="{\"id\":\"produce\",\"type\":\"REST\",\"endpointRef\":\"dev.success\",\"input\":{\"flag\":true},\"outputSchema\":{\"type\":\"object\",\"properties\":{\"flag\":{\"type\":\"boolean\"}},\"required\":[\"flag\"]}}";
  String condition="{\"id\":\"choice\",\"type\":\"CONDITION\",\"condition\":{\"field\":\"steps.produce.flag\",\"operator\":\"EQ\",\"value\":true},\"then\":"+leaf("yes","dev.pending")+",\"else\":"+leaf("no","dev.success")+"}";
  String id=start("["+producer+","+condition+"]");tick(id);tick(id);
  assertEquals("then",db.queryForObject("SELECT branch_choice FROM step_runs WHERE execution_id=? AND node_id='choice'",String.class,id));
  assertEquals(0,count("SELECT COUNT(*) FROM step_runs WHERE execution_id=? AND node_id='no'",id));
  finishPending(id,"yes");tick(id);assertEquals("SUCCEEDED",state(id));
  assertEquals("{\"value\":\"yes\"}",db.queryForObject("SELECT input_json FROM step_runs WHERE execution_id=? AND node_id='yes'",String.class,id));
  var when=(ObjectNode)parse(leaf("skipped","dev.success"));when.set("when",parse("{\"field\":\"steps.produce.flag\",\"operator\":\"EQ\",\"value\":false}"));
  String other=start("["+producer+","+when+"]");tick(other);assertEquals("SUCCEEDED",state(other));
  assertEquals("false",db.queryForObject("SELECT branch_choice FROM step_runs WHERE execution_id=? AND node_id='skipped'",String.class,other));
  assertEquals(1,count("SELECT COUNT(*) FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE execution_id=?",other));
 }
 @Test void AC025_successfulSiblingDoesNotRepeatDuringBoundedBranchRetryAndJoinMerges()throws Exception{
  var retry=(ObjectNode)parse(leaf("flaky","dev.flaky"));retry.set("retry",parse("{\"maxAttempts\":2,\"maxElapsedSeconds\":60,\"backoffSeconds\":1}"));
  String id=start("[{\"id\":\"parallel\",\"type\":\"PARALLEL\",\"join\":\"ALL_SETTLED\",\"branches\":["+leaf("ok","dev.success")+","+retry+"]}]");
  tick(id);tick(id);assertEquals("RETRY_WAIT",state(id));domainClock.now=domainClock.now.plusSeconds(2);tick(id);
  assertEquals("SUCCEEDED",state(id));assertEquals(1,count("SELECT attempt_count FROM step_runs WHERE execution_id=? AND node_id='ok'",id));
  var output=parse(db.queryForObject("SELECT output_json FROM step_runs WHERE execution_id=? AND node_id='parallel'",String.class,id));
  assertEquals("ok",output.path("ok").path("value").asText());assertEquals("flaky",output.path("flaky").path("value").asText());
 }
 @Test void AC026_sixHourDomainBudgetAndBackoffPersistWithoutChangingDbLeaseClock()throws Exception{
  var retry=(ObjectNode)parse(leaf("long","dev.flaky"));retry.set("retry",parse("{\"maxAttempts\":2,\"maxElapsedSeconds\":21601,\"backoffSeconds\":21600}"));
  String id=start("["+retry+"]");tick(id);assertEquals("RETRY_WAIT",state(id));
  var due=db.queryForObject("SELECT TIMESTAMPDIFF(SECOND,first_attempt_at,next_action_at) FROM step_runs WHERE execution_id=? AND node_id='long'",Long.class,id);assertEquals(21600,due);
  domainClock.now=domainClock.now.plusSeconds(21599);tick(id);assertEquals(1,count("SELECT attempt_count FROM step_runs WHERE execution_id=? AND node_id='long'",id));assertEquals(1,count("SELECT permit_held FROM executions WHERE id=?",id));
  domainClock.now=domainClock.now.plusSeconds(1);var work=service().claim(id);assertNotNull(work);
  assertTrue(count("SELECT TIMESTAMPDIFF(SECOND,UTC_TIMESTAMP(6),lease_until) FROM step_runs WHERE id=?",work.stepId())<=30);
  assertTrue(service().execute(work));assertEquals("SUCCEEDED",state(id));
  domainClock.now=java.time.Instant.now();retry.set("retry",parse("{\"maxAttempts\":100,\"maxElapsedSeconds\":21600,\"backoffSeconds\":21599}"));
  String expired=start("["+retry+"]");tick(expired);domainClock.now=domainClock.now.plusSeconds(21600);tick(expired);assertEquals("MANUAL_WAIT",state(expired));assertEquals(1,count("SELECT attempt_count FROM step_runs WHERE execution_id=? AND node_id='long'",expired));
 }
 @Test void AC027_allSettledAndNotificationMustConvergeBeforeAtomicManualRelease()throws Exception{
  var bad=(ObjectNode)parse(leaf("bad","dev.fail"));bad.set("onFailure",parse("{\"endpointRef\":\"dev.pending\",\"maxAttempts\":2}"));
  String id=start("[{\"id\":\"p\",\"type\":\"PARALLEL\",\"join\":\"ALL_SETTLED\",\"branches\":["+leaf("slow","dev.pending")+","+bad+"]},"+leaf("later","dev.success")+"]");
  tick(id);tick(id);tick(id);assertEquals("PAUSING",state(id));assertEquals(1,count("SELECT permit_held FROM executions WHERE id=?",id));
  finishPending(id,"slow");tick(id);assertEquals("PAUSING",state(id));assertEquals(1,count("SELECT permit_held FROM executions WHERE id=?",id));
  String notification=db.queryForObject("SELECT node_id FROM step_runs WHERE execution_id=? AND is_notification=TRUE",String.class,id);finishPending(id,notification);tick(id);
  assertEquals("MANUAL_WAIT",state(id));assertEquals(0,count("SELECT permit_held FROM executions WHERE id=?",id));assertEquals(0,count("SELECT COUNT(*) FROM step_runs WHERE execution_id=? AND node_id='later'",id));
  assertEquals(1,count("SELECT COUNT(*) FROM execution_events WHERE execution_id=? AND event_type='PERMIT_RELEASED'",id));
 }
 @Test void AC028_expiredLeaseObservesSameOperationAndRejectsOldWorkerResult()throws Exception{
  String id=start("["+leaf("a","dev.success")+"]");var old=service().claim(id);assertNotNull(old);
  var adapter=context.getBean(dev.routeengine.engine.DevelopmentAdapter.class);var outcome=adapter.submit(old.request());
  db.update("UPDATE step_runs SET lease_until=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE id=?",old.stepId());
  var current=service().claim(id);assertNotNull(current);assertTrue(current.observe());assertEquals(old.request().operationId(),current.request().operationId());
  assertEquals(old.request().operationGeneration(),current.request().operationGeneration());assertEquals(old.leaseGeneration()+1,current.leaseGeneration());assertEquals(old.permitGeneration(),current.permitGeneration());
  assertFalse(service().complete(old,outcome));assertTrue(service().execute(current));assertEquals("SUCCEEDED",state(id));
  assertEquals(1,count("SELECT COUNT(*) FROM step_attempts WHERE step_run_id=?",old.stepId()));
 }
 @Test void AC028_crashBeforeSubmitNeverBlindlyResubmitsUnknownIntent()throws Exception{
  String id=start("["+leaf("a","dev.success")+"]");var old=service().claim(id);
  db.update("UPDATE step_runs SET lease_until=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE id=?",old.stepId());
  assertFalse(service().execute(old));var current=service().claim(id);assertTrue(current.observe());service().execute(current);
  assertEquals("RECONCILING",state(id));assertEquals(1,count("SELECT permit_held FROM executions WHERE id=?",id));
  assertFalse(java.nio.file.Files.exists(java.nio.file.Path.of("target/engine-fixture",old.request().operationId()+".operation.json")));
 }
 @Test void AC029_workerAndQueueBoundsAreEnforced()throws Exception{
  var worker=new dev.routeengine.engine.EngineScheduler(service(),2,3);try{assertEquals(2,worker.maximumWorkers());assertEquals(3,worker.queueCapacity());}finally{worker.stop();}
  assertThrows(IllegalArgumentException.class,()->new dev.routeengine.engine.EngineScheduler(service(),33,3));
  assertThrows(IllegalArgumentException.class,()->new dev.routeengine.engine.EngineScheduler(service(),2,257));
 }

 @Test void AC030_knownObservationResolvesExistingIncidentWithoutNewAttempt()throws Exception{
  String id=start("["+leaf("pending","dev.pending")+"]");tick(id);
  String operation=db.queryForObject("SELECT a.operation_id FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE r.execution_id=?",String.class,id);
  java.nio.file.Files.writeString(java.nio.file.Path.of("target/engine-fixture",operation+".result.json"),"{\"status\":\"UNKNOWN\"}");
  db.update("UPDATE step_runs SET next_action_at=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE execution_id=? AND node_id='pending'",id);tick(id);
  assertEquals("RECONCILING",state(id));assertEquals(1,count("SELECT COUNT(*) FROM engine_incidents WHERE execution_id=? AND kind='IN_DOUBT' AND status='OPEN'",id));
  finishPending(id,"pending");tick(id);assertEquals("SUCCEEDED",state(id));assertEquals(1,count("SELECT COUNT(*) FROM engine_incidents WHERE execution_id=? AND kind='IN_DOUBT' AND status='RESOLVED'",id));
  assertEquals(1,count("SELECT attempt_count FROM step_runs WHERE execution_id=? AND node_id='pending'",id));
 }
 @Test void AC031_publishRevalidatesDraftAndAdmissionChecksTypedInput()throws Exception{
  String route="demo-engine-"+UUID.randomUUID().toString().substring(0,8);routes.create(route,"DEMO typed publish","tester","test");
  var d=(ObjectNode)parse("{\"routeId\":\""+route+"\",\"version\":1,\"dslVersion\":\"1\",\"engineSemanticsVersion\":\"1\",\"adapterContractVersion\":\"1\",\"inputSchema\":{\"type\":\"object\",\"properties\":{\"flag\":{\"type\":\"boolean\"}},\"required\":[\"flag\"]},\"root\":{\"id\":\"root\",\"type\":\"SEQUENCE\",\"children\":[]}}");
  routes.draft(route,d,"tester","test");var invalid=d.deepCopy();((ObjectNode)invalid.get("root")).put("type","SHELL");db.update("UPDATE route_versions SET definition_json=? WHERE route_id=? AND version=1",invalid.toString(),route);
  assertThrows(dev.routeengine.api.ApiProblem.class,()->routes.publish(route,1,0,"tester","test"));assertEquals("DRAFT",routes.getVersion(route,1).status());
  db.update("UPDATE route_versions SET definition_json=? WHERE route_id=? AND version=1",d.toString(),route);routes.publish(route,1,0,"tester","test");
  assertThrows(dev.routeengine.api.ApiProblem.class,()->admission.submit("tester",UUID.randomUUID().toString(),new AdmissionService.Request(route,1,"CRITICAL","NOW_OR_REJECT",json.createObjectNode().put("flag","true")),"test"));
  assertEquals(0,count("SELECT COUNT(*) FROM executions WHERE route_id=?",route));
 }

 @Test void AC028_AC030_eachBusinessAttemptHasItsOwnIncidentAndOldWorkerCannotResolveIt()throws Exception{
  var node=(ObjectNode)parse(leaf("work","dev.success"));node.set("retry",parse("{\"maxAttempts\":3,\"maxElapsedSeconds\":60,\"backoffSeconds\":0}"));
  String id=start("["+node+"]");var first=service().claim(id);assertNotNull(first);
  assertTrue(service().complete(first,dev.routeengine.engine.OperationAdapter.Outcome.unknown()));
  String firstIncident=db.queryForObject("SELECT id FROM engine_incidents WHERE execution_id=? AND kind='IN_DOUBT'",String.class,id);
  db.update("UPDATE step_runs SET next_action_at=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE id=?",first.stepId());
  var observed=service().claim(id);assertTrue(observed.observe());assertEquals(first.request().operationId(),observed.request().operationId());
  assertTrue(service().complete(observed,new dev.routeengine.engine.OperationAdapter.Outcome(dev.routeengine.engine.OperationAdapter.Status.FAILED,null,true,null)));
  assertEquals("RESOLVED",db.queryForObject("SELECT status FROM engine_incidents WHERE id=?",String.class,firstIncident));
  var second=service().claim(id);assertNotNull(second);assertFalse(second.observe());assertNotEquals(first.request().operationId(),second.request().operationId());
  assertTrue(service().complete(second,dev.routeengine.engine.OperationAdapter.Outcome.unknown()));
  assertEquals(1,count("SELECT COUNT(*) FROM engine_incidents WHERE execution_id=? AND kind='IN_DOUBT' AND status='OPEN'",id));
  String secondIncident=db.queryForObject("SELECT id FROM engine_incidents WHERE execution_id=? AND kind='IN_DOUBT' AND status='OPEN'",String.class,id);
  assertNotEquals(firstIncident,secondIncident);assertEquals(2,count("SELECT COUNT(*) FROM engine_incidents WHERE execution_id=? AND kind='IN_DOUBT'",id));
  assertEquals(second.attemptId(),db.queryForObject("SELECT attempt_id FROM engine_incidents WHERE id=?",String.class,secondIncident));
  assertEquals(second.request().operationId(),db.queryForObject("SELECT operation_id FROM engine_incidents WHERE id=?",String.class,secondIncident));
  assertEquals("FORWARD",db.queryForObject("SELECT direction FROM engine_incidents WHERE id=?",String.class,secondIncident));
  assertEquals(second.request().operationGeneration(),count("SELECT operation_generation FROM engine_incidents WHERE id=?",secondIncident));
  var success=new dev.routeengine.engine.OperationAdapter.Outcome(dev.routeengine.engine.OperationAdapter.Status.SUCCEEDED,json.createObjectNode(),false,null);
  assertFalse(service().complete(first,success));assertFalse(service().complete(observed,success));
  assertEquals("OPEN",db.queryForObject("SELECT status FROM engine_incidents WHERE id=?",String.class,secondIncident));
  db.update("UPDATE step_runs SET next_action_at=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE id=?",second.stepId());
  var current=service().claim(id);assertTrue(current.observe());assertEquals(second.request().operationId(),current.request().operationId());
  var wrongRequest=new dev.routeengine.engine.OperationAdapter.Request(first.request().operationId(),current.request().operationGeneration(),current.request().attempt(),current.request().direction(),current.request().node(),current.request().input());
  var wrongOperation=new dev.routeengine.engine.EngineService.Work(id,current.stepId(),current.attemptId(),current.permitGeneration(),current.leaseGeneration(),current.stepVersion(),true,wrongRequest);
  assertFalse(service().complete(wrongOperation,success));
  assertThrows(org.springframework.dao.DataAccessException.class,()->db.update("UPDATE engine_incidents SET operation_id=? WHERE id=?",first.request().operationId(),secondIncident));
  assertEquals("OPEN",db.queryForObject("SELECT status FROM engine_incidents WHERE id=?",String.class,secondIncident));
  long events=count("SELECT COUNT(*) FROM execution_events WHERE execution_id=?",id);
  assertThrows(IllegalStateException.class,()->transaction.executeWithoutResult(s->{assertTrue(service().complete(current,success));throw new IllegalStateException("incident-result rollback");}));
  assertEquals("OPEN",db.queryForObject("SELECT status FROM engine_incidents WHERE id=?",String.class,secondIncident));assertEquals(events,count("SELECT COUNT(*) FROM execution_events WHERE execution_id=?",id));
  assertTrue(service().complete(current,success));assertEquals("RESOLVED",db.queryForObject("SELECT status FROM engine_incidents WHERE id=?",String.class,secondIncident));assertEquals("SUCCEEDED",state(id));
 }
 // Deliberately hold only an incident in a separate test transaction to expose acquisition order.
 // This contention fixture is not production lock-taking code and never represents admission safety.
 void incidentBeforeStepLocks(String id,String step,String attempt,java.util.function.Supplier<Boolean> mutation)throws Exception{
  var worker=java.util.concurrent.Executors.newSingleThreadExecutor();
  var connectionId=new java.util.concurrent.atomic.AtomicLong();
  var pending=new java.util.concurrent.atomic.AtomicReference<java.util.concurrent.Future<Boolean>>();
  try{
   transaction.executeWithoutResult(holding->{
    assertFalse(db.queryForList("SELECT id FROM engine_incidents WHERE execution_id=? ORDER BY id FOR UPDATE",id).isEmpty());
    pending.set(worker.submit(()->transaction.execute(status->{
     connectionId.set(db.queryForObject("SELECT CONNECTION_ID()",Long.class));
     return mutation.get();
    })));
    long deadline=System.nanoTime()+java.util.concurrent.TimeUnit.SECONDS.toNanos(2);
    String blockedSql="";
    while(System.nanoTime()<deadline&&!pending.get().isDone()){
     if(connectionId.get()!=0){
      var queries=db.queryForList("SELECT INFO FROM information_schema.PROCESSLIST WHERE ID=?",String.class,connectionId.get());
      if(!queries.isEmpty()&&queries.getFirst()!=null){
       String query=queries.getFirst().toLowerCase(Locale.ROOT);
       if(query.contains("engine_incidents")&&(query.contains("for update")||query.startsWith("update engine_incidents"))){blockedSql=queries.getFirst();break;}
      }
     }
     try{Thread.sleep(10);}catch(InterruptedException interrupted){Thread.currentThread().interrupt();throw new IllegalStateException(interrupted);}
    }
    assertFalse(blockedSql.isBlank(),"Mutation must wait for its existing incident before writing step work");
    System.out.println("ACTUAL_DB_LOCK_ORDER waiting connection="+connectionId.get()+" sql="+blockedSql);
    assertDoesNotThrow(()->{
     try(var independent=Objects.requireNonNull(db.getDataSource()).getConnection()){
      independent.setAutoCommit(false);
      try{
       for(var target:List.of(Map.entry("step_attempts",attempt),Map.entry("step_runs",step))){
        try(var statement=independent.prepareStatement("SELECT id FROM "+target.getKey()+" WHERE id=? FOR UPDATE NOWAIT")){
         statement.setString(1,target.getValue());
         try(var result=statement.executeQuery()){assertTrue(result.next());}
        }
       }
      }finally{independent.rollback();}
     }
    },"Step and attempt must remain unlocked while the worker waits for incident ownership");
    System.out.println("ACTUAL_DB_LOCK_ORDER independent NOWAIT step/attempt locks acquired before incident release");
   });
   assertTrue(pending.get().get(5,java.util.concurrent.TimeUnit.SECONDS));
  }finally{
   worker.shutdown();
   assertTrue(worker.awaitTermination(5,java.util.concurrent.TimeUnit.SECONDS));
  }
 }
 dev.routeengine.engine.EngineService.Work unknownThenClaim(String id){
  var first=service().claim(id);assertNotNull(first);
  assertTrue(service().complete(first,dev.routeengine.engine.OperationAdapter.Outcome.unknown()));
  db.update("UPDATE step_runs SET next_action_at=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE id=?",first.stepId());
  var observed=service().claim(id);assertTrue(observed.observe());return observed;
 }
 @Test void AC028_existingIncidentLockPrecedesTerminalStepAndAttemptLocks()throws Exception{
  String id=start("["+leaf("known","dev.success")+"]");var observed=unknownThenClaim(id);
  var success=new dev.routeengine.engine.OperationAdapter.Outcome(dev.routeengine.engine.OperationAdapter.Status.SUCCEEDED,json.createObjectNode(),false,null);
  incidentBeforeStepLocks(id,observed.stepId(),observed.attemptId(),()->service().complete(observed,success));
  assertEquals("SUCCEEDED",state(id));assertEquals(0,count("SELECT COUNT(*) FROM engine_incidents WHERE execution_id=? AND status='OPEN'",id));
 }
 @Test void AC028_existingIncidentLockPrecedesRepeatedUnknownStepAndAttemptLocks()throws Exception{
  String id=start("["+leaf("unknown","dev.success")+"]");var observed=unknownThenClaim(id);
  incidentBeforeStepLocks(id,observed.stepId(),observed.attemptId(),()->service().complete(observed,dev.routeengine.engine.OperationAdapter.Outcome.unknown()));
  assertEquals("RECONCILING",state(id));assertEquals(1,count("SELECT COUNT(*) FROM engine_incidents WHERE execution_id=? AND status='OPEN'",id));
  assertEquals(1,count("SELECT COUNT(*) FROM step_attempts WHERE step_run_id=?",observed.stepId()));
 }
 @Test void AC028_existingIncidentLockPrecedesClaimBudgetFailureAndNewIncident()throws Exception{
  var retry=(ObjectNode)parse(leaf("budget","dev.success"));retry.set("retry",parse("{\"maxAttempts\":3,\"maxElapsedSeconds\":60,\"backoffSeconds\":1}"));
  String id=start("["+retry+"]");var observed=unknownThenClaim(id);
  assertTrue(service().complete(observed,new dev.routeengine.engine.OperationAdapter.Outcome(dev.routeengine.engine.OperationAdapter.Status.FAILED,null,true,null)));
  assertEquals("RETRY_WAIT",state(id));domainClock.now=domainClock.now.plusSeconds(61);
  incidentBeforeStepLocks(id,observed.stepId(),observed.attemptId(),()->service().claim(id)==null);
  assertEquals("MANUAL_WAIT",state(id));assertEquals(0,count("SELECT permit_held FROM executions WHERE id=?",id));
  assertEquals(1,count("SELECT COUNT(*) FROM engine_incidents WHERE execution_id=? AND kind='IN_DOUBT' AND status='RESOLVED'",id));
  assertEquals(1,count("SELECT COUNT(*) FROM engine_incidents WHERE execution_id=? AND kind='KNOWN_FAILURE' AND status='OPEN'",id));
 }

}
