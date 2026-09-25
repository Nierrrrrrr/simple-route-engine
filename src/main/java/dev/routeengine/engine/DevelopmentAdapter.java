package dev.routeengine.engine;

import com.fasterxml.jackson.databind.*;
import java.nio.file.*;
import java.io.IOException;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/** Explicit development profile only. A persisted operation file models a separate remote system.
 * Route definitions cannot choose paths. This is NOT a production REST/Kubernetes/Ansible adapter. */
@Component
@Profile("engine-development")
public class DevelopmentAdapter implements OperationAdapter {
 private final ObjectMapper json;private final Path base;
 public DevelopmentAdapter(ObjectMapper json,@Value("${route.engine.fixture-directory}") String directory){
  this.json=json;this.base=Path.of(directory).toAbsolutePath().normalize();
  try{Files.createDirectories(base);}catch(IOException e){throw new IllegalStateException("Development fixture directory unavailable");}
 }
 public boolean supports(JsonNode n){return n.path("type").asText().equals("REST")&&Set.of("dev.success","dev.fail","dev.flaky","dev.pending","dev.unknown","dev.throw").contains(n.path("endpointRef").asText());}
 public JsonNode binding(JsonNode n){
  if(!supports(n))throw new IllegalArgumentException("Unknown development fixture");
  return json.createObjectNode().put("nodeType","REST").put("ref",n.path("endpointRef").asText()).put("developmentContract",1);
 }
 private Path file(String id,String suffix){if(!id.matches("[a-f0-9-]{36}"))throw new IllegalArgumentException("Invalid operation identity");return base.resolve(id+suffix);}
 private void outside(){if(TransactionSynchronizationManager.isActualTransactionActive())throw new IllegalStateException("Adapter I/O inside DB transaction");}
 public Outcome submit(Request r){
  outside();Path intent=file(r.operationId(),".operation.json");
  try{
   var d=json.createObjectNode().put("operationId",r.operationId()).put("attempt",r.attempt()).put("ref",r.node().path("endpointRef").asText());d.set("input",r.input().deepCopy());
   try{Files.writeString(intent,d.toString(),StandardOpenOption.CREATE_NEW);}catch(FileAlreadyExistsException existing){return observe(r);}
   return result(r);
  }catch(IOException e){return Outcome.unknown();}
 }
 public Outcome observe(Request r){outside();if(!Files.isRegularFile(file(r.operationId(),".operation.json")))return Outcome.unknown();return result(r);}
 private Outcome result(Request r){
  String ref=r.node().path("endpointRef").asText();
  if(ref.equals("dev.throw"))throw new IllegalStateException("Controlled adapter exception");
  if(ref.equals("dev.unknown"))return Outcome.unknown();
  if(ref.equals("dev.pending")){
   var p=file(r.operationId(),".result.json");if(!Files.isRegularFile(p))return new Outcome(Status.WAITING,null,false,r.operationId());
   try{var v=json.readTree(Files.readString(p));return new Outcome(Status.valueOf(v.path("status").asText()),v.path("output"),false,r.operationId());}catch(Exception e){return Outcome.unknown();}
  }
  if(ref.equals("dev.fail")||(ref.equals("dev.flaky")&&r.attempt()<2))return new Outcome(Status.FAILED,null,true,r.operationId());
  return new Outcome(Status.SUCCEEDED,r.input().deepCopy(),false,r.operationId());
 }
 public Outcome cancel(Request r){outside();return observe(r);}
}