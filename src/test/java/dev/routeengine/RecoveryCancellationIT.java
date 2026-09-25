package dev.routeengine;

import com.fasterxml.jackson.databind.*;
import com.sun.net.httpserver.HttpServer;
import dev.routeengine.admission.AdmissionService;
import dev.routeengine.engine.EngineService;
import dev.routeengine.registry.RouteRegistry;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.atomic.*;
import static org.junit.jupiter.api.Assertions.*;

/** Deterministic claim/cancel/execute ordering with real MariaDB and real REST adapter I/O. */
class RecoveryCancellationIT {
 @TempDir Path temp;
 final ObjectMapper json=new ObjectMapper();
 long number(JdbcTemplate db,String sql,String id){return db.queryForObject(sql,Long.class,id);}
 String state(JdbcTemplate db,String id){return db.queryForObject("SELECT CONCAT(state,':',permit_held) FROM executions WHERE id=?",String.class,id);}
 EngineService.Work due(EngineService engine,String id)throws Exception{
  Instant deadline=Instant.now().plusSeconds(5);EngineService.Work work;
  do{work=engine.claim(id);if(work!=null)return work;Thread.sleep(20);}while(Instant.now().isBefore(deadline));
  fail("Existing operation was not reconciled within its polling bound");return null;
 }
 @Test void AC048_claimBeforeCancelRetainsPermitUntilRealTerminalObservationAndStopsNewClaims()throws Exception{
  var submits=new AtomicInteger();var deletes=new AtomicInteger();var observes=new AtomicInteger();
  var operation=new AtomicReference<String>();var terminalEvidence=new AtomicBoolean();
  var events=Collections.synchronizedList(new ArrayList<String>());
  HttpServer remote=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
  remote.createContext("/operation",e->{
   String method=e.getRequestMethod(),op;
   if(method.equals("POST")){var body=json.readTree(e.getRequestBody());op=body.path("operationId").asText();operation.set(op);submits.incrementAndGet();}
   else{op=e.getRequestURI().getPath().substring("/operation/".length());if(method.equals("DELETE"))deletes.incrementAndGet();else observes.incrementAndGet();}
   events.add(method+":"+op);
   String status=method.equals("GET")&&terminalEvidence.get()?"STOPPED":"WAITING";
   byte[] body=json.createObjectNode().put("operationId",op).put("status",status).toString().getBytes(StandardCharsets.UTF_8);
   e.sendResponseHeaders(status.equals("STOPPED")?200:202,body.length);e.getResponseBody().write(body);e.close();
  });remote.start();
  var config=json.createObjectNode();config.putObject("endpoints").putObject("cancel-fixture")
   .put("baseUri","http://127.0.0.1:"+remote.getAddress().getPort()+"/operation").put("allowedHost","127.0.0.1").put("allowLoopbackHttp",true)
   .put("query",true).put("cancel",true).put("timeoutMillis",2000).put("maxResponseBytes",4096);
  Path catalog=temp.resolve("catalog.json");Files.writeString(catalog,config.toString());
  SpringApplication application=new SpringApplication(RouteEngineApplication.class);
  try(var context=application.run("--server.port=0","--spring.datasource.url=${ROUTE_ENGINE_TEST_DB_URL}","--spring.datasource.username=${ROUTE_ENGINE_TEST_DB_USER}","--spring.datasource.password=${ROUTE_ENGINE_TEST_DB_PASSWORD}","--route.scheduler.enabled=false","--route.engine.enabled=false","--route.adapters.config="+catalog)){
   var db=context.getBean(JdbcTemplate.class);var engine=context.getBean(EngineService.class);var routes=context.getBean(RouteRegistry.class);
   assertTrue(db.queryForObject("SELECT VERSION()",String.class).contains("MariaDB"));
   String expectedDatabase=Objects.requireNonNull(System.getenv("ROUTE_ENGINE_TEST_DB_URL")).split("\\?")[0];
   assertNotEquals(Objects.requireNonNull(System.getenv("ROUTE_DB_URL")).split("\\?")[0],expectedDatabase,"Engine integration must use its independently owned database");
   try(var connection=db.getDataSource().getConnection()){assertEquals(expectedDatabase,connection.getMetaData().getURL().split("\\?")[0]);}
   String route="demo-cancel-"+UUID.randomUUID().toString().substring(0,8);
   routes.create(route,"DEMO cancellation ordering","test","cancel-order");
   var definition=json.createObjectNode().put("routeId",route).put("version",1).put("dslVersion","1").put("engineSemanticsVersion","1").put("adapterContractVersion","1");
   var children=definition.putObject("root").put("id","root").put("type","SEQUENCE").putArray("children");
   var branches=children.addObject().put("id","parallel").put("type","PARALLEL").put("join","ALL_SETTLED").putArray("branches");
   for(String id:List.of("active","unclaimed"))branches.addObject().put("id",id).put("type","REST").put("endpointRef","cancel-fixture");
   children.addObject().put("id","later").put("type","REST").put("endpointRef","cancel-fixture");
   routes.draft(route,definition,"test","cancel-order");routes.publish(route,1,0,"test","cancel-order");
   var admitted=context.getBean(AdmissionService.class).submit("test",UUID.randomUUID().toString(),new AdmissionService.Request(route,1,"CRITICAL","NOW_OR_REJECT",json.createObjectNode()),"cancel-order");
   assertEquals(202,admitted.status());String id=admitted.body().path("executionId").asText();
   var claimed=engine.claim(id);assertNotNull(claimed);assertFalse(claimed.observe());assertFalse(claimed.request().cancelRequested());
   assertEquals("active",claimed.request().node().path("id").asText());assertEquals(0,submits.get());
   assertEquals("INTENT_COMMITTED",db.queryForObject("SELECT state FROM step_attempts WHERE id=?",String.class,claimed.attemptId()));
   int port=((ServletWebServerApplicationContext)context).getWebServer().getPort();
   var request=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+"/executions/"+id+"/cancel"))
    .header("Authorization","Bearer "+Objects.requireNonNull(System.getenv("ROUTE_TEST_TOKEN"))).header("Content-Type","application/json").header("Idempotency-Key","cancel-order")
    .POST(HttpRequest.BodyPublishers.ofString("{\"reason\":\"cancel after durable claim before HTTP submit\"}")).build();
   var cancelled=HttpClient.newHttpClient().send(request,HttpResponse.BodyHandlers.ofString());assertEquals(202,cancelled.statusCode(),cancelled.body());
   assertEquals("CANCEL_REQUESTED",json.readTree(cancelled.body()).path("code").asText());assertEquals("CANCELING:1",state(db,id));assertEquals(0,submits.get());
   assertNull(engine.claim(id),"No fresh sibling dispatch after cancel while existing intent lease is held");
   assertTrue(engine.execute(claimed));assertEquals(1,submits.get());assertEquals(claimed.request().operationId(),operation.get());
   assertEquals("CANCELING:1",state(db,id));assertEquals(1,number(db,"SELECT permit_generation FROM executions WHERE id=?",id));
   var firstCancel=due(engine,id);assertTrue(firstCancel.observe());assertTrue(firstCancel.request().cancelRequested());assertEquals(operation.get(),firstCancel.request().operationId());
   assertTrue(engine.execute(firstCancel));assertEquals(1,deletes.get());assertEquals(1,observes.get());
   assertEquals("CANCELING:1",state(db,id),"DELETE202 and WAITING observation are not stopped evidence");
   terminalEvidence.set(true);
   var confirmed=due(engine,id);assertEquals(operation.get(),confirmed.request().operationId());assertTrue(confirmed.request().cancelRequested());
   assertTrue(engine.execute(confirmed));assertEquals("CANCELLED:0",state(db,id));
   assertEquals(1,submits.get());assertEquals(2,deletes.get());assertEquals(2,observes.get());assertEquals(1,confirmed.permitGeneration());
   assertEquals(1,number(db,"SELECT permit_generation FROM executions WHERE id=?",id));
   assertEquals(1,number(db,"SELECT COUNT(*) FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE execution_id=?",id));
   assertEquals(0,number(db,"SELECT COUNT(*) FROM step_runs WHERE execution_id=? AND node_id IN ('unclaimed','later') AND attempt_count>0",id));
   assertEquals("STOPPED",db.queryForObject("SELECT state FROM step_runs WHERE execution_id=? AND node_id='unclaimed'",String.class,id));
   assertEquals("STOPPED",db.queryForObject("SELECT state FROM step_attempts WHERE id=?",String.class,claimed.attemptId()));
   assertNull(engine.claim(id));assertFalse(engine.execute(claimed));assertEquals(1,submits.get());
   var proof=json.createObjectNode().put("executionId",id).put("operationId",operation.get()).put("submitAfterCancel",submits.get()).put("cancelRequests",deletes.get())
    .put("observations",observes.get()).put("permitGeneration",confirmed.permitGeneration()).put("finalState",state(db,id)).put("newClaimsAfterCancel",0).put("heldUntilTerminalObservation",true).put("engineDatabase",expectedDatabase).put("distinctEngineDatabase",true);
   proof.set("httpEvents",json.valueToTree(events));System.out.println("CANCEL_INTERLEAVING_PROOF "+proof);
  }finally{remote.stop(0);}
 }
}
