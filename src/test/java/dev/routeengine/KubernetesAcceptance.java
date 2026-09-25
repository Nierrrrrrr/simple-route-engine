package dev.routeengine;
import com.fasterxml.jackson.databind.*;
import dev.routeengine.admission.AdmissionService;
import dev.routeengine.engine.*;
import dev.routeengine.registry.RouteRegistry;
import io.fabric8.kubernetes.client.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import java.util.*;
import java.nio.file.*;
import java.time.Duration;
import static org.junit.jupiter.api.Assertions.*;
/** Explicit M4 suite. No skipped-on-unavailable or mock Kubernetes fallback. */
@SpringBootTest(properties={"route.scheduler.enabled=false","route.engine.enabled=false","route.engine.lease-seconds=2"})
class KubernetesAcceptance {
 @Autowired ObjectMapper json;@Autowired JdbcTemplate db;@Autowired RouteRegistry routes;@Autowired AdmissionService admission;@Autowired EngineService engine;
 KubernetesClient client;String ns;
 @BeforeEach void connect()throws Exception{
  var cfg=json.readTree(Files.readString(Path.of(Objects.requireNonNull(System.getenv("ROUTE_ADAPTER_CATALOG"))))).get("kubernetes");
  var k=Config.fromKubeconfig(cfg.path("context").asText(),Path.of(cfg.path("kubeconfig").asText()).toFile());k.setRequestRetryBackoffLimit(0);client=new KubernetesClientBuilder().withConfig(k).build();
  ns=Objects.requireNonNull(System.getenv("ROUTE_ADAPTER_NAMESPACE"));
 }
 @AfterEach void close(){client.close();}
 JsonNode waitTaskMarker(String operation)throws Exception{
  var pods=client.pods().inNamespace(ns).withLabel("route-engine.operation",operation).list().getItems();
  for(var pod:pods){
   if(pod.getStatus()==null||!"Running".equals(pod.getStatus().getPhase()))continue;
   assertEquals(Boolean.FALSE,pod.getSpec().getAutomountServiceAccountToken());
   assertEquals(Boolean.TRUE,pod.getSpec().getSecurityContext().getRunAsNonRoot());
   var security=pod.getSpec().getContainers().getFirst().getSecurityContext();
   assertEquals(Boolean.TRUE,security.getReadOnlyRootFilesystem());assertEquals(Boolean.FALSE,security.getAllowPrivilegeEscalation());assertEquals(List.of("ALL"),security.getCapabilities().getDrop());
   var command=List.of("kubectl","--context",Objects.requireNonNull(System.getenv("ROUTE_CLUSTER")).replaceFirst("^","kind-"),"-n",ns,"exec",pod.getMetadata().getName(),"--","cat","/artifacts/"+operation+"/wait-started.json");
   var process=new ProcessBuilder(command).redirectErrorStream(true).start();
   assertTrue(process.waitFor(10,java.util.concurrent.TimeUnit.SECONDS),"Bounded marker read");
   String text=new String(process.getInputStream().readAllBytes(),java.nio.charset.StandardCharsets.UTF_8);
   if(process.exitValue()==0){var marker=json.readTree(text);assertEquals(operation,marker.path("operationId").asText());assertEquals("runner_on_start",marker.path("event").asText());assertEquals("Bounded synchronous wait",marker.path("task").asText());return marker;}
  }
  return null;
 }
 String state(String id){return db.queryForObject("SELECT CONCAT(state,':',permit_held) FROM executions WHERE id=?",String.class,id);}
 String start(String type,String ref)throws Exception{
  String route="demo-adapter-"+UUID.randomUUID().toString().substring(0,8);routes.create(route,"DEMO M4 kind","test","m4");
  var d=json.createObjectNode().put("routeId",route).put("version",1).put("dslVersion","1").put("engineSemanticsVersion","1").put("adapterContractVersion","1");
  d.putObject("root").put("id","root").put("type","SEQUENCE").putArray("children").addObject().put("id","work").put("type",type).put(type.equals("ANSIBLE")?"playbookRef":"resourceRef",ref);
  routes.draft(route,d,"test","m4");routes.publish(route,1,0,"test","m4");
  var result=admission.submit("test",UUID.randomUUID().toString(),new AdmissionService.Request(route,1,"CRITICAL","NOW_OR_REJECT",json.createObjectNode()),"m4");
  assertEquals(202,result.status());assertEquals("ADMITTED",result.body().path("decision").asText());return result.body().path("executionId").asText();
 }
 void waitState(String id,String target,int seconds)throws Exception{long end=System.nanoTime()+Duration.ofSeconds(seconds).toNanos();while(System.nanoTime()<end){engine.tick(id);if(state(id).equals(target))return;Thread.sleep(150);}assertEquals(target,state(id));}
 String op(String id){return db.queryForObject("SELECT a.operation_id FROM step_attempts a JOIN step_runs s ON s.id=a.step_run_id WHERE s.execution_id=?",String.class,id);}
 void evidence(String name,Object value)throws Exception{Files.writeString(Path.of(Objects.requireNonNull(System.getenv("ROUTE_ADAPTER_EVIDENCE"))).resolve(name+".json"),json.writerWithDefaultPrettyPrinter().writeValueAsString(value));}
 @Test void AC035_realDeploymentCompletesExactUidGenerationAndActual409()throws Exception{
  String id=start("KUBERNETES","deployment");var w=engine.claim(id);
  assertEquals("re-"+w.request().operationId(),w.request().context().path("name").asText());
  assertNull(client.apps().deployments().inNamespace(ns).withName("re-"+w.request().operationId()).get());
  assertTrue(engine.execute(w));assertTrue(state(id).endsWith(":1"));waitState(id,"SUCCEEDED:0",90);
  var deployment=client.apps().deployments().inNamespace(ns).withName("re-"+op(id)).get();assertNotNull(deployment);
  assertEquals(1L,deployment.getMetadata().getGeneration());assertEquals(deployment.getMetadata().getGeneration(),deployment.getStatus().getObservedGeneration());
  assertEquals(deployment.getMetadata().getUid(),db.queryForObject("SELECT external_uid FROM step_attempts WHERE id=?",String.class,w.attemptId()));
  assertTrue(deployment.getMetadata().getOwnerReferences()==null||deployment.getMetadata().getOwnerReferences().isEmpty());
  var duplicate=new io.fabric8.kubernetes.api.model.apps.DeploymentBuilder(deployment).editMetadata().withResourceVersion(null).withUid(null).endMetadata().build();
  var conflict=assertThrows(KubernetesClientException.class,()->client.apps().deployments().inNamespace(ns).resource(duplicate).create());assertEquals(409,conflict.getCode());
  evidence("deployment-uid-generation-conflict",Map.of("execution",id,"uid",deployment.getMetadata().getUid(),"generation",deployment.getMetadata().getGeneration(),"actualConflict",conflict.getCode(),"state",state(id)));
 }
 @Test void AC035_failedRolloutStopsWorkBeforeManualRelease()throws Exception{
  String id=start("KUBERNETES","deployment-fail");engine.tick(id);assertTrue(state(id).endsWith(":1"));waitState(id,"MANUAL_WAIT:0",120);
  String op=op(id);assertNull(client.apps().deployments().inNamespace(ns).withName("re-"+op).get());assertTrue(client.pods().inNamespace(ns).withLabel("route-engine.operation",op).list().getItems().isEmpty());
  assertEquals("FAILED",db.queryForObject("SELECT reason FROM adapter_stops WHERE operation_id=?",String.class,op));
  evidence("failed-rollout-stopped",Map.of("execution",id,"operation",op,"state",state(id),"pods",0));
 }
 @Test void AC036_jobReclaimObservesStableIdentityAndGcMissingNeverRecreates()throws Exception{
  String id=start("KUBERNETES","job");var first=engine.claim(id);assertTrue(engine.execute(first));String op=op(id);var job=client.batch().v1().jobs().inNamespace(ns).withName("re-"+op).get();assertNotNull(job);
  assertEquals(0,job.getSpec().getBackoffLimit());assertTrue(job.getMetadata().getOwnerReferences()==null||job.getMetadata().getOwnerReferences().isEmpty());String uid=job.getMetadata().getUid();
  Thread.sleep(1100);var reclaimed=engine.claim(id);assertNotNull(reclaimed);assertTrue(reclaimed.observe());assertEquals(first.request().operationId(),reclaimed.request().operationId());assertEquals(uid,reclaimed.request().externalUid());assertTrue(engine.execute(reclaimed));
  client.batch().v1().jobs().inNamespace(ns).withName("re-"+op).delete();
  long until=System.nanoTime()+Duration.ofSeconds(30).toNanos();while(client.batch().v1().jobs().inNamespace(ns).withName("re-"+op).get()!=null&&System.nanoTime()<until)Thread.sleep(100);
  Thread.sleep(1100);engine.tick(id);assertEquals("RECONCILING:1",state(id));assertNull(client.batch().v1().jobs().inNamespace(ns).withName("re-"+op).get());assertEquals(1,db.queryForObject("SELECT COUNT(*) FROM engine_incidents WHERE execution_id=? AND kind='IN_DOUBT'",Integer.class,id));
  evidence("job-missing-retained",Map.of("execution",id,"operation",op,"uid",uid,"state",state(id)));
 }
 @Test void AC037_AC041_realRunnerJobCompletesAndPersistsArtifactReference()throws Exception{
  String id=start("ANSIBLE","runner");engine.tick(id);waitState(id,"SUCCEEDED:0",120);String operation=op(id);
  var job=client.batch().v1().jobs().inNamespace(ns).withName("re-"+operation).get();assertNotNull(job);assertEquals(1,job.getStatus().getSucceeded());
  var output=json.readTree(db.queryForObject("SELECT output_json FROM step_runs WHERE execution_id=? AND node_id='work'",String.class,id));
  assertEquals("artifacts",output.path("artifacts").path("pvc").asText());assertEquals(operation,output.path("artifacts").path("path").asText());
  evidence("runner-artifact-reference",Map.of("execution",id,"operation",operation,"uid",job.getMetadata().getUid(),"output",output));
 }
 @Test void AC038_runningRunnerCancelHoldsSamePermitUntilPodsAreGone()throws Exception{
  String id=start("ANSIBLE","runner-wait");engine.tick(id);String operation=op(id);long generation=db.queryForObject("SELECT permit_generation FROM executions WHERE id=?",Long.class,id);
  long end=System.nanoTime()+Duration.ofSeconds(60).toNanos();
  while(client.pods().inNamespace(ns).withLabel("route-engine.operation",operation).list().getItems().stream().noneMatch(p->p.getStatus()!=null&&"Running".equals(p.getStatus().getPhase()))&&System.nanoTime()<end)Thread.sleep(100);
  assertTrue(client.pods().inNamespace(ns).withLabel("route-engine.operation",operation).list().getItems().stream().anyMatch(p->p.getStatus()!=null&&"Running".equals(p.getStatus().getPhase())));
  JsonNode marker=null;
  while(marker==null&&System.nanoTime()<end){marker=waitTaskMarker(operation);if(marker==null)Thread.sleep(100);}
  assertNotNull(marker,"Ansible must really enter the synchronous wait task before cancellation");
  evidence("runner-cancel-task-started",marker);
  engine.requestCancel(id,"test-operator","M4 bounded cancellation fixture");assertEquals("CANCELING:1",state(id));assertEquals(generation,db.queryForObject("SELECT permit_generation FROM executions WHERE id=?",Long.class,id));
  Thread.sleep(1100);engine.tick(id);assertEquals("CANCELING:1",state(id));
  waitState(id,"CANCELLED:0",90);assertTrue(client.pods().inNamespace(ns).withLabel("route-engine.operation",operation).list().getItems().isEmpty());assertNull(client.batch().v1().jobs().inNamespace(ns).withName("re-"+operation).get());
  evidence("runner-cancel-converged",Map.of("execution",id,"operation",operation,"permitGeneration",generation,"state",state(id)));
 }
}
