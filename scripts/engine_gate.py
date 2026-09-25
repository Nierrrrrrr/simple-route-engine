#!/usr/bin/env python3
"""M3 controlled development adapter and real MariaDB/JVM crash acceptance, not M4 integration."""
import json,os,sys,pathlib,subprocess,socket,time,traceback,urllib.error,uuid
import xml.etree.ElementTree as ET
from admission_gate import AdmissionFixture
from crash_boundary import snapshot as consistent_snapshot,crash as stopped_crash,validate_crash_boundary
from gate_common import ROOT,fixed,evidence_path

class EngineFixture(AdmissionFixture):
 def __init__(self,base):
  super().__init__(base);self.external=base/'external-fixture';self.external.mkdir();self.crashes=[]
 def start_engine(self,label,pause=''):
  with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
  stream=(self.base/('jvm-'+label+'.log')).open('w')
  env=dict(self.env,ROUTE_PORT=str(port),ROUTE_SCHEDULER_ENABLED='false',ROUTE_ENGINE_ENABLED='true',SPRING_PROFILES_ACTIVE='engine-development',ROUTE_ENGINE_FIXTURE_DIRECTORY=str(self.external),ROUTE_ENGINE_LEASE_SECONDS='2',ROUTE_ENGINE_WORKERS='2',ROUTE_ENGINE_QUEUE_SIZE='3',ROUTE_ENGINE_PAUSE_AFTER_NODE=pause)
  args=['bash','scripts/local-run.sh']
  (self.base/('jvm-'+label+'.command.json')).write_text(json.dumps(args)+'\n')
  process=subprocess.Popen(args,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
  app={'label':label,'port':port,'process':process,'stream':stream};self.apps.append(app)
  self.process_proofs.append({'label':label,'pid':process.pid,'engine_enabled':True,'development_adapter':True,'worker_max':2,'queue_capacity':3,'database':self.database_endpoints[-1]})
  deadline=time.monotonic()+90
  while time.monotonic()<deadline:
   assert process.poll() is None,'Engine JVM exited '+label
   try:
    if self.api(app,'GET','/actuator/health')[0]==200:return app
   except (OSError,urllib.error.URLError):pass
   time.sleep(.25)
  raise AssertionError('Engine readiness timeout '+label)
 def wait(self,predicate,description,seconds=60):
  deadline=time.monotonic()+seconds
  while time.monotonic()<deadline:
   value=predicate()
   if value:return value
   time.sleep(.1)
  raise AssertionError('Timed out: '+description)
 def publish(self,app,children):
  route='demo-engine-'+uuid.uuid4().hex[:10]
  self.api(app,'POST','/routes',{'routeId':route,'name':'DEMO M3 process fixture'},expected=201)
  d={'routeId':route,'version':1,'dslVersion':'1','engineSemanticsVersion':'1','adapterContractVersion':'1','root':{'id':'root','type':'SEQUENCE','children':children}}
  self.api(app,'POST','/routes/'+route+'/versions',{'definition':d},expected=201)
  self.api(app,'POST','/routes/'+route+'/versions/1/publish',{'stateVersion':0},expected=200)
  return route
 def execute(self,app,children):
  route=self.publish(app,children)
  return self.api(app,'POST','/executions',{'routeId':route,'priority':'CRITICAL','admissionMode':'NOW_OR_REJECT','input':{}},str(uuid.uuid4()),202)[1]['executionId']
 def status(self,id):return self.sql("SELECT CONCAT(state,':',permit_held) FROM executions WHERE id='"+id+"'")
 def step(self,id,node,column='state'):
  assert column in ('state','input_json','output_json','branch_choice','lease_generation','attempt_count')
  return self.sql("SELECT "+column+" FROM step_runs WHERE execution_id='"+id+"' AND node_id='"+node+"'")
 def operation(self,id,node):
  return self.sql("SELECT a.operation_id FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE r.execution_id='"+id+"' AND r.node_id='"+node+"' ORDER BY attempt_number DESC LIMIT 1")
 def respond(self,operation,output):
  (self.external/(operation+'.result.json')).write_text(json.dumps({'status':'SUCCEEDED','output':output})+'\n')
 def snapshot(self,id):return consistent_snapshot(self,id)
 def crash(self,apps,id,window):return stopped_crash(self,apps,id,window)
 def cleanup(self):
  (self.base/'crash-proof.json').write_text(json.dumps(self.crashes,indent=2)+'\n')
  super().cleanup()

def leaf(id,ref='dev.success',**extra):
 return {'id':id,'type':'REST','endpointRef':ref,'input':{'value':id},**extra}

def process_acceptance(base):
 base.mkdir(parents=True,exist_ok=False);f=EngineFixture(base);suite=ET.Element('testsuite',name='EngineProcesses');problem=None
 def case(name,fn):
  c=ET.SubElement(suite,'testcase',classname='EngineProcesses',name=name)
  try:fn()
  except Exception:ET.SubElement(c,'failure').text=traceback.format_exc();raise
 try:
  f.start()
  def atomic():
   a=f.start_engine('commit-window',pause='first')
   id=f.execute(a,[leaf('first'),leaf('second')])
   f.wait(lambda:(f.external/('pause-'+id+'.reached')).exists(),'result transaction committed')
   assert f.step(id,'first')=='SUCCEEDED';assert f.step(id,'second')=='PENDING';assert f.operation(id,'second')==''
   record=f.crash([a],id,'result-and-next-pending-committed-before-next-dispatch')
   b=f.start_engine('commit-restart')
   f.wait(lambda:f.status(id)=='SUCCEEDED:0','sequence restart success')
   assert f.step(id,'first','attempt_count')=='1';assert f.step(id,'second','attempt_count')=='1'
   assert f.sql("SELECT COUNT(*) FROM step_runs WHERE execution_id='"+id+"'")=='3'
   record.update(restarted_pid=b['process'].pid,after_restart=f.snapshot(id));f.kill(b)
  case('AC023_resultAndNextPendingCommitThenSigkillRestart',atomic)
  def choice():
   a=f.start_engine('choice-window',pause='produce')
   source=leaf('produce','dev.pending',outputSchema={'type':'object','properties':{'flag':{'type':'boolean'}},'required':['flag']})
   branch={'id':'choice','type':'CONDITION','condition':{'field':'steps.produce.flag','operator':'EQ','value':True},'then':leaf('selected'),'else':leaf('unselected')}
   id=f.execute(a,[source,branch])
   f.wait(lambda:f.step(id,'produce')=='WAITING_EXTERNAL','producer waiting')
   operation=f.operation(id,'produce');f.respond(operation,{'flag':True})
   f.wait(lambda:(f.external/('pause-'+id+'.reached')).exists(),'choice committed')
   assert f.step(id,'choice','branch_choice')=='then';assert f.step(id,'selected')=='PENDING'
   record=f.crash([a],id,'condition-choice-and-resolved-output-committed')
   f.respond(operation,{'flag':False})
   b=f.start_engine('choice-restart');f.wait(lambda:f.status(id)=='SUCCEEDED:0','condition restart')
   assert f.step(id,'choice','branch_choice')=='then';assert f.step(id,'unselected')==''
   assert json.loads(f.step(id,'produce','output_json'))=={'flag':True};assert f.step(id,'produce','attempt_count')=='1'
   record.update(restarted_pid=b['process'].pid,external_result_changed=True,after_restart=f.snapshot(id));f.kill(b)
  case('AC024_externalDataChangesAfterPersistedChoiceDoNotReselect',choice)
  def branches():
   a=f.start_engine('branches-a');b=f.start_engine('branches-b')
   parallel={'id':'parallel','type':'PARALLEL','join':'ALL_SETTLED','branches':[leaf('slow','dev.pending'),leaf('success')]}
   id=f.execute(a,[parallel,leaf('after')])
   f.wait(lambda:f.step(id,'slow')=='WAITING_EXTERNAL' and f.step(id,'success')=='SUCCEEDED','one branch still active, sibling settled')
   op=f.operation(id,'slow');assert f.status(id).endswith(':1')
   record=f.crash([a,b],id,'parallel-branch-still-external-and-sibling-succeeded')
   assert f.status(id).endswith(':1');f.respond(op,{'branch':'slow'})
   c=f.start_engine('branches-restart');f.wait(lambda:f.status(id)=='SUCCEEDED:0','parallel restart')
   assert f.operation(id,'slow')==op;assert f.step(id,'slow','attempt_count')=='1';assert f.step(id,'success','attempt_count')=='1'
   assert int(f.step(id,'slow','lease_generation'))>=2
   result=json.loads(f.step(id,'parallel','output_json'));assert result=={'slow':{'branch':'slow'},'success':{'value':'success'}}
   assert len(list(f.external.glob(op+'.operation.json')))==1
   record.update(restarted_pid=c['process'].pid,after_restart=f.snapshot(id));f.kill(c)
  case('AC025_AC028_twoJvmParallelBranchCrashReconcilesSameIdentity',branches)
  def retry():
   a=f.start_engine('retry-before')
   id=f.execute(a,[leaf('retry','dev.flaky',retry={'maxAttempts':2,'maxElapsedSeconds':120,'backoffSeconds':40})])
   f.wait(lambda:f.status(id)=='RETRY_WAIT:1','retry wait')
   query="SELECT CONCAT(attempt_count,':',max_attempts,':',max_elapsed_seconds,':',backoff_seconds,':',next_action_at) FROM step_runs WHERE execution_id='"+id+"' AND node_id='retry'"
   persisted=f.sql(query);assert persisted.startswith('1:2:120:40:')
   record=f.crash([a],id,'durable-retry-wait-with-permit')
   b=f.start_engine('retry-after')
   # If startup is faster than backoff, the unchanged timestamp must still prevent early attempt2.
   due=f.sql("SELECT next_action_at>UTC_TIMESTAMP(6) FROM step_runs WHERE execution_id='"+id+"' AND node_id='retry'")
   if due=='1':assert f.sql(query)==persisted;assert f.status(id)=='RETRY_WAIT:1'
   f.wait(lambda:f.status(id)=='SUCCEEDED:0','wall-clock retry due',90)
   assert f.step(id,'retry','attempt_count')=='2'
   ops=f.sql("SELECT GROUP_CONCAT(a.operation_id ORDER BY attempt_number) FROM step_attempts a JOIN step_runs r ON r.id=a.step_run_id WHERE r.execution_id='"+id+"'").split(',')
   assert len(ops)==2 and len(set(ops))==2
   record.update(restarted_pid=b['process'].pid,persisted_before=persisted,after_restart=f.snapshot(id),real_wall_clock=True);f.kill(b)
  case('AC026_shortWallClockRetryPersistsAcrossKilledJvm',retry)
  def unknown():
   a=f.start_engine('unknown-before')
   id=f.execute(a,[leaf('unknown','dev.unknown'),leaf('unsafe')])
   f.wait(lambda:f.status(id)=='RECONCILING:1','unknown observed')
   op=f.operation(id,'unknown');record=f.crash([a],id,'unknown-operation-holds-permit')
   b=f.start_engine('unknown-after')
   f.wait(lambda:int(f.step(id,'unknown','lease_generation'))>=2,'unknown reconciled')
   assert f.status(id)=='RECONCILING:1';assert f.step(id,'unsafe')=='';assert f.step(id,'unknown','attempt_count')=='1';assert f.operation(id,'unknown')==op
   assert len(list(f.external.glob(op+'.operation.json')))==1
   record.update(restarted_pid=b['process'].pid,after_restart=f.snapshot(id));f.kill(b)
  case('AC030_unknownAfterRestartNeverResubmitsOrReleases',unknown)
  def isolation():
   a=f.start_engine('exception-isolation')
   bad=f.execute(a,[leaf('throws','dev.throw')]);good=f.execute(a,[leaf('ok')])
   f.wait(lambda:f.status(good)=='SUCCEEDED:0','other execution continues')
   f.wait(lambda:f.status(bad)=='RECONCILING:1','throw safely unknown')
   assert f.step(bad,'throws','attempt_count')=='1'
   (base/'exception-isolation.json').write_text(json.dumps({'bad':f.snapshot(bad),'good':f.snapshot(good),'same_pid':a['process'].pid,'bounded_workers':2,'queue_capacity':3},indent=2)+'\n');f.kill(a)
  case('AC029_exceptionIsolationWithBoundedExecutor',isolation)
 except Exception as e:problem=e;(base/'failure.log').write_text(traceback.format_exc())
 finally:
  try:f.cleanup()
  except Exception as e:problem=problem or e;(base/'cleanup-failure.log').write_text(traceback.format_exc())
  (base/'junit').mkdir(exist_ok=True);ET.ElementTree(suite).write(base/'junit/TEST-EngineProcesses.xml',encoding='utf-8',xml_declaration=True)
 if problem:raise problem
 return fixed.junit_counts(base/'junit/TEST-EngineProcesses.xml')

def validate_m3_reports(base):
 reports=[base/'m2/m1/junit/TEST-dev.routeengine.EngineIT.xml',base/'m2/m1/junit/TEST-dev.routeengine.registry.EngineDslTest.xml',base/'processes/junit/TEST-EngineProcesses.xml'];names=[]
 for p in reports:
  counts=fixed.junit_counts(p);assert counts['tests']>0 and not any(counts[k] for k in ('failures','errors','skipped')),str(p)
  names.extend(c.attrib.get('name','') for c in ET.parse(p).getroot().iter('testcase'))
 for n in range(23,32):assert any(('AC%03d_'%n) in name for name in names),'Missing actual M3 testcase AC-%03d'%n
 proofs=json.loads((base/'processes/crash-proof.json').read_text())
 for proof in proofs:validate_crash_boundary(proof)
 for window in ['result-and-next-pending-committed-before-next-dispatch','parallel-branch-still-external-and-sibling-succeeded','durable-retry-wait-with-permit']:
  matching=[p for p in proofs if p['window']==window];assert len(matching)==1
  p=matching[0];assert p['killed_pids'] and all(x==-9 for x in p['exit_codes']) and p['restarted_pid'] not in p['killed_pids'] and p['after_restart']
 assert any(len(p['killed_pids'])==2 for p in proofs),'No two independent engine JVMs'

def main():
 base=evidence_path(ROOT,sys.argv[1]);base.mkdir(parents=True,exist_ok=True)
 rc=subprocess.run(['bash','scripts/verify-phase.sh','M2',str(base/'m2')],cwd=ROOT).returncode
 if rc:return rc
 old=fixed.load_json(base/'m2/summary.json')
 result={'phase':'M3','source_fingerprint':os.environ['ROUTE_SOURCE_FINGERPRINT'],'production_authorized':False,
  'checks':[{**c,'evidence':'m2/'+c['evidence']} for c in old['checks']],'suites':[{**s,'report':'m2/'+s['report']} for s in old['suites']]}
 try:
  counts=process_acceptance(base/'processes');validate_m3_reports(base)
  result['suites'].append({'name':'EngineProcesses',**counts,'report':'processes/junit/TEST-EngineProcesses.xml'})
  for n in range(23,32):
   name='AC-%03d'%n;(base/(name+'.log')).write_text('Actual clean EngineIT/EngineDslTest and real EngineProcesses passed. Inspect m2/m1/junit, processes/junit, crash-proof.json, external-fixture, HTTP responses and raw command/exit logs. Development adapter only; no M4 production integration or six-hour soak claim.\n')
   result['checks'].append({'id':name,'status':'PASS','evidence':name+'.log'})
 except Exception:
  (base/'failure.log').write_text(traceback.format_exc())
  for n in range(23,32):result['checks'].append({'id':'AC-%03d'%n,'status':'FAIL','evidence':'failure.log'})
 fixed.atomic_json(base/'summary.json',result)
 try:fixed.validate_gate(result,base,fixed.load_json(ROOT/'ai-kit/requirements.json'),'M3',os.environ['ROUTE_SOURCE_FINGERPRINT'])
 except Exception as e:print('M3 FAILED:',e);return 1
 print('M3 cumulative executable gate passed; fresh review pending');return 0
if __name__=='__main__':sys.exit(main())