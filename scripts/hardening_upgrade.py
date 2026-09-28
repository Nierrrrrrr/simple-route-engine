"""Replayable M5-to-M6 upgrade: an actual pinned old runtime writes every fixture state."""
import hashlib,json,os,pathlib,traceback,uuid,xml.etree.ElementTree as ET
from gate_common import ROOT
from hardening_processes import HardeningFixture

def baseline_jar():
 spec=json.loads((ROOT/'config/upgrade/m5-fixture.json').read_text())
 default=ROOT/'.evidence/desktop'/os.environ['ROUTE_RUN_ID']/'baseline/m5-runtime/route-engine-0.1.0.jar'
 jar=pathlib.Path(os.environ.get('ROUTE_M5_BASELINE_JAR',str(default))).resolve()
 if not jar.is_file():
  assert 'ROUTE_M5_BASELINE_JAR' not in os.environ,'Explicit old artifact path missing; do not silently substitute'
  import importlib.util
  module=importlib.util.spec_from_file_location('historical_builder',ROOT/'scripts/build-m5-baseline.py');builder=importlib.util.module_from_spec(module);module.loader.exec_module(builder)
  jar,proof=builder.build(ROOT/'.evidence/desktop'/os.environ['ROUTE_RUN_ID']/('historical-baseline-'+uuid.uuid4().hex))
  spec=dict(spec,runtimeSha256=proof['jarSha256'],runtimeMode=proof['mode']);return jar,spec
 assert jar.stat().st_size==spec['jarBytes'] and hashlib.sha256(jar.read_bytes()).hexdigest()==spec['jarSha256'],'M5 artifact does not match accepted provenance'
 return jar,dict(spec,runtimeSha256=spec['jarSha256'],runtimeMode='EXACT_ACCEPTED_ARTIFACT')

def acceptance(base,historical_provenance=None):
 base.mkdir(parents=True,exist_ok=False);f=HardeningFixture(base);suite=ET.Element('testsuite',name='UpgradeProcesses');case=ET.SubElement(suite,'testcase',classname='UpgradeProcesses',name='AC054_genuineM5RuntimeQueuedAndManualSurviveV8');problem=None
 try:
  if historical_provenance is None:jar,spec=baseline_jar()
  else:
   from gate_common import fixed
   provenance=json.loads(historical_provenance.read_text());spec=json.loads((ROOT/'config/upgrade/m5-fixture.json').read_text());jar=pathlib.Path(provenance['jarPath'])
   assert provenance['mode']=='PINNED_HISTORICAL_SOURCE_REBUILD' and provenance['sourceFingerprint']==spec['sourceFingerprint']
   assert provenance['archiveSha256']==spec['historicalArchiveSha256'] and hashlib.sha256(jar.read_bytes()).hexdigest()==provenance['jarSha256']
   assert fixed.source_fingerprint(jar.parent.parent)==spec['sourceFingerprint']
   spec=dict(spec,runtimeSha256=provenance['jarSha256'],runtimeMode=provenance['mode'])
  f.start();f.setup_catalog();old=f.launch('genuine-m5',jar,{'ROUTE_ENGINE_ENABLED':'true'})
  versions=f.sql('SELECT version FROM flyway_schema_history WHERE success=1 ORDER BY installed_rank').splitlines();assert versions==spec['migrationVersions']
  manual=f.execute(old,[spec['manualLeaf']]);f.wait(lambda:f.status(manual)=='MANUAL_WAIT:0','old engine manual boundary')
  f.configure(old,enabled=False)
  route=f.publish(old,[spec['queuedLeaf']]);queued=f.api(old,'POST','/executions',{'routeId':route,'priority':'LOW','admissionMode':'QUEUE','input':{}},str(uuid.uuid4()),202)[1]['executionId']
  assert f.status(queued)=='QUEUED:0'
  bound="SELECT route_id,version,definition_hash,definition_json,adapter_bindings FROM route_versions ORDER BY route_id,version"
  before=f.sql(bound);manualBefore=f.snapshot(manual);queueBefore=f.snapshot(queued)
  f.kill(old);new=f.launch('m6-migration')
  assert f.sql('SELECT version FROM flyway_schema_history WHERE success=1 ORDER BY installed_rank').splitlines()==versions+['8']
  assert f.sql(bound)==before and f.snapshot(manual)==manualBefore and f.snapshot(queued)==queueBefore
  incident=f.api(new,'GET','/executions/'+manual+'/incidents',expected=200)[1]['incidents'][0]
  body={'incidentId':incident['incidentId'],'stepId':incident['stepId'],'action':'RETRY','admissionMode':'QUEUE','reason':'Verified old engine upgrade fixture'}
  f.api(new,'POST','/executions/'+manual+'/recoveries',body,str(uuid.uuid4()),202)
  f.configure(new,enabled=True);f.kill(new)
  running=f.launch('m6-resume',extra={'ROUTE_ENGINE_ENABLED':'true','ROUTE_SCHEDULER_ENABLED':'true'})
  for id in [queued,manual]:f.wait(lambda:f.status(id)=='SUCCEEDED:0','upgraded fixture '+id)
  assert f.sql(bound)==before
  assert f.sql("SELECT CONCAT(route_version,':',priority) FROM executions WHERE id='"+queued+"'")=='1:LOW'
  assert f.sql("SELECT permit_generation FROM executions WHERE id='"+manual+"'")=='2'
  proof={'oldJarSha256':spec['runtimeSha256'],'oldRuntimeMode':spec['runtimeMode'],'acceptedJarSha256':spec['jarSha256'],'oldSourceFingerprint':spec['sourceFingerprint'],'oldPid':old['process'].pid,'newPid':running['process'].pid,'versionsBefore':versions,'versionsAfter':versions+['8'],'definitionsAndBindingsUnchanged':True,'beforeDefinitionRows':before,'afterDefinitionRows':f.sql(bound),'manualBefore':manualBefore,'queuedBefore':queueBefore,'manualAfter':f.snapshot(manual),'queuedAfter':f.snapshot(queued),'queuedPriority':'LOW','manualPermitGeneration':2}
  (base/'upgrade-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
 except Exception as e:problem=e;ET.SubElement(case,'failure').text=traceback.format_exc();(base/'failure.log').write_text(traceback.format_exc())
 finally:
  (base/'junit').mkdir(exist_ok=True);ET.ElementTree(suite).write(base/'junit/TEST-UpgradeProcesses.xml',encoding='utf-8',xml_declaration=True);f.cleanup()
 if problem:raise problem
