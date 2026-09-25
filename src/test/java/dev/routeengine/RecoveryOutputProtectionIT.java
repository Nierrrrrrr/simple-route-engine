package dev.routeengine;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import com.sun.net.httpserver.HttpServer;
import dev.routeengine.admission.AdmissionService;
import dev.routeengine.engine.EngineService;
import dev.routeengine.registry.RouteRegistry;
import dev.routeengine.recovery.OperatorService;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.*;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.stream.*;
import static org.junit.jupiter.api.Assertions.*;

/** Public operator requests, real REST adapter and a separately owned MariaDB; synthetic credentials only. */
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class RecoveryOutputProtectionIT {
 @TempDir static Path temp;
 final ObjectMapper json=new ObjectMapper();final HttpClient http=HttpClient.newHttpClient();
 final Map<String,String> secrets=new LinkedHashMap<>();final Map<String,Integer> submissions=new ConcurrentHashMap<>();
 final Set<String> stopped=ConcurrentHashMap.newKeySet();final List<String> owned=new ArrayList<>();
 final ArrayNode proof=json.createArrayNode();ConfigurableApplicationContext context;HttpServer remote;JdbcTemplate db;EngineService engine;AdmissionService admission;int port;boolean databaseVerified;
 static final List<String> SHAPES=List.of("plain","escaped","nested","field","integer","decimal","true","false","null","credential");
 static Stream<Arguments> cases(){return Stream.of("resolve","skip-queue","skip-now","capacity-reject").flatMap(mode->SHAPES.stream().map(shape->Arguments.of(mode,shape)));}
 @BeforeAll void setup()throws Exception{
  secrets.put("plain","canary-"+UUID.randomUUID());secrets.put("escaped","quote-\"-slash-\\-"+UUID.randomUUID());
  for(String shape:List.of("nested","field","credential"))secrets.put(shape,"canary-"+UUID.randomUUID());
  secrets.put("integer","879431056287940123765982314678951");secrets.put("decimal","1.25E18");secrets.put("true","true");secrets.put("false","false");secrets.put("null","null");
  remote=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
  remote.createContext("/",e->{
   String[] path=e.getRequestURI().getPath().substring(1).split("/");String shape=path[0],mode=path[1],op;
   String status;ObjectNode body=json.createObjectNode();
   if(e.getRequestMethod().equals("POST")){
    var input=json.readTree(e.getRequestBody());op=input.path("operationId").asText();submissions.merge(op,1,Integer::sum);
    status=mode.equals("failed")?"FAILED":"SUCCEEDED";body.putObject("output").put("value",secrets.get(shape));
   }else{op=path[2];if(e.getRequestMethod().equals("DELETE"))stopped.add(op);status=stopped.contains(op)?"STOPPED":"UNKNOWN";}
   body.put("operationId",op).put("status",status).put("retryable",false);
   byte[] bytes=body.toString().getBytes(StandardCharsets.UTF_8);e.sendResponseHeaders(status.equals("FAILED")?500:200,bytes.length);e.getResponseBody().write(bytes);e.close();
  });remote.start();
  var config=json.createObjectNode();var endpoints=config.putObject("endpoints");var credentials=config.putObject("credentials");
  for(var entry:secrets.entrySet()){
   Path file=temp.resolve(entry.getKey()+".credential");Files.writeString(file,entry.getValue());credentials.put(entry.getKey(),file.toString());
   for(String mode:List.of("leak","failed"))endpoints.putObject(entry.getKey()+"-"+mode)
    .put("baseUri","http://127.0.0.1:"+remote.getAddress().getPort()+"/"+entry.getKey()+"/"+mode).put("allowedHost","127.0.0.1").put("allowLoopbackHttp",true)
    .put("query",true).put("cancel",true).put("timeoutMillis",2000).put("maxResponseBytes",4096).put("credentialRef",entry.getKey());
  }
  Path catalog=temp.resolve("catalog.json");Files.writeString(catalog,config.toString());
  context=new SpringApplication(RouteEngineApplication.class).run("--server.port=0","--route.scheduler.enabled=false","--route.engine.enabled=false","--route.adapters.config="+catalog,
   "--spring.datasource.url=${ROUTE_ENGINE_TEST_DB_URL}","--spring.datasource.username=${ROUTE_ENGINE_TEST_DB_USER}","--spring.datasource.password=${ROUTE_ENGINE_TEST_DB_PASSWORD}");
  db=context.getBean(JdbcTemplate.class);engine=context.getBean(EngineService.class);admission=context.getBean(AdmissionService.class);port=((ServletWebServerApplicationContext)context).getWebServer().getPort();
  assertTrue(db.queryForObject("SELECT VERSION()",String.class).contains("MariaDB"));
  String expected=Objects.requireNonNull(System.getenv("ROUTE_ENGINE_TEST_DB_URL")).split("\\?")[0];
  assertNotEquals(System.getenv("ROUTE_DB_URL").split("\\?")[0],expected);
  try(var connection=db.getDataSource().getConnection()){assertEquals(expected,connection.getMetaData().getURL().split("\\?")[0]);databaseVerified=true;}
 }
 String state(String id){return db.queryForObject("SELECT CONCAT(state,':',permit_held) FROM executions WHERE id=?",String.class,id);}
 void config(int total){admission.configure(new AdmissionService.Config(total,0,6,3,1,true,admission.capacity().path("configVersion").asLong(),"isolated output boundary"),"operator","fixture");}
 String start(String shape,boolean unknown,boolean run)throws Exception{return start(shape,unknown,run,false);}
 String start(String shape,boolean unknown,boolean run,boolean typed)throws Exception{
  String route="demo-output-"+UUID.randomUUID().toString().substring(0,8);var registry=context.getBean(RouteRegistry.class);registry.create(route,"DEMO operator output guard","test","fixture");
  var d=json.createObjectNode().put("routeId",route).put("version",1).put("dslVersion","1").put("engineSemanticsVersion","1").put("adapterContractVersion","1");
  var node=d.putObject("root").put("id","root").put("type","SEQUENCE").putArray("children").addObject().put("id","work").put("type","REST").put("endpointRef",shape+(unknown?"-leak":"-failed"));
  var schema=node.putObject("outputSchema").put("type","object");
  if(typed){schema.putObject("properties").putObject("value").put("type","string");schema.putArray("required").add("value");}
  registry.draft(route,d,"test","fixture");registry.publish(route,1,0,"test","fixture");
  var result=admission.submit("test",UUID.randomUUID().toString(),new AdmissionService.Request(route,1,"CRITICAL","NOW_OR_REJECT",json.createObjectNode()),"fixture");assertEquals(202,result.status());String id=result.body().path("executionId").asText();owned.add(id);
  if(run){engine.tick(id);assertEquals(unknown?"RECONCILING:1":"MANUAL_WAIT:0",state(id));}return id;
 }
 JsonNode incident(String id){var all=context.getBean(OperatorService.class).incidents(id).path("incidents");assertEquals(1,all.size());return all.get(0);}
 ObjectNode output(String shape)throws Exception{
  var out=json.createObjectNode();String secret=secrets.get(shape);
  switch(shape){
   case "nested" -> out.putArray("outer").addArray().addObject().put("value",secret);
   case "field" -> out.put("prefix-"+secret+"-suffix","ordinary");
   case "integer","decimal","true","false","null" -> out.set("value",json.readTree(secret));
   case "credential" -> out.put("CrEdEnTiAl","ordinary");
   default -> out.put("value",secret);
  }return out;
 }
 ObjectNode body(JsonNode i,boolean resolve,String mode,JsonNode output){
  var b=json.createObjectNode().put("stepId",i.path("stepId").asText()).put("reason","fixture verified nonsecret decision");
  if(resolve){b.put("operationId",i.path("operationId").asText()).put("outcome","SUCCEEDED").put("evidence","fixture exact operation result");b.set("output",output);}
  else{b.put("incidentId",i.path("incidentId").asText()).put("action","SKIP").put("admissionMode",mode.equals("skip-queue")?"QUEUE":"NOW_OR_REJECT");b.set("replacementOutput",output);}
  return b;
 }
 String path(String id,JsonNode i,boolean resolve){return "/executions/"+id+(resolve?"/incidents/"+i.path("incidentId").asText()+"/resolve":"/recoveries");}
 HttpResponse<String> post(String path,JsonNode body,String key,String requestId)throws Exception{
  return http.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+path)).header("Authorization","Bearer "+Objects.requireNonNull(System.getenv("ROUTE_TEST_TOKEN")))
   .header("Content-Type","application/json").header("Idempotency-Key",key).header("X-Request-ID",requestId).POST(HttpRequest.BodyPublishers.ofString(body.toString())).build(),HttpResponse.BodyHandlers.ofString());
 }
 Map<String,Object> snapshot(String id){
  var result=new LinkedHashMap<String,Object>();
  for(String table:List.of("executions","engine_incidents","step_runs","admission_requests","operator_commands","execution_events"))result.put(table,db.queryForList("SELECT * FROM "+table+" WHERE "+(table.equals("executions")?"id":"execution_id")+"=? ORDER BY id",id));
  result.put("attempts",db.queryForList("SELECT a.* FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE r.execution_id=? ORDER BY a.id",id));
  result.put("pool",db.queryForList("SELECT * FROM scheduler_pool"));return result;
 }
 void reject(String name,String id,JsonNode i,String path,ObjectNode body,String key,String requestId)throws Exception{
  var before=snapshot(id);var response=post(path,body,key,requestId);boolean unchanged=before.equals(snapshot(id));
  int submits=submissions.getOrDefault(i.path("operationId").asText(),0);
  proof.addObject().put("case",name).put("status",response.statusCode()).put("unchanged",unchanged).put("submits",submits).put("state",state(id));
  assertAll(name,()->assertEquals(422,response.statusCode(),"Unsafe operator payload must be rejected"),()->assertTrue(unchanged,"Rejected request mutated persisted state"),()->assertEquals(1,submits,"Operator request must not submit external work"));
 }
 @ParameterizedTest(name="AC041_{0}_{1}") @MethodSource("cases")
 void AC041_AC045_AC049_operatorOutputsCannotBypassBoundCredentialGuard(String mode,String shape)throws Exception{
  boolean resolve=mode.equals("resolve");String id=start(shape,resolve,true);var i=incident(id);
  if(mode.equals("capacity-reject")){config(1);start("plain",false,false);}
  reject(mode+":"+shape,id,i,path(id,i,resolve),body(i,resolve,mode,output(shape)),UUID.randomUUID().toString(),"operator-boundary");
 }
 @ParameterizedTest @ValueSource(strings={"resolve-reason","resolve-evidence","resolve-key","resolve-requestId","skip-reason","skip-key","cancel-reason","cancel-key"})
 void AC041_operatorMetadataMustNotPersistBoundCredential(String location)throws Exception{
  boolean cancel=location.startsWith("cancel"),resolve=location.startsWith("resolve");String id=start("plain",resolve||cancel,true);var i=incident(id);String secret=secrets.get("plain"),key=UUID.randomUUID().toString(),rid="operator-boundary";
  var b=cancel?json.createObjectNode().put("reason","ordinary stop"):body(i,resolve,"skip-now",json.createObjectNode().put("value","ordinary"));
  if(location.endsWith("reason"))b.put("reason",secret);if(location.endsWith("evidence"))b.put("evidence",secret);if(location.endsWith("key"))key=secret;if(location.endsWith("requestId"))rid=secret;
  reject(location,id,i,cancel?"/executions/"+id+"/cancel":path(id,i,resolve),b,key,rid);
 }
 @ParameterizedTest @ValueSource(strings={"resolve","skip-queue","skip-now","capacity-reject"})
 void AC041_legitimateTypedOutputAndOriginalReplayRemainUsable(String mode)throws Exception{
  boolean resolve=mode.equals("resolve");String id=start("plain",resolve,true,true);var i=incident(id);if(mode.equals("capacity-reject")){config(1);start("plain",false,false);}
  var out=json.createObjectNode().put("value","ordinary");out.putObject("detail").putNull("optional");var b=body(i,resolve,mode,out);String key=UUID.randomUUID().toString(),path=path(id,i,resolve);
  var response=post(path,b,key,"operator-control");int expected=resolve?200:mode.equals("capacity-reject")?409:202;assertEquals(expected,response.statusCode(),"Legitimate output must remain supported");
  Path file=temp.resolve("plain.credential"),unavailable=temp.resolve("plain.temporarily-unavailable");Files.move(file,unavailable);
  try{var replay=post(path,b,key,"operator-control");assertEquals(response.statusCode(),replay.statusCode());assertEquals(json.readTree(response.body()),json.readTree(replay.body()));}finally{Files.move(unavailable,file);}
  if(mode.equals("skip-queue"))assertEquals(id,admission.tick());if(!mode.equals("capacity-reject"))engine.tick(id);
  assertEquals(mode.equals("capacity-reject")?"MANUAL_WAIT:0":"SUCCEEDED:0",state(id));assertEquals(1,submissions.get(i.path("operationId").asText()));
  proof.addObject().put("case","control:"+mode).put("status",response.statusCode()).put("state",state(id)).put("replayWithoutCredentialFile",true).put("submits",1);
 }
 @ParameterizedTest @CsvSource({"null,STOPPED","true,FAILED","false,RETRY","null,CANCEL","true,CANCEL"})
 void AC041_structuralAbsentOutputDoesNotEqualLiteralCredential(String shape,String action)throws Exception{
  boolean resolve=Set.of("STOPPED","FAILED").contains(action);String id=start(shape,resolve,true);var i=incident(id);
  var b=body(i,resolve,"skip-now",null);b.put(resolve?"outcome":"action",action);
  var response=post(path(id,i,resolve),b,UUID.randomUUID().toString(),"operator-absent");assertEquals(resolve?200:202,response.statusCode(),"Absent optional output must not trigger credential detection");
  if(!resolve)engine.tick(id);assertEquals(action.equals("CANCEL")?"CANCELLED:0":"MANUAL_WAIT:0",state(id));
  proof.addObject().put("case","absent:"+shape+":"+action).put("status",response.statusCode()).put("state",state(id)).put("optionalOutputAbsent",true);
 }
 @AfterEach void cleanup()throws Exception{
  for(String id:owned){
   if(state(id).startsWith("RECOVERY_QUEUED"))context.getBean(OperatorService.class).cancel(id,"test",UUID.randomUUID().toString(),new OperatorService.Cancel("fixture withdrawal"),"fixture");
   if(state(id).endsWith(":1")){
    engine.requestCancel(id,"test","fixture stop");Instant until=Instant.now().plusSeconds(5);
    while(state(id).endsWith(":1")&&Instant.now().isBefore(until)){engine.tick(id);Thread.sleep(25);}
    assertFalse(state(id).endsWith(":1"),"Fixture must converge its own actual operation");
   }
  }owned.clear();config(100);
 }
 @AfterAll void close()throws Exception{
  try{Files.createDirectories(Path.of("target"));Files.writeString(Path.of("target/operator-output-proof.json"),json.createObjectNode().put("syntheticCredentialsOnly",true).put("distinctEngineDatabase",databaseVerified).set("cases",proof).toPrettyString());}
  finally{if(context!=null)context.close();if(remote!=null)remote.stop(0);}
 }
}

