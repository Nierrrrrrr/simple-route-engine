package dev.routeengine.engine;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
/** I/O methods always run outside a transaction. UNKNOWN never permits resubmission. */
public interface OperationAdapter {
 enum Status { SUCCEEDED, FAILED, WAITING, UNKNOWN, STOPPED }
 record Request(String operationId,long operationGeneration,int attempt,String direction,JsonNode node,JsonNode input,
                JsonNode context,String externalUid,boolean cancelRequested){
  public Request(String operationId,long operationGeneration,int attempt,String direction,JsonNode node,JsonNode input){
   this(operationId,operationGeneration,attempt,direction,node,input,JsonNodeFactory.instance.objectNode(),null,false);
  }
  public Request planned(JsonNode plan){return new Request(operationId,operationGeneration,attempt,direction,node,input,plan,externalUid,cancelRequested);}
 }
 record Outcome(Status status,JsonNode output,boolean retryable,String externalUid){
  public static Outcome unknown(){return new Outcome(Status.UNKNOWN,null,false,null);}
 }
 boolean supports(JsonNode node);
 /** Pure nonsecret publication semantics. Unknown contracts must fail publication, not guess. */
 default JsonNode binding(JsonNode node){throw new IllegalArgumentException("Unversioned adapter");}
 /** Pure local planning from already-loaded config. No external I/O, credentials or DB writes. */
 default JsonNode plan(Request request){return JsonNodeFactory.instance.objectNode();}
 Outcome submit(Request request);
 Outcome observe(Request request);
 Outcome cancel(Request request);
}
