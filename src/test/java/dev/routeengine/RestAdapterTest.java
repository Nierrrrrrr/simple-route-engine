package dev.routeengine;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.HttpExchange;
import dev.routeengine.adapters.*;
import dev.routeengine.engine.OperationAdapter.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import java.net.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import static org.junit.jupiter.api.Assertions.*;
class RestAdapterTest {
 @TempDir Path temp;
 ObjectMapper json=new ObjectMapper(); HttpServer server; ExecutorService executor;
 RestAdapter adapter; AdapterCatalog catalog; String secret="fixture-secret-"+UUID.randomUUID();
 AtomicInteger submits=new AtomicInteger(),effects=new AtomicInteger(),redirected=new AtomicInteger();
 Set<String> operations=ConcurrentHashMap.newKeySet();volatile String mode="sync";volatile boolean ready;
 @BeforeEach void setup() throws Exception {
  server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);executor=Executors.newCachedThreadPool();server.setExecutor(executor);
  server.createContext("/operations",this::handle);server.createContext("/leak",e->{redirected.incrementAndGet();e.sendResponseHeaders(500,-1);e.close();});server.start();
  var cfg=json.createObjectNode();var endpoints=cfg.putObject("endpoints");
  for(String ref:List.of("fixture","noquery")){
   endpoints.putObject(ref).put("baseUri","http://127.0.0.1:"+server.getAddress().getPort()+"/operations").put("allowedHost","127.0.0.1").put("allowLoopbackHttp",true).put("query",!ref.equals("noquery")).put("cancel",true).put("timeoutMillis",250).put("maxResponseBytes",1024).put("credentialRef","fixture");
  }
  Path credential=temp.resolve("credential");Files.writeString(credential,secret);cfg.putObject("credentials").put("fixture",credential.toString());
  Path file=temp.resolve("catalog.json");Files.writeString(file,cfg.toString());catalog=new AdapterCatalog(json,file.toString());adapter=new RestAdapter(catalog,json);
 }
 @AfterEach void close(){server.stop(0);executor.shutdownNow();}
 void handle(HttpExchange e) throws java.io.IOException {
  try{
   assertEquals("Bearer "+secret,e.getRequestHeaders().getFirst("Authorization"));
   String op;
   if(e.getRequestMethod().equals("POST")){
    var body=json.readTree(e.getRequestBody());op=body.path("operationId").asText();assertEquals(op,e.getRequestHeaders().getFirst("Idempotency-Key"));submits.incrementAndGet();if(operations.add(op))effects.incrementAndGet();
   }else op=e.getRequestURI().getPath().substring("/operations/".length());
   if(mode.equals("drop")){e.close();return;}
   if(mode.equals("timeout")){Thread.sleep(700);e.close();return;}
   if(mode.equals("redirect")){e.getResponseHeaders().set("Location","/leak");e.sendResponseHeaders(307,-1);e.close();return;}
   String state=mode.equals("async")&&!ready?"WAITING":Set.of("400","500").contains(mode)?"FAILED":"SUCCEEDED";
   var body=json.createObjectNode().put("operationId",op).put("status",state).put("retryable",mode.equals("500"));
   body.putObject("output").put("value",mode.equals("secret")?secret:mode.equals("large")?"x".repeat(2048):"ok");
   if(mode.equals("wrong"))body.put("operationId",UUID.randomUUID().toString());
   byte[] bytes=body.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);
   int status=mode.equals("400")?400:mode.equals("500")?500:mode.equals("async")&&!ready?202:200;
   e.sendResponseHeaders(status,bytes.length);e.getResponseBody().write(bytes);e.close();
  }catch(InterruptedException interrupted){Thread.currentThread().interrupt();e.close();}
 }
 Request request(String ref){var n=json.createObjectNode().put("type","REST").put("endpointRef",ref);var r=new Request(UUID.randomUUID().toString(),1,1,"FORWARD",n,json.createObjectNode());return r.planned(adapter.plan(r));}
 @Test void AC032_syncAndAcceptedNeedTerminalPoll(){var r=request("fixture");assertEquals(Status.SUCCEEDED,adapter.submit(r).status());mode="async";r=request("fixture");assertEquals(Status.WAITING,adapter.submit(r).status());assertEquals(Status.WAITING,adapter.observe(r).status());ready=true;assertEquals(Status.SUCCEEDED,adapter.observe(r).status());}
 @Test void AC032_explicit4xxAnd5xxKnownFailures(){mode="400";var o=adapter.submit(request("fixture"));assertEquals(Status.FAILED,o.status());assertFalse(o.retryable());mode="500";o=adapter.submit(request("fixture"));assertEquals(Status.FAILED,o.status());assertTrue(o.retryable());}
 @Test void AC032_timeoutAndLostResponseRemainUnknown(){for(String m:List.of("timeout","drop")){mode=m;var r=request("fixture");assertEquals(Status.UNKNOWN,adapter.submit(r).status());mode="sync";assertEquals(Status.SUCCEEDED,adapter.observe(r).status());}assertEquals(2,effects.get());}
 @Test void AC034_noQueryUnknownNeverSubmitsDuringObserve(){mode="drop";var r=request("noquery");assertEquals(Status.UNKNOWN,adapter.submit(r).status());for(int i=0;i<3;i++)assertEquals(Status.UNKNOWN,adapter.observe(r).status());assertEquals(1,submits.get());}
 @Test void AC039_transportDedupesButNewBusinessAndDirectionHaveNewIdentity(){var first=request("fixture");adapter.submit(first);adapter.submit(first);assertEquals(2,submits.get());assertEquals(1,effects.get());var second=request("fixture");assertNotEquals(first.operationId(),second.operationId());adapter.submit(second);var rollback=new Request(UUID.randomUUID().toString(),2,2,"ROLLBACK",first.node(),first.input()).planned(first.context());adapter.submit(rollback);assertEquals(3,effects.get());}
 @Test void AC041_redirectSizeSecretAndMismatchedIdentityFailClosed(){for(String m:List.of("redirect","large","secret","wrong")){mode=m;assertEquals(Status.UNKNOWN,adapter.submit(request("fixture")).status(),m);}assertEquals(0,redirected.get());}
 @Test void AC041_catalogRejectsUnsafeHostAndPlaintextRemote() throws Exception {
  Path file=temp.resolve("unsafe.json");Files.writeString(file,"{\"endpoints\":{\"a\":{\"baseUri\":\"http://example.com\",\"allowedHost\":\"example.com\",\"timeoutMillis\":1000,\"maxResponseBytes\":1024}}}");
  assertThrows(IllegalArgumentException.class,()->new AdapterCatalog(json,file.toString()));
  Files.writeString(file,"{\"endpoints\":{\"a\":{\"baseUri\":\"https://example.com\",\"allowedHost\":\"evil.example\",\"timeoutMillis\":1000,\"maxResponseBytes\":1024}}}");
  assertThrows(IllegalArgumentException.class,()->new AdapterCatalog(json,file.toString()));
 }
}
