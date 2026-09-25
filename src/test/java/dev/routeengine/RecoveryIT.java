package dev.routeengine;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import dev.routeengine.admission.AdmissionService;
import dev.routeengine.registry.RouteRegistry;
import dev.routeengine.engine.*;
import dev.routeengine.recovery.*;
import dev.routeengine.api.ApiProblem;
import org.junit.jupiter.api.*;
import org.junit.jupiter.params.*;
import org.junit.jupiter.params.provider.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties={"route.scheduler.enabled=false","route.engine.enabled=false","route.engine.development=true","route.engine.fixture-directory=target/recovery-fixture"})
@org.springframework.test.context.ActiveProfiles("engine-development")
class RecoveryIT {
 @org.springframework.test.context.DynamicPropertySource
 static void database(org.springframework.test.context.DynamicPropertyRegistry p){
  for(String key:List.of("URL","USER","PASSWORD"))p.add("spring.datasource."+switch(key){case "URL"->"url";case "USER"->"username";default->"password";},()->Objects.requireNonNull(System.getenv("ROUTE_ENGINE_TEST_DB_"+key)));
 }
 @Autowired ObjectMapper json;@Autowired JdbcTemplate db;@Autowired RouteRegistry routes;@Autowired AdmissionService admission;
 @Autowired EngineService engine;@Autowired OperatorService operator;
 final List<String> owned=new ArrayList<>();
 JsonNode parse(String s)throws Exception{return json.readTree(s);}
 long n(String q,Object... args){return db.queryForObject(q,Long.class,args);}
 String state(String id){return db.queryForObject("SELECT state FROM executions WHERE id=?",String.class,id);}
 String leaf(String id,String ref){return "{\"id\":\""+id+"\",\"type\":\"REST\",\"endpointRef\":\""+ref+"\",\"input\":{\"value\":\""+id+"\"}}";}
 String start(String children,String priority,String mode)throws Exception{
  String route="demo-recovery-"+UUID.randomUUID().toString().substring(0,8);
  routes.create(route,"DEMO recovery","test","test");
  var definition=parse("{\"routeId\":\""+route+"\",\"version\":1,\"dslVersion\":\"1\",\"engineSemanticsVersion\":\"1\",\"adapterContractVersion\":\"1\",\"root\":{\"id\":\"root\",\"type\":\"SEQUENCE\",\"children\":"+children+"}}");
  routes.draft(route,definition,"test","test");routes.publish(route,1,0,"test","test");
  var result=admission.submit("test",UUID.randomUUID().toString(),new AdmissionService.Request(route,1,priority,mode,json.createObjectNode()),"test");
  assertEquals(202,result.status());String id=result.body().path("executionId").asText();owned.add(id);return id;
 }
 String manual(String ref,boolean rollback)throws Exception{
  var node=(ObjectNode)parse(leaf("bad",ref));if(rollback)node.set("rollback",parse(leaf("undo","dev.success")));
  String id=start("["+node+"]","HIGH","NOW_OR_REJECT");engine.tick(id);assertEquals("MANUAL_WAIT",state(id));return id;
 }
 JsonNode incident(String id){var all=operator.incidents(id).path("incidents");assertEquals(1,all.size(),all.toString());return all.get(0);}
 RecoveryPolicy.Request q(String id,String action,String mode,JsonNode replacement){var i=incident(id);return new RecoveryPolicy.Request(i.path("incidentId").asText(),i.path("stepId").asText(),action,mode,"verified operator decision",replacement);}
 AdmissionService.Result recover(String id,RecoveryPolicy.Request q,String key){return admission.recover(id,"operator",key,q,"test");}
 void config(int total,boolean enabled){long v=admission.capacity().path("configVersion").asLong();admission.configure(new AdmissionService.Config(total,0,6,3,1,enabled,v,"recovery fixture"),"operator","test");}
 @AfterEach void cleanup(){
  for(String id:owned){
   String state=state(id);
   if(Set.of("QUEUED","RECOVERY_QUEUED").contains(state))operator.cancel(id,"operator",UUID.randomUUID().toString(),new OperatorService.Cancel("test fixture withdrawal"),"test");
   if(n("SELECT permit_held FROM executions WHERE id=?",id)==1){
    engine.requestCancel(id,"operator","test fixture stop");
    for(int k=0;k<20&&n("SELECT permit_held FROM executions WHERE id=?",id)==1;k++){
     var work=engine.claim(id);if(work!=null)engine.complete(work,new OperationAdapter.Outcome(OperationAdapter.Status.STOPPED,json.createObjectNode(),false,null));
    }
   }
  }
  config(100,true);
 }
 @ParameterizedTest @CsvSource({"RETRY,QUEUE","RETRY,NOW_OR_REJECT","SKIP,QUEUE","SKIP,NOW_OR_REJECT","ROLLBACK,QUEUE","ROLLBACK,NOW_OR_REJECT","CANCEL,QUEUE","CANCEL,NOW_OR_REJECT"})
 void AC042_AC043_allActionsModesRejectAtomicallyAndAcquireNewGeneration(String action,String mode)throws Exception{
  String id=manual("dev.flaky",true);var q=q(id,action,mode,null);var prior=db.queryForMap("SELECT * FROM executions WHERE id=?",id);
  config(1,true);String holder=start("["+leaf("hold","dev.success")+"]","CRITICAL","NOW_OR_REJECT");
  var stepBefore=db.queryForList("SELECT * FROM step_runs WHERE execution_id=? ORDER BY id",id);var incidentBefore=db.queryForList("SELECT * FROM engine_incidents WHERE execution_id=?",id);
  String key=UUID.randomUUID().toString();var first=recover(id,q,key);
  assertEquals(mode.equals("QUEUE")?202:409,first.status());
  if(mode.equals("NOW_OR_REJECT")){
   assertEquals("MANUAL_WAIT",state(id));assertEquals(stepBefore,db.queryForList("SELECT * FROM step_runs WHERE execution_id=? ORDER BY id",id));
   assertEquals(incidentBefore,db.queryForList("SELECT * FROM engine_incidents WHERE execution_id=?",id));assertEquals(prior,db.queryForMap("SELECT * FROM executions WHERE id=?",id));
  }else{assertEquals("RECOVERY_QUEUED",state(id));assertEquals(0,n("SELECT permit_held FROM executions WHERE id=?",id));}
  engine.tick(holder);assertEquals(first.body(),recover(id,q,key).body());
  if(mode.equals("QUEUE"))assertEquals(id,admission.tick());
  else {assertNull(admission.tick());assertEquals(202,recover(id,q,UUID.randomUUID().toString()).status());}
  assertEquals(2,n("SELECT permit_generation FROM executions WHERE id=?",id));assertEquals(1,n("SELECT permit_held FROM executions WHERE id=?",id));
  assertEquals(1,n("SELECT route_version FROM executions WHERE id=?",id));
  assertEquals("HIGH",db.queryForObject("SELECT priority FROM executions WHERE id=?",String.class,id));
  engine.tick(id);assertEquals(action.equals("ROLLBACK")?"MANUAL_WAIT":action.equals("CANCEL")?"CANCELLED":"SUCCEEDED",state(id));
  assertEquals(0,n("SELECT permit_held FROM executions WHERE id=?",id));
  assertThrows(ApiProblem.class,()->recover(id,q,UUID.randomUUID().toString()));
 }
 @Test void AC043_persistedOptionalPayloadRoundTripPreservesDecision()throws Exception{
  var request=new RecoveryPolicy.Request("incident","step","RETRY","QUEUE","reason",null);
  assertEquals(request,json.treeToValue(json.valueToTree(request),RecoveryPolicy.Request.class));
 }
 @Test void AC044_scopePrincipalReplayAndBodyConflictKeepOneDecision()throws Exception{
  String a=manual("dev.flaky",false),b=manual("dev.flaky",false);var qa=q(a,"RETRY","QUEUE",null);var qb=q(b,"RETRY","QUEUE",null);
  var first=recover(a,qa,"same");assertEquals(first.body(),recover(a,qa,"same").body());
  assertEquals(202,recover(b,qb,"same").status());
  assertThrows(ApiProblem.class,()->recover(a,new RecoveryPolicy.Request(qa.incidentId(),qa.stepId(),"CANCEL","QUEUE",qa.reason(),null),"same"));
  assertThrows(ApiProblem.class,()->admission.recover(a,"other","same",qa,"test"));
  assertEquals(1,n("SELECT COUNT(*) FROM admission_requests WHERE execution_id=? AND recovery_payload IS NOT NULL",a));
  assertEquals(a,admission.tick());engine.tick(a);assertEquals(first.body(),recover(a,qa,"same").body());
 }
 @Test void AC045_failedBranchRetryPreservesConditionChoiceSiblingOutputAndNextWork()throws Exception{
  String parallel="{\"id\":\"p\",\"type\":\"PARALLEL\",\"join\":\"ALL_SETTLED\",\"branches\":["+leaf("ok","dev.success")+","+leaf("bad","dev.flaky")+"]}";
  String choice="{\"id\":\"choice\",\"type\":\"CONDITION\",\"condition\":{\"field\":\"steps.producer.flag\",\"operator\":\"EQ\",\"value\":true},\"then\":"+parallel+",\"else\":"+leaf("never","dev.success")+"}";
  String producer="{\"id\":\"producer\",\"type\":\"REST\",\"endpointRef\":\"dev.success\",\"input\":{\"flag\":true},\"outputSchema\":{\"type\":\"object\",\"properties\":{\"flag\":{\"type\":\"boolean\"}},\"required\":[\"flag\"]}}";
  String id=start("["+producer+","+choice+","+leaf("later","dev.success")+"]","HIGH","NOW_OR_REJECT");
  for(int x=0;x<4;x++)engine.tick(id);assertEquals("MANUAL_WAIT",state(id));
  var stable=db.queryForList("SELECT * FROM step_runs WHERE execution_id=? AND node_id IN ('ok','producer') ORDER BY id",id);
  recover(id,q(id,"RETRY","NOW_OR_REJECT",null),"retry");
  for(int x=0;x<4;x++)engine.tick(id);
  assertEquals("SUCCEEDED",state(id));assertEquals(stable,db.queryForList("SELECT * FROM step_runs WHERE execution_id=? AND node_id IN ('ok','producer') ORDER BY id",id));
  assertEquals("then",db.queryForObject("SELECT branch_choice FROM step_runs WHERE execution_id=? AND node_id='choice'",String.class,id));
  assertEquals(0,n("SELECT COUNT(*) FROM step_runs WHERE execution_id=? AND node_id='never'",id));assertEquals(2,n("SELECT attempt_count FROM step_runs WHERE execution_id=? AND node_id='bad'",id));
 }
 @Test void AC045_skipRequiresTypedReplacementAndRetainsAudit()throws Exception{
  var node=(ObjectNode)parse(leaf("bad","dev.fail"));node.set("outputSchema",parse("{\"type\":\"object\",\"properties\":{\"value\":{\"type\":\"string\"}},\"required\":[\"value\"],\"additionalProperties\":false}"));
  var later=(ObjectNode)parse(leaf("later","dev.success"));later.set("input",parse("{\"copied\":{\"$ref\":\"steps.bad.value\"}}"));
  String id=start("["+node+","+later+"]","HIGH","NOW_OR_REJECT");engine.tick(id);
  for(var bad:List.of(json.createObjectNode(),parse("{\"value\":4}"),parse("{\"value\":\"x\",\"token\":\"forbidden\"}"))){
   assertThrows(ApiProblem.class,()->recover(id,q(id,"SKIP","NOW_OR_REJECT",bad),UUID.randomUUID().toString()));assertEquals("MANUAL_WAIT",state(id));
  }
  recover(id,q(id,"SKIP","NOW_OR_REJECT",parse("{\"value\":\"replacement\"}")),"skip");engine.tick(id);
  assertEquals("SUCCEEDED",state(id));assertEquals("replacement",parse(db.queryForObject("SELECT input_json FROM step_runs WHERE execution_id=? AND node_id='later'",String.class,id)).path("copied").asText());
  assertEquals(1,n("SELECT COUNT(*) FROM execution_events WHERE execution_id=? AND event_type='RECOVERY_ADMITTED' AND actor='operator' AND reason='verified operator decision'",id));
 }
 @Test void AC046_rollbackDefaultDenyAndOldSuccessfulTargetRejected()throws Exception{
  String id=manual("dev.fail",false);assertThrows(ApiProblem.class,()->recover(id,q(id,"ROLLBACK","NOW_OR_REJECT",null),"rollback"));
  String other=start("["+leaf("old","dev.success")+","+leaf("bad","dev.fail")+"]","HIGH","NOW_OR_REJECT");engine.tick(other);engine.tick(other);
  var i=incident(other);String old=db.queryForObject("SELECT id FROM step_runs WHERE execution_id=? AND node_id='old'",String.class,other);
  assertThrows(ApiProblem.class,()->recover(other,new RecoveryPolicy.Request(i.path("incidentId").asText(),old,"ROLLBACK","NOW_OR_REJECT","invalid old target",null),"old"));
 }
 @Test void AC047_failedCompensationHumanRetryUsesFreshBoundedBudgetAndNewManualIncident()throws Exception{
  var node=(ObjectNode)parse(leaf("bad","dev.fail"));node.set("rollback",parse(leaf("undo","dev.flaky")));
  String id=start("["+node+"]","HIGH","NOW_OR_REJECT");engine.tick(id);var original=incident(id);var rollback=q(id,"ROLLBACK","NOW_OR_REJECT",null);
  recover(id,rollback,"rollback");engine.tick(id);assertEquals("MANUAL_WAIT",state(id));var failure=incident(id);
  assertEquals("ROLLBACK",failure.path("direction").asText());assertNotEquals(original.path("incidentId"),failure.path("incidentId"));
  var retry=q(id,"RETRY","NOW_OR_REJECT",null);recover(id,retry,"retry");engine.tick(id);
  assertEquals("MANUAL_WAIT",state(id));assertEquals(3,n("SELECT permit_generation FROM executions WHERE id=?",id));
  assertEquals(1,n("SELECT attempt_count FROM step_runs WHERE execution_id=? AND node_id='bad'",id));assertEquals(2,n("SELECT attempt_count FROM step_runs WHERE execution_id=? AND node_id='undo'",id));
  assertEquals(3,n("SELECT COUNT(DISTINCT operation_id) FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE execution_id=?",id));
  var compensated=incident(id);assertEquals("COMPENSATED",compensated.path("kind").asText());assertEquals(parse("[\"CANCEL\"]"),compensated.path("actions"));
  assertThrows(ApiProblem.class,()->recover(id,q(id,"ROLLBACK","NOW_OR_REJECT",null),"again"));
  recover(id,q(id,"CANCEL","NOW_OR_REJECT",null),"cancel");engine.tick(id);assertEquals("CANCELLED",state(id));
 }
 @Test void AC048_withdrawInitialAndRecoveryQueuesWithoutNewPermit()throws Exception{
  String queued=start("["+leaf("bad","dev.fail")+"]","HIGH","QUEUE");
  operator.cancel(queued,"operator","withdraw",new OperatorService.Cancel("withdraw initial"),"test");assertEquals("CANCELLED",state(queued));assertEquals(0,n("SELECT permit_generation FROM executions WHERE id=?",queued));
  String id=manual("dev.fail",false);recover(id,q(id,"RETRY","QUEUE",null),"queue");
  operator.cancel(id,"operator","withdraw",new OperatorService.Cancel("withdraw recovery"),"test");assertEquals("MANUAL_WAIT",state(id));assertEquals(1,n("SELECT permit_generation FROM executions WHERE id=?",id));
  assertNull(admission.tick());assertEquals(1,operator.incidents(id).path("incidents").size());
 }
 @Test void AC049_confirmExactExistingUnknownOperationAndFenceObserver()throws Exception{
  String id=start("["+leaf("unknown","dev.unknown")+","+leaf("later","dev.success")+"]","HIGH","NOW_OR_REJECT");engine.tick(id);
  var i=incident(id);assertEquals("RECONCILING",state(id));long before=n("SELECT COUNT(*) FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE execution_id=?",id);
  assertThrows(ApiProblem.class,()->operator.resolve(id,i.path("incidentId").asText(),"operator","bad",new OperatorService.Resolve(i.path("stepId").asText(),"wrong","SUCCEEDED","checked","remote evidence",json.createObjectNode()),"test"));
  var body=new OperatorService.Resolve(i.path("stepId").asText(),i.path("operationId").asText(),"FAILED","checked","remote operation terminal failure",null);
  var result=operator.resolve(id,i.path("incidentId").asText(),"operator","resolve",body,"test");
  assertEquals("MANUAL_WAIT",state(id));assertEquals(before,n("SELECT COUNT(*) FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE execution_id=?",id));assertEquals(result,operator.resolve(id,i.path("incidentId").asText(),"operator","resolve",body,"test"));
  assertEquals(0,n("SELECT COUNT(*) FROM step_runs WHERE execution_id=? AND node_id='later'",id));assertEquals("KNOWN_FAILURE",incident(id).path("kind").asText());
 }
 @Test void AC050_oldReleaseAndCallbackCannotAffectSecondGeneration()throws Exception{
  String id=start("["+leaf("bad","dev.flaky")+"]","HIGH","NOW_OR_REJECT");var first=engine.claim(id);assertNotNull(first);
  engine.execute(first);assertEquals("MANUAL_WAIT",state(id));long version=n("SELECT state_version FROM executions WHERE id=?",id);
  recover(id,q(id,"RETRY","NOW_OR_REJECT",null),"retry");var second=engine.claim(id);assertNotNull(second);
  assertEquals("STALE",admission.stop(id,first.permitGeneration(),version,"MANUAL_WAIT","test","old release","test"));
  assertFalse(engine.complete(first,new OperationAdapter.Outcome(OperationAdapter.Status.SUCCEEDED,json.createObjectNode(),false,null)));
  assertEquals(1,n("SELECT permit_held FROM executions WHERE id=?",id));assertEquals(2,second.permitGeneration());
  assertNotEquals(first.request().operationId(),second.request().operationId());assertTrue(engine.execute(second));assertEquals("SUCCEEDED",state(id));
 }
 @Test void AC043_mixedInitialRecoverySharePersistentWrrFifoAndCriticalPriority()throws Exception{
  var recoveries=new LinkedHashMap<String,List<String>>();
  for(String priority:List.of("HIGH","NORMAL","LOW")){
   var ids=new ArrayList<String>();
   for(int x=0;x<6;x++){String id=start("["+leaf("bad","dev.flaky")+"]",priority,"NOW_OR_REJECT");engine.tick(id);ids.add(id);}
   recoveries.put(priority,ids);
  }
  config(1,false);var fifo=new LinkedHashMap<String,Deque<String>>();
  for(String priority:recoveries.keySet()){
   var expected=new ArrayDeque<String>();fifo.put(priority,expected);
   for(String id:recoveries.get(priority)){
    String initial=start("["+leaf("initial","dev.success")+"]",priority,"QUEUE");expected.add(initial);
    recover(id,q(id,"RETRY","QUEUE",null),UUID.randomUUID().toString());expected.add(id);
   }
  }
  String critical=start("["+leaf("critical","dev.success")+"]","CRITICAL","QUEUE");
  config(1,true);assertEquals(critical,admission.tick());engine.tick(critical);
  // Reset weights through a real configuration change, not an arbitrary cursor UPDATE.
  long v=admission.capacity().path("configVersion").asLong();
  admission.configure(new AdmissionService.Config(1,0,5,3,1,true,v,"reset fixture weights"),"test","test");
  config(1,true);var seen=new ArrayList<String>();
  for(int x=0;x<10;x++){
   String id=admission.tick();assertNotNull(id);
   String priority=db.queryForObject("SELECT priority FROM executions WHERE id=?",String.class,id);seen.add(priority);assertEquals(fifo.get(priority).removeFirst(),id);
   engine.tick(id);assertEquals("SUCCEEDED",state(id));
  }
  assertEquals(List.of("HIGH","HIGH","HIGH","HIGH","HIGH","HIGH","NORMAL","NORMAL","NORMAL","LOW"),seen);
 }
 @Test void AC043_staleQueuedIncidentIsWithdrawnBeforePermitOrStepMutation()throws Exception{
  String id=manual("dev.flaky",false);var request=q(id,"RETRY","QUEUE",null);var before=db.queryForList("SELECT * FROM step_runs WHERE execution_id=? ORDER BY id",id);
  var decision=recover(id,request,"queue");
  // Inject only a stale incident decision in this isolated fixture; never manipulate permit state.
  db.update("UPDATE engine_incidents SET status='RESOLVED' WHERE id=?",request.incidentId());
  assertNull(admission.tick());assertEquals("MANUAL_WAIT",state(id));assertEquals(1,n("SELECT permit_generation FROM executions WHERE id=?",id));
  assertEquals(before,db.queryForList("SELECT * FROM step_runs WHERE execution_id=? ORDER BY id",id));
  assertEquals("WITHDRAWN",db.queryForObject("SELECT decision FROM admission_requests WHERE id=?",String.class,decision.body().path("admissionRequestId").asText()));
 }
 @Test void AC045_multipleFailedBranchesRecoverIndividuallyWithoutReplayingSuccess()throws Exception{
  String id=start("[{\"id\":\"p\",\"type\":\"PARALLEL\",\"join\":\"ALL_SETTLED\",\"branches\":["+leaf("a","dev.flaky")+","+leaf("b","dev.flaky")+"]}]","HIGH","NOW_OR_REJECT");
  var first=engine.claim(id);var second=engine.claim(id);assertNotNull(first);assertNotNull(second);engine.execute(first);engine.execute(second);assertEquals("MANUAL_WAIT",state(id));
  var incidents=operator.incidents(id).path("incidents");assertEquals(2,incidents.size());
  for(var i:incidents){
   var request=new RecoveryPolicy.Request(i.path("incidentId").asText(),i.path("stepId").asText(),"RETRY","NOW_OR_REJECT","retry one failed branch",null);
   recover(id,request,UUID.randomUUID().toString());engine.tick(id);
  }
  assertEquals("SUCCEEDED",state(id));assertEquals(4,n("SELECT COUNT(*) FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE r.execution_id=?",id));
 }
 @Test void AC048_cancelAdmittedUndispatchedCompensationDoesNotSubmitIt()throws Exception{
  String id=manual("dev.fail",true);recover(id,q(id,"ROLLBACK","NOW_OR_REJECT",null),"rollback");
  operator.cancel(id,"operator","stop",new OperatorService.Cancel("stop before compensation submit"),"test");engine.tick(id);
  assertEquals("CANCELLED",state(id));assertEquals(0,n("SELECT COUNT(*) FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE r.execution_id=? AND a.direction='ROLLBACK'",id));
 }

 @Test void AC049_stoppedConfirmationAdvertisesLegalActionsAndSettlesUndispatchedBranches()throws Exception{
  String id=start("[{\"id\":\"p\",\"type\":\"PARALLEL\",\"join\":\"ALL_SETTLED\",\"branches\":["+leaf("a","dev.flaky")+","+leaf("b","dev.success")+"]},"+leaf("later","dev.success")+"]","HIGH","NOW_OR_REJECT");
  var work=engine.claim(id);assertNotNull(work);
  assertTrue(engine.complete(work,OperationAdapter.Outcome.unknown()));var unknown=incident(id);
  operator.resolve(id,unknown.path("incidentId").asText(),"operator","resolve",new OperatorService.Resolve(unknown.path("stepId").asText(),unknown.path("operationId").asText(),"STOPPED","checked","fixture confirms no running side effect",null),"test");
  assertEquals("MANUAL_WAIT",state(id));assertEquals(parse("[\"CANCEL\",\"RETRY\"]"),incident(id).path("actions"));
  assertEquals("STOPPED",db.queryForObject("SELECT state FROM step_runs WHERE execution_id=? AND node_id='b'",String.class,id));
  recover(id,q(id,"RETRY","NOW_OR_REJECT",null),"retry");
  for(int x=0;x<4;x++)engine.tick(id);
  assertEquals("SUCCEEDED",state(id));assertEquals(1,n("SELECT attempt_count FROM step_runs WHERE execution_id=? AND node_id='b'",id));
 }
 @Test void AC045_retryResumesNeverDispatchedSiblingAfterEarlyFailure()throws Exception{
  String id=start("[{\"id\":\"p\",\"type\":\"PARALLEL\",\"join\":\"ALL_SETTLED\",\"branches\":["+leaf("a","dev.flaky")+","+leaf("b","dev.success")+"]}]","HIGH","NOW_OR_REJECT");
  engine.tick(id);assertEquals("MANUAL_WAIT",state(id));assertEquals(0,n("SELECT attempt_count FROM step_runs WHERE execution_id=? AND node_id='b'",id));
  recover(id,q(id,"RETRY","NOW_OR_REJECT",null),"retry");for(int x=0;x<3;x++)engine.tick(id);
  assertEquals("SUCCEEDED",state(id));assertEquals(1,n("SELECT attempt_count FROM step_runs WHERE execution_id=? AND node_id='b'",id));
 }
 @Test void AC046_falseRollbackGuardRefusesSideEffectAndPreservesIncident()throws Exception{
  String producer="{\"id\":\"producer\",\"type\":\"REST\",\"endpointRef\":\"dev.success\",\"input\":{\"flag\":false},\"outputSchema\":{\"type\":\"object\",\"properties\":{\"flag\":{\"type\":\"boolean\"}},\"required\":[\"flag\"]}}";
  var bad=(ObjectNode)parse(leaf("bad","dev.fail"));var undo=(ObjectNode)parse(leaf("undo","dev.success"));
  undo.set("when",parse("{\"field\":\"steps.producer.flag\",\"operator\":\"EQ\",\"value\":true}"));bad.set("rollback",undo);
  String id=start("["+producer+","+bad+"]","HIGH","NOW_OR_REJECT");engine.tick(id);engine.tick(id);
  var before=operator.incidents(id);
  assertThrows(ApiProblem.class,()->recover(id,q(id,"ROLLBACK","NOW_OR_REJECT",null),"forbidden"));
  assertEquals(before,operator.incidents(id));assertEquals("MANUAL_WAIT",state(id));assertEquals(1,n("SELECT permit_generation FROM executions WHERE id=?",id));
  assertEquals(0,n("SELECT COUNT(*) FROM step_runs WHERE execution_id=? AND direction='ROLLBACK'",id));
 }

}
