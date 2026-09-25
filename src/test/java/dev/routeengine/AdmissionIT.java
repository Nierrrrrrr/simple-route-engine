package dev.routeengine;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import dev.routeengine.registry.RouteRegistry;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;
import java.net.URI;
import java.net.http.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT,properties={"route.scheduler.enabled=false","route.engine.enabled=false"})
class AdmissionIT {
 @LocalServerPort int port;
 @Autowired ObjectMapper json;
 @Autowired JdbcTemplate db;
 @Autowired TransactionTemplate tx;
 @Autowired RouteRegistry routes;
 @Autowired ApplicationContext context;
 final HttpClient client=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
 final String token=Objects.requireNonNull(System.getenv("ROUTE_TEST_TOKEN"));
 String route;
 @BeforeEach void setup(){
  tx.executeWithoutResult(s->{
   db.queryForList("SELECT id FROM scheduler_pool WHERE id=1 FOR UPDATE");
   // Test-only holders have no external work; close all previous test work, keeping append-only audit.
   db.update("UPDATE admission_requests SET decision='WITHDRAWN' WHERE decision='QUEUED'");
   db.update("UPDATE executions SET permit_held=FALSE,state='CANCELLED' WHERE state IN ('QUEUED','ADMITTED','MANUAL_WAIT','RECOVERING')");
   db.update("UPDATE scheduler_pool SET total_slots=100,critical_reserved=20,high_weight=6,normal_weight=3,low_weight=1,wrr_cursor=0,admission_enabled=TRUE WHERE id=1");
  });
  route="demo-admit-"+UUID.randomUUID().toString().substring(0,8);
  routes.create(route,"DEMO admission fixture","tester","setup");
  publish(1);
 }
 void publish(int v){var d=json.createObjectNode();d.put("routeId",route).put("version",v).put("dslVersion","1").put("engineSemanticsVersion","1").put("adapterContractVersion","1");d.putObject("root").put("id","root").put("type","SEQUENCE").putArray("children");routes.draft(route,d,"tester","setup");routes.publish(route,v,0,"tester","setup");}
 ObjectNode request(String priority,String mode){return json.createObjectNode().put("routeId",route).put("priority",priority).put("admissionMode",mode).set("input",json.createObjectNode());}
 HttpResponse<String> raw(String method,String path,String key,String body,String accept)throws Exception{
  var b=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+path)).timeout(Duration.ofSeconds(45)).header("Authorization","Bearer "+token).header("Content-Type","application/json").header("Accept",accept).header("X-Request-ID","admission-test");
  if(key!=null)b.header("Idempotency-Key",key);
  return client.send(b.method(method,body==null?HttpRequest.BodyPublishers.noBody():HttpRequest.BodyPublishers.ofString(body)).build(),HttpResponse.BodyHandlers.ofString());
 }
 JsonNode call(String method,String path,String key,JsonNode body,int status)throws Exception{var r=raw(method,path,key,body==null?null:body.toString(),"application/json");assertEquals(status,r.statusCode(),r.body());return json.readTree(r.body());}
 JsonNode submit(String p,String mode,int status)throws Exception{return call("POST","/executions",UUID.randomUUID().toString(),request(p,mode),status);}
 JsonNode capacity()throws Exception{return call("GET","/capacity",null,null,200);}
 long scalar(String sql,Object... args){return db.queryForObject(sql,Long.class,args);}
 void pool(int total,int reserved,boolean enabled){tx.executeWithoutResult(s->{db.queryForList("SELECT id FROM scheduler_pool WHERE id=1 FOR UPDATE");db.update("UPDATE scheduler_pool SET total_slots=?,critical_reserved=?,admission_enabled=? WHERE id=1",total,reserved,enabled);});}
 Object service(){return context.getBean("admissionService");}
 Object tick()throws Exception{return service().getClass().getMethod("tick").invoke(service());}
 String stop(String id,long generation,long stateVersion)throws Exception{return (String)service().getClass().getMethod("stop",String.class,long.class,long.class,String.class,String.class,String.class,String.class).invoke(service(),id,generation,stateVersion,"SUCCEEDED","tester","test fixture completed; no external work","stop-fixture");}
 void closeHolders(){tx.executeWithoutResult(s->{db.queryForList("SELECT id FROM scheduler_pool WHERE id=1 FOR UPDATE");db.update("UPDATE executions SET state='SUCCEEDED',permit_held=FALSE,state_version=state_version+1 WHERE permit_held=TRUE");});}

 @Test void AC011_twoHundredCompetingRequestsOnlyOneFinalPermit()throws Exception{
  for(int i=0;i<99;i++)submit("CRITICAL","NOW_OR_REJECT",202);
  var start=new CountDownLatch(1);var ready=new CountDownLatch(200);
  try(var executor=Executors.newVirtualThreadPerTaskExecutor()){
   var futures=new ArrayList<Future<Integer>>();
   for(int i=0;i<200;i++){String key="race-"+UUID.randomUUID();futures.add(executor.submit(()->{ready.countDown();start.await();return raw("POST","/executions",key,request("CRITICAL","NOW_OR_REJECT").toString(),"application/json").statusCode();}));}
   assertTrue(ready.await(10,TimeUnit.SECONDS));start.countDown();int accepted=0,rejected=0;
   for(var f:futures){int status=f.get(60,TimeUnit.SECONDS);if(status==202)accepted++;else if(status==409)rejected++;else fail("Unexpected race response "+status);}
   assertEquals(1,accepted);assertEquals(199,rejected);
  }
  assertEquals(100,scalar("SELECT COUNT(*) FROM executions WHERE permit_held=TRUE"));
  assertEquals(100,capacity().path("used").asInt());
 }
 @Test void AC012_hardReserveAndCriticalSharedNoPreemption()throws Exception{
  for(int i=0;i<80;i++)submit("NORMAL","NOW_OR_REJECT",202);
  submit("HIGH","NOW_OR_REJECT",409);submit("LOW","NOW_OR_REJECT",409);
  for(int i=0;i<20;i++)submit("CRITICAL","NOW_OR_REJECT",202);
  submit("CRITICAL","NOW_OR_REJECT",409);
  assertEquals(80,capacity().path("nonCriticalUsed").asInt());assertEquals(100,capacity().path("used").asInt());
  closeHolders();for(int i=0;i<100;i++)submit("CRITICAL","NOW_OR_REJECT",202);
  assertEquals(100,capacity().path("used").asInt());assertEquals(0,capacity().path("nonCriticalUsed").asInt());
 }
 @Test void AC013_criticalQueueWinsWithoutPreemptingHolder()throws Exception{
  pool(1,0,true);var holder=submit("LOW","NOW_OR_REJECT",202);var high=submit("HIGH","QUEUE",202);var critical=submit("CRITICAL","QUEUE",202);
  assertNull(tick());assertEquals(1,scalar("SELECT permit_held FROM executions WHERE id=?",holder.path("executionId").asText()));
  closeHolders();assertEquals(critical.path("executionId").asText(),tick());assertEquals(0,scalar("SELECT permit_held FROM executions WHERE id=?",high.path("executionId").asText()));
 }
 @Test void AC014_persistedWrrHundredBackloggedAdmissionsSixtyThirtyTen()throws Exception{
  pool(1,0,false);for(String p:List.of("HIGH","NORMAL","LOW"))for(int i=0;i<101;i++)submit(p,"QUEUE",202);
  pool(1,0,true);var count=new HashMap<String,Integer>();
  for(int i=0;i<100;i++){String id=(String)tick();assertNotNull(id);String p=db.queryForObject("SELECT priority FROM executions WHERE id=?",String.class,id);count.merge(p,1,Integer::sum);closeHolders();}
  assertEquals(Map.of("HIGH",60,"NORMAL",30,"LOW",10),count);assertEquals(0,scalar("SELECT wrr_cursor FROM scheduler_pool WHERE id=1"));
  // Every queue was continuously backlogged throughout the observed 100 admissions.
  for(String p:List.of("HIGH","NORMAL","LOW"))assertTrue(scalar("SELECT COUNT(*) FROM admission_requests WHERE decision='QUEUED' AND priority=?",p)>=41);
 }
 @Test void AC014_emptyClassesSkipAndOnlyRealAdmissionMovesCursor()throws Exception{
  pool(1,0,false);var n=submit("NORMAL","QUEUE",202);assertNull(tick());assertEquals(0,scalar("SELECT wrr_cursor FROM scheduler_pool"));
  pool(1,0,true);assertEquals(n.path("executionId").asText(),tick());assertEquals(7,scalar("SELECT wrr_cursor FROM scheduler_pool"));
  assertNull(tick());assertEquals(7,scalar("SELECT wrr_cursor FROM scheduler_pool"));
 }
 @Test void AC015_fifoAndNowCannotBypassCriticalSameClassOrWrr()throws Exception{
  pool(1,0,false);var old=submit("HIGH","QUEUE",202);var next=submit("HIGH","QUEUE",202);pool(1,0,true);
  submit("HIGH","NOW_OR_REJECT",409);assertEquals(0,scalar("SELECT wrr_cursor FROM scheduler_pool"));assertEquals(old.path("executionId").asText(),tick());closeHolders();assertEquals(next.path("executionId").asText(),tick());
  closeHolders();var c=submit("CRITICAL","QUEUE",202);submit("HIGH","NOW_OR_REJECT",409);assertEquals(c.path("executionId").asText(),tick());
  closeHolders();db.update("UPDATE scheduler_pool SET wrr_cursor=6");var n=submit("NORMAL","QUEUE",202);submit("HIGH","NOW_OR_REJECT",409);assertEquals(6,scalar("SELECT wrr_cursor FROM scheduler_pool"));assertEquals(n.path("executionId").asText(),tick());
 }
 @Test void AC016_nowRejectHasNoLatentExecutionEvenAfterCapacityReturns()throws Exception{
  pool(1,0,true);var accepted=submit("HIGH","NOW_OR_REJECT",202);assertEquals("ADMITTED",accepted.path("decision").asText());assertEquals(1,scalar("SELECT permit_held FROM executions WHERE id=?",accepted.path("executionId").asText()));
  long before=scalar("SELECT COUNT(*) FROM executions");var rejected=submit("HIGH","NOW_OR_REJECT",409);assertEquals("ADMISSION_REJECTED",rejected.path("code").asText());assertTrue(rejected.path("executionId").isNull());assertEquals(before,scalar("SELECT COUNT(*) FROM executions"));
  closeHolders();assertNull(tick());assertEquals(before,scalar("SELECT COUNT(*) FROM executions"));assertEquals(0,capacity().path("used").asInt());
 }
 @Test void AC017_queueBindsExactVersionAndSnapshotIsObservation()throws Exception{
  pool(1,0,false);var q=submit("LOW","QUEUE",202);assertEquals("QUEUED",q.path("decision").asText());assertEquals(0,scalar("SELECT permit_held FROM executions WHERE id=?",q.path("executionId").asText()));
  var cap=capacity();Instant.parse(cap.path("observedAt").asText());assertTrue(cap.has("configVersion"));
  publish(2);var r=routes.get(route);routes.update(route,r.name(),false,r.stateVersion(),"tester","disabled");
  call("POST","/executions","disabled",request("LOW","QUEUE"),422);
  pool(1,0,true);assertEquals(q.path("executionId").asText(),tick());assertEquals(1,scalar("SELECT route_version FROM executions WHERE id=?",q.path("executionId").asText()));assertEquals(1,capacity().path("used").asInt());assertEquals(0,cap.path("used").asInt());
 }
 @Test void AC017_routeEligibilityIsLockedInsidePoolTransaction()throws Exception{
  var held=new CountDownLatch(1);var release=new CountDownLatch(1);
  try(var executor=Executors.newVirtualThreadPerTaskExecutor()){
   var locker=executor.submit(()->tx.executeWithoutResult(s->{db.queryForList("SELECT * FROM routes WHERE route_id=? FOR UPDATE",route);db.update("UPDATE routes SET enabled=FALSE WHERE route_id=?",route);held.countDown();try{release.await(8,TimeUnit.SECONDS);}catch(InterruptedException e){throw new RuntimeException(e);}}));
   assertTrue(held.await(5,TimeUnit.SECONDS));var waiting=executor.submit(()->raw("POST","/executions","eligibility-race",request("NORMAL","QUEUE").toString(),"application/json"));
   Thread.sleep(300);assertFalse(waiting.isDone(),"admission must block on route eligibility lock");release.countDown();locker.get();assertEquals(422,waiting.get().statusCode());assertEquals(0,scalar("SELECT COUNT(*) FROM executions WHERE route_id=?",route));
  }finally{release.countDown();}
 }
 @Test void AC018_parallelSameKeyCanonicalContentConflictAndOriginalReplay()throws Exception{
  var body=request("HIGH","NOW_OR_REJECT");body.set("input",json.readTree("{\"b\":2,\"a\":1}"));String key="duplicate-"+UUID.randomUUID();var start=new CountDownLatch(1);
  try(var executor=Executors.newVirtualThreadPerTaskExecutor()){
   var futures=new ArrayList<Future<HttpResponse<String>>>();for(int i=0;i<30;i++)futures.add(executor.submit(()->{start.await();return raw("POST","/executions",key,body.toString(),"application/json");}));start.countDown();String original=null;
   for(var f:futures){var r=f.get();assertEquals(202,r.statusCode());if(original==null)original=r.body();else assertEquals(original,r.body());}
  }
  body.set("input",json.readTree("{\"a\":1,\"b\":2}"));var replay=call("POST","/executions",key,body,202);assertEquals(1,scalar("SELECT COUNT(*) FROM executions WHERE route_id=?",route));
  body.put("priority","LOW");assertEquals("IDEMPOTENCY_CONFLICT",call("POST","/executions",key,body,409).path("code").asText());
  assertEquals(replay,call("GET","/admission-requests/"+replay.path("admissionRequestId").asText(),null,null,200));
 }
 @Test void AC018_rejectedKeyRemainsRejectedNewKeyCanCompete()throws Exception{
  pool(1,0,false);String key="rejected-"+UUID.randomUUID();var body=request("NORMAL","NOW_OR_REJECT");var rejected=call("POST","/executions",key,body,409);pool(1,0,true);
  assertEquals(rejected,call("POST","/executions",key,body,409));submit("NORMAL","NOW_OR_REJECT",202);
 }
 ObjectNode config(int t,int r,int h,int n,int l)throws Exception{return json.createObjectNode().put("totalSlots",t).put("criticalReserved",r).put("highWeight",h).put("normalWeight",n).put("lowWeight",l).put("admissionEnabled",true).put("configVersion",capacity().path("configVersion").asLong()).put("reason","test config");}
 @Test void AC019_invalidAndUnsafeShrinkRejectedConfigAuditAtomic()throws Exception{
  for(int[] x:new int[][]{{0,0,6,3,1},{2,3,6,3,1},{2,-1,6,3,1},{2,0,0,3,1},{2,0,6,-1,1}})call("PUT","/capacity/config",null,config(x[0],x[1],x[2],x[3],x[4]),422);
  submit("NORMAL","NOW_OR_REJECT",202);submit("NORMAL","NOW_OR_REJECT",202);var before=capacity();long events=scalar("SELECT COUNT(*) FROM execution_events WHERE event_type='POOL_CONFIG_UPDATED'");
  call("PUT","/capacity/config",null,config(1,0,6,3,1),409);call("PUT","/capacity/config",null,config(3,2,6,3,1),409);assertEquals(before.path("configVersion"),capacity().path("configVersion"));assertEquals(events,scalar("SELECT COUNT(*) FROM execution_events WHERE event_type='POOL_CONFIG_UPDATED'"));
  var input=config(3,1,3,2,1);var changed=call("PUT","/capacity/config",null,input,200);assertEquals(before.path("configVersion").asLong()+1,changed.path("configVersion").asLong());assertEquals(0,changed.path("wrrCursor").asInt());assertEquals(events+1,scalar("SELECT COUNT(*) FROM execution_events WHERE event_type='POOL_CONFIG_UPDATED'"));call("PUT","/capacity/config",null,input,409);
 }
 @Test void AC020_releaseIdempotentStaleGenerationFencedLeaseExpiryDoesNotRelease()throws Exception{
  var a=submit("NORMAL","NOW_OR_REJECT",202);String id=a.path("executionId").asText();db.update("UPDATE executions SET lease_generation=7,lease_until=UTC_TIMESTAMP(6)-INTERVAL 1 HOUR WHERE id=?",id);tick();assertEquals(1,scalar("SELECT permit_held FROM executions WHERE id=?",id));assertEquals(1,scalar("SELECT permit_generation FROM executions WHERE id=?",id));
  long state=scalar("SELECT state_version FROM executions WHERE id=?",id);assertEquals("RELEASED",stop(id,1,state));assertEquals("ALREADY_RELEASED",stop(id,1,state));
  // Isolated future-recovery fixture: new permit generation, no external work exists.
  tx.executeWithoutResult(s->{db.queryForList("SELECT id FROM scheduler_pool WHERE id=1 FOR UPDATE");db.update("UPDATE executions SET state='RECOVERING',permit_held=TRUE,permit_generation=2,state_version=state_version+1 WHERE id=?",id);});
  assertEquals("STALE",stop(id,1,state));assertEquals(1,scalar("SELECT permit_held FROM executions WHERE id=?",id));assertEquals(7,scalar("SELECT lease_generation FROM executions WHERE id=?",id));
 }
 @Test void AC022_poolLockTimeoutIs503AndRetrySameIdentityIsSafe()throws Exception{
  var held=new CountDownLatch(1);var release=new CountDownLatch(1);String key="lock-"+UUID.randomUUID();
  try(var executor=Executors.newVirtualThreadPerTaskExecutor()){
   var lock=executor.submit(()->tx.executeWithoutResult(s->{db.queryForList("SELECT id FROM scheduler_pool WHERE id=1 FOR UPDATE");held.countDown();try{release.await(20,TimeUnit.SECONDS);}catch(Exception e){throw new RuntimeException(e);}}));assertTrue(held.await(5,TimeUnit.SECONDS));
   var r=raw("POST","/executions",key,request("CRITICAL","NOW_OR_REJECT").toString(),"application/json");assertEquals(503,r.statusCode(),r.body());assertEquals("DATABASE_UNAVAILABLE",json.readTree(r.body()).path("code").asText());assertTrue(r.headers().firstValue("X-Admission-Request-ID").isPresent());release.countDown();lock.get();
   var accepted=call("POST","/executions",key,request("CRITICAL","NOW_OR_REJECT"),202);assertEquals(r.headers().firstValue("X-Admission-Request-ID").orElseThrow(),accepted.path("admissionRequestId").asText());assertEquals(1,scalar("SELECT COUNT(*) FROM executions WHERE route_id=?",route));
  }finally{release.countDown();}
 }
 @Test void AC008_admissionAndConfigRejectMalformedAndUnacceptableBeforeMutation()throws Exception{
  long before=scalar("SELECT COUNT(*) FROM admission_requests"),events=scalar("SELECT COUNT(*) FROM execution_events");
  for(String suffix:List.of(" {}","garbage"))assertEquals(422,raw("POST","/executions","bad",request("HIGH","QUEUE")+suffix,"application/json").statusCode());
  var body=request("HIGH","QUEUE");body.put("routeVersion",0.5);assertEquals(422,raw("POST","/executions","bad",body.toString(),"application/json").statusCode());
  assertEquals(406,raw("POST","/executions","bad",request("HIGH","QUEUE").toString(),"image/png").statusCode());
  var cfg=config(100,20,6,3,1);assertEquals(406,raw("PUT","/capacity/config",null,cfg.toString(),"image/png").statusCode());cfg.put("totalSlots","100");assertEquals(422,raw("PUT","/capacity/config",null,cfg.toString(),"application/json").statusCode());
  assertEquals(before,scalar("SELECT COUNT(*) FROM admission_requests"));assertEquals(events,scalar("SELECT COUNT(*) FROM execution_events"));
 }
 @Test void AC018_principalIsolationAndLookupNeverExposeOtherPrincipals()throws Exception{
  var service=(dev.routeengine.admission.AdmissionService)service();var body=json.treeToValue(request("LOW","NOW_OR_REJECT"),dev.routeengine.admission.AdmissionService.Request.class);
  var a=service.submit("principal-a","same-scope-key",body,"principal-test");var b=service.submit("principal-b","same-scope-key",body,"principal-test");
  assertEquals(202,a.status());assertEquals(202,b.status());assertNotEquals(a.body().path("executionId"),b.body().path("executionId"));
  assertEquals(a.body(),service.submit("principal-a","same-scope-key",body,"replay").body());
  assertThrows(dev.routeengine.api.ApiProblem.class,()->service.lookup("principal-b",a.body().path("admissionRequestId").asText()));
  call("GET","/admission-requests/"+a.body().path("admissionRequestId").asText(),null,null,404);
  assertEquals(2,scalar("SELECT COUNT(*) FROM admission_requests WHERE idempotency_key='same-scope-key' AND operation_scope='POST /executions'"));
 }
 @Test void AC019_configRollbackIncludesPoolAuditAndHistory()throws Exception{
  var service=(dev.routeengine.admission.AdmissionService)service();var before=db.queryForMap("SELECT * FROM scheduler_pool WHERE id=1");long events=scalar("SELECT COUNT(*) FROM execution_events"),history=scalar("SELECT COUNT(*) FROM pool_config_history");
  var c=json.treeToValue(config(123,12,3,2,1),dev.routeengine.admission.AdmissionService.Config.class);
  assertThrows(RuntimeException.class,()->service.configure(c,"x".repeat(129),"audit-rollback"));
  assertEquals(before,db.queryForMap("SELECT * FROM scheduler_pool WHERE id=1"));assertEquals(events,scalar("SELECT COUNT(*) FROM execution_events"));assertEquals(history,scalar("SELECT COUNT(*) FROM pool_config_history"));
 }
 @Test void AC020_unknownOperationBlocksInternalReleaseAndNoPublicReleaseEndpoint()throws Exception{
  var a=submit("HIGH","NOW_OR_REJECT",202);String id=a.path("executionId").asText(),step=UUID.randomUUID().toString();
  db.update("INSERT INTO step_runs(id,execution_id,node_id,state) VALUES(?,?,'fixture','FAILED')",step,id);
  db.update("INSERT INTO step_attempts(id,step_run_id,attempt_number,direction,state,permit_generation,lease_generation,operation_generation,operation_id) VALUES(?,?,1,'FORWARD','IN_DOUBT',1,7,3,?)",UUID.randomUUID().toString(),step,"fixture-"+UUID.randomUUID());
  var service=(dev.routeengine.admission.AdmissionService)service();long state=scalar("SELECT state_version FROM executions WHERE id=?",id);
  var error=assertThrows(dev.routeengine.api.ApiProblem.class,()->service.stop(id,1,state,"MANUAL_WAIT","tester","unknown work","test"));assertEquals("WORK_NOT_STOPPED",error.code());assertEquals(1,scalar("SELECT permit_held FROM executions WHERE id=?",id));
  call("POST","/executions/"+id+"/release",null,json.createObjectNode(),404);
  db.update("UPDATE step_attempts SET state='STOPPED' WHERE step_run_id=?",step);
  assertEquals("RELEASED",stop(id,1,state));assertEquals(3,scalar("SELECT operation_generation FROM step_attempts WHERE step_run_id=?",step));
 }
 @Test void AC019_capacityOnlyUpdatePreservesCursorWeightsUpdateResets()throws Exception{
  submit("NORMAL","NOW_OR_REJECT",202);assertEquals(7,scalar("SELECT wrr_cursor FROM scheduler_pool"));
  var changed=call("PUT","/capacity/config",null,config(101,20,6,3,1),200);assertEquals(7,changed.path("wrrCursor").asInt(),"M0 defaults preserve cursor when weights unchanged");
  changed=call("PUT","/capacity/config",null,config(101,20,5,3,1),200);assertEquals(0,changed.path("wrrCursor").asInt());
 }
}
