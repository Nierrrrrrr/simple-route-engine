package dev.routeengine.adapters;
import com.fasterxml.jackson.databind.*;
import dev.routeengine.engine.OperationAdapter;
import java.net.URI;
import java.net.http.*;
import java.nio.ByteBuffer;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.Flow;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronizationManager;
/** Controlled JSON operation protocol. Acceptance and transport errors are never terminal. */
@Component
public class RestAdapter implements OperationAdapter {
 private final AdapterCatalog catalog;private final ObjectMapper json;
 private final HttpClient client=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).followRedirects(HttpClient.Redirect.NEVER).build();
 public RestAdapter(AdapterCatalog catalog,ObjectMapper json){this.catalog=catalog;this.json=json;}
 public boolean supports(JsonNode node){return node.path("type").asText().equals("REST")&&!catalog.endpoint(node.path("endpointRef").asText()).isMissingNode();}
 public JsonNode binding(JsonNode node){
  if(!supports(node))throw new IllegalArgumentException("Unsupported REST reference");
  return catalog.plan(node.path("endpointRef").asText(),catalog.endpoint(node.path("endpointRef").asText())).put("nodeType","REST");
 }
 public JsonNode plan(Request r){return binding(r.node()).deepCopy();}
 public Outcome submit(Request r){return send(r,"POST","");}
 public Outcome observe(Request r){
  var c=catalog.endpoint(r.node().path("endpointRef").asText());
  if(!c.path("query").asBoolean(false))return Outcome.unknown();
  return send(r,"GET","/"+r.operationId());
 }
 public Outcome cancel(Request r){
  var c=catalog.endpoint(r.node().path("endpointRef").asText());
  if(!c.path("cancel").asBoolean(false))return observe(r);
  Outcome submitted=send(r,"DELETE","/"+r.operationId());
  return submitted.status()==Status.UNKNOWN?submitted:observe(r);
 }
 private Outcome send(Request r,String method,String suffix){
  if(TransactionSynchronizationManager.isActualTransactionActive())throw new IllegalStateException("External I/O inside transaction");
  var c=catalog.endpoint(r.node().path("endpointRef").asText());
  if(!supports(r.node())||!catalog.matches(r.context(),c))return Outcome.unknown();
  CompletableFuture<HttpResponse<byte[]>> call=null;
  try{
   String secret=catalog.credential(c);
   URI uri=URI.create(c.path("baseUri").asText().replaceAll("/$","")+suffix);
   var builder=HttpRequest.newBuilder(uri).timeout(Duration.ofMillis(c.path("timeoutMillis").asInt())).header("Accept","application/json");
   if(!secret.isEmpty())builder.header("Authorization","Bearer "+secret);
   if(method.equals("POST")){
    var body=json.createObjectNode().put("operationId",r.operationId()).put("direction",r.direction()).put("operationGeneration",r.operationGeneration());
    body.set("input",r.input());catalog.safeOutput(r.input(),secret);
    builder.header("Content-Type","application/json").header("Idempotency-Key",r.operationId()).POST(HttpRequest.BodyPublishers.ofString(body.toString()));
   }else builder.method(method,HttpRequest.BodyPublishers.noBody());
   call=client.sendAsync(builder.build(),info->new LimitedBody(c.path("maxResponseBytes").asInt()));
   var response=call.orTimeout(c.path("timeoutMillis").asInt(),TimeUnit.MILLISECONDS).join();
   int code=response.statusCode();
   if(code>=300&&code<400)return Outcome.unknown();
   if(method.equals("DELETE"))return code>=200&&code<300?new Outcome(Status.WAITING,null,false,r.externalUid()):Outcome.unknown();
   if(code==404&&method.equals("GET"))return Outcome.unknown();
   JsonNode body=json.readTree(response.body());
   if(!body.path("operationId").asText().equals(r.operationId()))return Outcome.unknown();
   if(code==202)return new Outcome(Status.WAITING,null,false,r.operationId());
   String state=body.path("status").asText();
   if(state.equals("WAITING"))return new Outcome(Status.WAITING,null,false,r.operationId());
   if(state.equals("SUCCEEDED")&&code>=200&&code<300)return new Outcome(Status.SUCCEEDED,catalog.safeOutput(body.path("output").isMissingNode()?json.createObjectNode():body.get("output"),secret),false,r.operationId());
   if(state.equals("STOPPED"))return new Outcome(Status.STOPPED,json.createObjectNode(),false,r.operationId());
   if(state.equals("FAILED"))return new Outcome(Status.FAILED,null,body.path("retryable").asBoolean(false),r.operationId());
   return Outcome.unknown();
  }catch(Exception e){if(call!=null)call.cancel(true);return Outcome.unknown();}
 }
 private static class LimitedBody implements HttpResponse.BodySubscriber<byte[]> {
  private final HttpResponse.BodySubscriber<byte[]> delegate=HttpResponse.BodySubscribers.ofByteArray();
  private final int limit;private long bytes;private Flow.Subscription subscription;
  LimitedBody(int limit){this.limit=limit;}
  public CompletionStage<byte[]> getBody(){return delegate.getBody();}
  public void onSubscribe(Flow.Subscription s){subscription=s;delegate.onSubscribe(s);}
  public void onNext(List<ByteBuffer> chunks){for(var b:chunks)bytes+=b.remaining();if(bytes>limit){subscription.cancel();delegate.onError(new IllegalArgumentException("Response too large"));}else delegate.onNext(chunks);}
  public void onError(Throwable e){delegate.onError(e);}
  public void onComplete(){delegate.onComplete();}
 }
}
