"""Real adapter response-window SIGKILL and restart acceptance, separate from the Java suites."""
import json,time,traceback,pathlib,xml.etree.ElementTree as ET
from adapter_fixture import AdapterFixture
from engine_gate import leaf
from gate_common import fixed

def process_acceptance(base,image=None):
 base.mkdir(parents=True,exist_ok=False);f=AdapterFixture(base);suite=ET.Element('testsuite',name='AdapterProcesses');problem=None
 def case(name,fn):
  item=ET.SubElement(suite,'testcase',name=name,classname='AdapterProcesses')
  try:fn()
  except Exception:ET.SubElement(item,'failure').text=traceback.format_exc();raise
 try:
  f.start();f.setup_catalog(image)
  def rest_crash():
   a=f.start_adapter('rest-before-result',pause='work');id=f.execute(a,[leaf('work','sync')])
   f.wait(lambda:(f.external/('io-'+id+'.reached')).exists(),'real HTTP side effect before DB result')
   op=f.operation(id,'work');assert f.remote.effects[op]==1
   assert f.step(id,'work')=='RUNNING';assert f.status(id).endswith(':1')
   plan=f.sql("SELECT adapter_plan FROM step_attempts WHERE operation_id='"+op+"'");assert json.loads(plan)['catalogHash']
   record=f.crash([a],id,'real-http-side-effect-before-result-db')
   b=f.start_adapter('rest-after-kill');f.wait(lambda:f.status(id)=='SUCCEEDED:0','existing HTTP operation reconciled')
   assert f.operation(id,'work')==op and f.step(id,'work','attempt_count')=='1';assert f.remote.effects[op]==1
   assert sum(x['operation']==op for x in f.remote.submits)==1
   record.update(restarted_pid=b['process'].pid,after_restart=f.snapshot(id),operation=op,side_effects=1,submits=1);f.kill(b)
  case('AC033_realHttpSideEffectSigkillBeforeResultAndOriginalOperationReconciled',rest_crash)
  def unknown_crash():
   a=f.start_adapter('unsafe-before');id=f.execute(a,[leaf('work','unsafe'),leaf('never','sync')])
   f.wait(lambda:f.status(id)=='RECONCILING:1','unsafe response loss incident');op=f.operation(id,'work')
   before=int(f.step(id,'work','lease_generation'));record=f.crash([a],id,'non-dedupe-http-unknown')
   b=f.start_adapter('unsafe-after');f.wait(lambda:int(f.step(id,'work','lease_generation'))>=before+2,'unknown observed after restart')
   assert f.status(id)=='RECONCILING:1';assert f.step(id,'never')=='';assert f.step(id,'work','attempt_count')=='1'
   assert sum(x['operation']==op for x in f.remote.submits)==1 and f.remote.effects[op]==1
   assert f.sql("SELECT COUNT(*) FROM engine_incidents WHERE execution_id='"+id+"' AND kind='IN_DOUBT' AND status='OPEN'")=='1'
   record.update(restarted_pid=b['process'].pid,after_restart=f.snapshot(id),operation=op,side_effects=1,submits=1);f.kill(b)
  case('AC034_unknownWithoutDedupeOrQuerySurvivesSigkillWithoutResubmit',unknown_crash)
  if image is not None:
   def job_crash():
    a=f.start_adapter('job-before-result',pause='work');id=f.execute(a,[{'id':'work','type':'KUBERNETES','resourceRef':'job'}])
    f.wait(lambda:(f.external/('io-'+id+'.reached')).exists(),'real Job create before DB result')
    op=f.operation(id,'work');job=json.loads(f.kube('-n',f.namespace,'get','job','re-'+op,'-o','json'));uid=job['metadata']['uid']
    assert not job['metadata'].get('ownerReferences');assert job['spec']['backoffLimit']==0
    assert f.sql("SELECT COALESCE(external_uid,'NULL') FROM step_attempts WHERE operation_id='"+op+"'")=='NULL'
    plan=json.loads(f.sql("SELECT adapter_plan FROM step_attempts WHERE operation_id='"+op+"'"));assert plan['name']=='re-'+op and plan['namespace']==f.namespace
    record=f.crash([a],id,'real-job-created-before-result-db')
    after=json.loads(f.kube('-n',f.namespace,'get','job','re-'+op,'-o','json'));assert after['metadata']['uid']==uid
    b=f.start_adapter('job-after-kill')
    f.wait(lambda:f.sql("SELECT COALESCE(external_uid,'NULL') FROM step_attempts WHERE operation_id='"+op+"'")==uid,'same Job UID reconciled')
    current=json.loads(f.kube('-n',f.namespace,'get','jobs','-l','route-engine.operation='+op,'-o','json'));assert len(current['items'])==1 and current['items'][0]['metadata']['uid']==uid
    assert f.operation(id,'work')==op and f.step(id,'work','attempt_count')=='1' and f.status(id).endswith(':1')
    record.update(restarted_pid=b['process'].pid,after_restart=f.snapshot(id),operation=op,job_uid=uid,job_count=1);f.kill(b)
   case('AC036_realJobCreatedThenSigkillKeepsSameUidAndNeverUsesAppPodOwner',job_crash)
 except Exception as error:
  problem=error;(base/'failure.log').write_text(traceback.format_exc())
 finally:
  try:f.cleanup()
  except Exception as error:problem=problem or error;(base/'cleanup-failure.log').write_text(traceback.format_exc())
  (base/'junit').mkdir(exist_ok=True);ET.ElementTree(suite).write(base/'junit/TEST-AdapterProcesses.xml',encoding='utf-8',xml_declaration=True)
 if problem:raise problem
 return fixed.junit_counts(base/'junit/TEST-AdapterProcesses.xml')
