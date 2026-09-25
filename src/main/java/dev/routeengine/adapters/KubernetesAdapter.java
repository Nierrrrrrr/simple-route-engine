package dev.routeengine.adapters;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import dev.routeengine.engine.OperationAdapter;
import io.fabric8.kubernetes.api.model.*;
import io.fabric8.kubernetes.api.model.apps.Deployment;
import io.fabric8.kubernetes.api.model.batch.v1.Job;
import io.fabric8.kubernetes.client.*;
import io.fabric8.kubernetes.client.utils.Serialization;
import java.nio.file.*;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/** Only catalog-bound, operation-owned resources. The application Pod is never an owner. */
@Component
public class KubernetesAdapter implements OperationAdapter, AutoCloseable {
 private final AdapterCatalog catalog;private final ObjectMapper json;private final JdbcTemplate db;
 private volatile KubernetesClient client;
 public KubernetesAdapter(AdapterCatalog catalog,ObjectMapper json,JdbcTemplate db){this.catalog=catalog;this.json=json;this.db=db;}
 public boolean supports(JsonNode n){
  String t=n.path("type").asText(),kind=resource(n).path("kind").asText();
  return t.equals("ANSIBLE")?kind.equals("ANSIBLE"):t.equals("KUBERNETES")&&Set.of("DEPLOYMENT","JOB").contains(kind);
 }
 private JsonNode resource(JsonNode n){return catalog.resource(n.path(n.path("type").asText().equals("ANSIBLE")?"playbookRef":"resourceRef").asText());}
 public JsonNode binding(JsonNode node){
  if(!supports(node))throw new IllegalArgumentException("Unsupported resource kind");
  JsonNode c=resource(node);String ref=node.path(node.path("type").asText().equals("ANSIBLE")?"playbookRef":"resourceRef").asText();
  if(node.has("artifactDigest")&&!node.path("artifactDigest").asText().equals(c.path("artifactDigest").asText()))throw new IllegalArgumentException("Artifact digest mismatch");
  ObjectNode bound=catalog.plan(ref,c).put("nodeType",node.path("type").asText()).put("kind",c.path("kind").asText()).put("image",c.path("image").asText()).put("namespace",c.path("namespace").asText()).put("targetHash",catalog.kubernetesTargetHash());
  if(c.path("kind").asText().equals("ANSIBLE"))bound.put("playbook",c.path("playbook").asText()).put("artifactDigest",c.path("artifactDigest").asText());
  return bound;
 }
 public JsonNode plan(Request r){return ((ObjectNode)binding(r.node())).put("name","re-"+r.operationId()).put("generation",1);}
 private KubernetesClient client() throws Exception {
  if(client==null){synchronized(this){if(client==null){
   io.fabric8.kubernetes.client.Config config=catalog.kubernetesConfig();
   config.setRequestRetryBackoffLimit(0);
   config.setRequestTimeout(5000);config.setConnectionTimeout(5000);
   client=new KubernetesClientBuilder().withConfig(config).build();
  }}}
  return client;
 }
 private void outside(){if(TransactionSynchronizationManager.isActualTransactionActive())throw new IllegalStateException("External I/O inside transaction");}
 private boolean valid(Request r){
  return supports(r.node())&&catalog.matches(r.context(),resource(r.node()))
   &&r.context().path("targetHash").asText().equals(catalog.kubernetesTargetHash())
   &&r.context().path("kind").asText().equals(resource(r.node()).path("kind").asText())
   &&r.context().path("namespace").asText().equals(resource(r.node()).path("namespace").asText())
   &&r.context().path("generation").asInt()==1&&r.context().path("name").asText().equals("re-"+r.operationId());
 }
 private String ns(Request r){return r.context().path("namespace").asText();}
 private String name(Request r){return r.context().path("name").asText();}
 private boolean deployment(Request r){return r.context().path("kind").asText().equals("DEPLOYMENT");}
 public Outcome submit(Request r){
  outside();if(!valid(r))return Outcome.unknown();
  try{
   // This path is used only for the first durable intent. Reclaimed workers exclusively observe.
   HasMetadata existing=get(r);if(existing!=null)return inspect(r,existing);
   HasMetadata desired=manifest(r);
   try{if(desired instanceof Deployment d)client().apps().deployments().inNamespace(ns(r)).resource(d).create();else client().batch().v1().jobs().inNamespace(ns(r)).resource((Job)desired).create();}
   catch(KubernetesClientException conflict){if(conflict.getCode()!=409)throw conflict;}
   return observe(r);
  }catch(Exception e){return Outcome.unknown();}
 }
 public Outcome observe(Request r){
  outside();if(!valid(r))return Outcome.unknown();
  try{
   HasMetadata found=get(r);var stop=stop(r);
   if(!stop.isEmpty())return converge(r,found,stop);
   if(found==null)return Outcome.unknown(); // Includes previously submitted resources removed by GC.
   return inspect(r,found);
  }catch(Exception e){return Outcome.unknown();}
 }
 public Outcome cancel(Request r){
  outside();if(!valid(r))return Outcome.unknown();
  try{
   HasMetadata found=get(r);if(found==null)return observe(r);
   if(!identity(r,found))return Outcome.unknown();
   stopIntent(r,found,"CANCEL");
   return converge(r,found,stop(r));
  }catch(Exception e){return Outcome.unknown();}
 }
 private HasMetadata get(Request r)throws Exception{return deployment(r)?client().apps().deployments().inNamespace(ns(r)).withName(name(r)).get():client().batch().v1().jobs().inNamespace(ns(r)).withName(name(r)).get();}
 private boolean identity(Request r,HasMetadata found){
  var m=found.getMetadata();var labels=m.getLabels();
  return labels!=null&&r.operationId().equals(labels.get("route-engine.operation"))&&resource(r.node()).path("runId").asText().equals(labels.get("route-engine.run-id"))
   &&"adapter-work".equals(labels.get("route-engine.purpose"))&&(r.externalUid()==null||r.externalUid().equals(m.getUid()))
   &&(!deployment(r)||Objects.equals(m.getGeneration(),r.context().path("generation").asLong()));
 }
 private Map<String,Object> stop(Request r){var rows=db.queryForList("SELECT * FROM adapter_stops WHERE operation_id=?",r.operationId());return rows.isEmpty()?Map.of():rows.getFirst();}
 private void stopIntent(Request r,HasMetadata found,String reason){
  String uid=found.getMetadata().getUid();
  db.update("INSERT INTO adapter_stops(operation_id,resource_uid,reason) VALUES(?,?,?) ON DUPLICATE KEY UPDATE operation_id=operation_id",r.operationId(),uid,reason);
  if(!uid.equals(stop(r).get("resource_uid")))throw new IllegalStateException("Stop identity mismatch");
 }
 private Outcome converge(Request r,HasMetadata found,Map<String,Object> stop)throws Exception{
  String uid=(String)stop.get("resource_uid");
  if(found!=null){
   if(!identity(r,found)||!uid.equals(found.getMetadata().getUid()))return Outcome.unknown();
   // ResourceVersion precondition binds deletion to the already verified UID; a replacement conflicts.
   client().resource(found).inNamespace(ns(r)).lockResourceVersion(found.getMetadata().getResourceVersion()).delete();
   return new Outcome(Status.WAITING,null,false,uid);
  }
  var pods=client().pods().inNamespace(ns(r)).withLabel("route-engine.operation",r.operationId()).list().getItems();
  if(!pods.isEmpty())return new Outcome(Status.WAITING,null,false,uid);
  // This contract permits only synchronous local Pod work; untracked remote async is unsupported.
  return new Outcome(stop.get("reason").equals("FAILED")?Status.FAILED:Status.STOPPED,json.createObjectNode(),false,uid);
 }
 private Outcome inspect(Request r,HasMetadata found)throws Exception{
  if(!identity(r,found))return Outcome.unknown();
  String uid=found.getMetadata().getUid();
  var priorStop=stop(r);if(!priorStop.isEmpty())return converge(r,found,priorStop);
  if(found.getMetadata().getDeletionTimestamp()!=null)return new Outcome(Status.WAITING,null,false,uid);
  ObjectNode output=json.createObjectNode().put("name",name(r)).put("namespace",ns(r)).put("uid",uid).put("generation",found.getMetadata().getGeneration());
  if(found instanceof Deployment d){
   var s=d.getStatus();if(s==null)return new Outcome(Status.WAITING,null,false,uid);
   boolean failed=s.getConditions()!=null&&s.getConditions().stream().anyMatch(c->"Progressing".equals(c.getType())&&"False".equals(c.getStatus())&&"ProgressDeadlineExceeded".equals(c.getReason()));
   if(failed){stopIntent(r,found,"FAILED");return converge(r,found,stop(r));}
   boolean done=s.getObservedGeneration()!=null&&s.getObservedGeneration().equals(d.getMetadata().getGeneration())
    &&Integer.valueOf(1).equals(s.getUpdatedReplicas())&&Integer.valueOf(1).equals(s.getAvailableReplicas())&&Integer.valueOf(1).equals(s.getReplicas())&&(s.getUnavailableReplicas()==null||s.getUnavailableReplicas()==0);
   return new Outcome(done?Status.SUCCEEDED:Status.WAITING,done?output:null,false,uid);
  }
  Job job=(Job)found;var s=job.getStatus();
  if(s==null||s.getConditions()==null)return new Outcome(Status.WAITING,null,false,uid);
  boolean complete=s.getConditions().stream().anyMatch(c->"Complete".equals(c.getType())&&"True".equals(c.getStatus()));
  boolean failed=s.getConditions().stream().anyMatch(c->"Failed".equals(c.getType())&&"True".equals(c.getStatus()));
  boolean active=client().pods().inNamespace(ns(r)).withLabel("route-engine.operation",r.operationId()).list().getItems().stream().anyMatch(p->p.getStatus()==null||!Set.of("Succeeded","Failed").contains(p.getStatus().getPhase()));
  if(active||!complete&&!failed)return new Outcome(Status.WAITING,null,false,uid);
  if(resource(r.node()).path("kind").asText().equals("ANSIBLE"))output.putObject("artifacts").put("pvc",resource(r.node()).path("pvc").asText()).put("path",r.operationId()).put("artifactDigest",resource(r.node()).path("artifactDigest").asText());
  return new Outcome(complete?Status.SUCCEEDED:Status.FAILED,output,false,uid);
 }
 /** Controlled templates; route input cannot add shell, URLs, images, namespaces, async or env. */
 private HasMetadata manifest(Request r)throws Exception{
  JsonNode c=resource(r.node());ObjectNode root=json.createObjectNode().put("apiVersion",deployment(r)?"apps/v1":"batch/v1").put("kind",deployment(r)?"Deployment":"Job");
  ObjectNode labels=json.createObjectNode().put("route-engine.operation",r.operationId()).put("route-engine.run-id",c.path("runId").asText()).put("route-engine.purpose","adapter-work");
  root.putObject("metadata").put("name",name(r)).put("namespace",ns(r)).set("labels",labels);
  ObjectNode spec=root.putObject("spec");
  if(deployment(r)){spec.put("replicas",1).put("progressDeadlineSeconds",c.path("progressDeadlineSeconds").asInt(30));spec.putObject("selector").set("matchLabels",labels);}
  else spec.put("backoffLimit",0).put("completions",1).put("parallelism",1).put("activeDeadlineSeconds",300);
  ObjectNode template=spec.putObject("template");template.putObject("metadata").set("labels",labels.deepCopy());
  ObjectNode pod=template.putObject("spec").put("restartPolicy",deployment(r)?"Always":"Never").put("automountServiceAccountToken",false).put("terminationGracePeriodSeconds",5);
  ObjectNode security=pod.putObject("securityContext");security.put("runAsNonRoot",true).put("runAsUser",1000).put("runAsGroup",1000).put("fsGroup",1000);
  ObjectNode container=pod.putArray("containers").addObject().put("name","work").put("image",c.path("image").asText()).put("imagePullPolicy",c.path("imagePullPolicy").asText("IfNotPresent"));
  container.putArray("command").add("python").add("/opt/route/entrypoint.py");
  container.putObject("securityContext").put("allowPrivilegeEscalation",false).put("readOnlyRootFilesystem",true).putObject("capabilities").putArray("drop").add("ALL");
  container.putObject("resources").putObject("limits").put("cpu","500m").put("memory","256Mi");
  var env=container.putArray("env");env.addObject().put("name","MODE").put("value",deployment(r)?"server":c.path("kind").asText().equals("ANSIBLE")?"runner":"wait");
  env.addObject().put("name","OPERATION_ID").put("value",r.operationId());env.addObject().put("name","PLAYBOOK").put("value",c.path("playbook").asText("probe"));
  if(deployment(r)){container.putObject("readinessProbe").putObject("tcpSocket").put("port",8080);}
  var volumes=pod.putArray("volumes");volumes.addObject().put("name","tmp").putObject("emptyDir").put("sizeLimit","64Mi");
  var mounts=container.putArray("volumeMounts");mounts.addObject().put("name","tmp").put("mountPath","/tmp");
  if(c.path("kind").asText().equals("ANSIBLE")){
   volumes.addObject().put("name","artifacts").putObject("persistentVolumeClaim").put("claimName",c.path("pvc").asText());
   mounts.addObject().put("name","artifacts").put("mountPath","/artifacts");
   if(c.has("secretName")){
    volumes.addObject().put("name","credential").putObject("secret").put("secretName",c.path("secretName").asText()).put("defaultMode",288);
    mounts.addObject().put("name","credential").put("mountPath","/run/route-secrets").put("readOnly",true);
   }
  }
  return deployment(r)?Serialization.unmarshal(root.toString(),Deployment.class):Serialization.unmarshal(root.toString(),Job.class);
 }
 public void close(){if(client!=null)client.close();}
}
