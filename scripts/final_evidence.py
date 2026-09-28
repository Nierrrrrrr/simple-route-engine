"""Strict import boundary for previously executed fresh-agent handoff evidence."""
import json,pathlib,re,xml.etree.ElementTree as ET
from gate_common import ROOT,fixed
from final_handoff import sha,java_hashes,example_hashes
from final_async import validate_lifecycle

PROOF_KEYS={'schema_version','kind','run_id','source_fingerprint','source_fingerprint_after','java_before','java_after','examples_before','examples_after','jar_sha256','authored_config_source','authored_config_sha256','route6_id','cases','suite','cleanup_completed','fixture','agent_freshness','build_tests_run','async_lifecycle','files'}
RECEIPT_KEYS={'schema_version','role','agent_id','agent_call_number','run_id','source_fingerprint','proof_sha256','evidence_directory'}
CASE_KEYS={'route_id','execution_id','config','config_sha256','trace','stdout','command','exit','pid','terminal'}
def artifact(base,name,*,nonempty=True):
 assert isinstance(name,str) and name and '\\' not in name
 relative=pathlib.PurePosixPath(name);assert not relative.is_absolute() and '..' not in relative.parts and ':' not in name
 raw=base/name;path=raw.resolve();assert path.is_relative_to(base.resolve()) and path.is_file()
 assert not nonempty or path.stat().st_size>0
 assert not any(p.is_symlink() for p in [raw,*raw.parents] if p!=base.parent)
 return path

def manifest_artifact(base,name):
 auxiliary=bool(re.fullmatch(r'fixture/raw-[0-9]+-[^/]+\.log',name))
 if auxiliary:
  # A successful command may emit no output; its command and exit still exist.
  artifact(base,name[:-4]+'.command.json');artifact(base,name[:-4]+'.exit')
 return artifact(base,name,nonempty=not auxiliary)

def validate_handoff(base,receipt,fingerprint,run_id,java,examples,minimum_call,*,root=ROOT):
 assert base.is_dir() and not base.is_symlink()
 proof_path=artifact(base,'handoff-proof.json');p=json.loads(proof_path.read_text())
 assert set(p)==PROOF_KEYS and set(receipt)==RECEIPT_KEYS
 assert p['schema_version']==receipt['schema_version']==1
 assert p['kind']=='EXTERNAL_FRESH_HANDOFF_EXECUTION' and p['agent_freshness']=='CONTROLLER_ATTESTATION_REQUIRED'
 assert p['run_id']==receipt['run_id']==run_id and p['source_fingerprint']==p['source_fingerprint_after']==receipt['source_fingerprint']==fingerprint
 assert receipt['role']=='FRESH_ACCEPTANCE' and isinstance(receipt['agent_id'],str) and receipt['agent_id'].strip()
 assert type(receipt['agent_call_number']) is int and receipt['agent_call_number']>minimum_call
 assert receipt['proof_sha256']==sha(proof_path) and receipt['evidence_directory']==base.relative_to(root).as_posix()
 assert p['java_before']==p['java_after']==java and java
 assert p['examples_before']==p['examples_after']==examples and len(examples)==5
 assert p['cleanup_completed'] is True and p['build_tests_run'] is False
 assert re.fullmatch('[a-f0-9]{64}',p['jar_sha256'])
 assert set(p['fixture'])=={'database','namespace','run_id'} and p['fixture']['run_id']==run_id
 assert p['fixture']['database'].startswith('re-m1-'+run_id+'-') and p['fixture']['namespace'].startswith('re-m4-')
 files=p['files'];assert isinstance(files,dict) and files
 actual={path.relative_to(base).as_posix() for path in base.rglob('*') if path.is_file() and path!=proof_path}
 assert set(files)==actual
 for name,digest in files.items():
  assert re.fullmatch('[a-f0-9]{64}',digest) and sha(manifest_artifact(base,name))==digest
 assert p['async_lifecycle']=='async-lifecycle.json'
 validate_lifecycle(json.loads(artifact(base,p['async_lifecycle']).read_text()),json.loads(artifact(base,'fixture/remote-proof.json').read_text())['submits'])
 authored=artifact(root,p['authored_config_source']);assert authored.is_relative_to(root/'.evidence/desktop'/run_id)
 assert sha(authored)==p['authored_config_sha256']==sha(artifact(base,'authored-route.json'))
 six=json.loads((base/'authored-route.json').read_text());route6=six['definition']['routeId'];assert route6==p['route6_id'] and six['name'].startswith('DEMO ')
 expected={'demo-delivery-'+str(i) for i in range(1,6)};assert route6.startswith('demo-') and route6 not in expected;expected.add(route6)
 assert len(p['cases'])==6 and {c['route_id'] for c in p['cases']}==expected
 assert len({c['execution_id'] for c in p['cases']})==6 and len({c['pid'] for c in p['cases']})==1
 for c in p['cases']:
  assert set(c)==CASE_KEYS and type(c['pid']) is int and c['pid']>0
  config=artifact(base,c['config']);payload=json.loads(config.read_text());route=c['route_id'];assert payload['definition']['routeId']==route and payload['definition']['version']==1 and sha(config)==c['config_sha256']
  if route==route6:assert sha(config)==p['authored_config_sha256']
  else:assert sha(config)==examples['examples/delivery/demo-'+route.rsplit('-',1)[1]+'.json']
  assert artifact(base,c['exit']).read_text().strip()=='0'
  command=json.loads(artifact(base,c['command']).read_text());assert command[:3]==['python3','-B','scripts/publish-demo.py'] and len(command)==4 and pathlib.Path(command[3]).name==config.name
  stdout=[json.loads(line) for line in artifact(base,c['stdout']).read_text().splitlines()];assert len(stdout)==2 and stdout[0]['executionId']==c['execution_id'] and stdout[1]==c['terminal']
  terminal=c['terminal'];assert terminal['executionId']==c['execution_id'] and terminal['routeId']==route and terminal['state']=='SUCCEEDED' and terminal['permitHeld'] is False
  trace=json.loads(artifact(base,c['trace']).read_text());assert len(trace)>=5
  expected_prefix=[('POST','/routes',201),('POST','/routes/'+route+'/versions',201),('POST','/routes/'+route+'/versions/1/publish',200),('POST','/executions',202)]
  assert [(r['method'],r['path'],r['status']) for r in trace[:4]]==expected_prefix and trace[3]['body']==stdout[0]
  assert all(r['method']=='GET' and r['path']=='/executions/'+c['execution_id'] and r['status']==200 for r in trace[4:]) and trace[-1]['body']==terminal
 suite=p['suite'];assert set(suite)=={'report','tests','failures','errors','skipped'} and suite['report']=='junit/TEST-FreshHandoff.xml'
 report=artifact(base,suite['report']);counts=fixed.junit_counts(report)
 assert {k:suite[k] for k in counts}==counts and counts=={'tests':6,'failures':0,'errors':0,'skipped':0}
 parsed=ET.parse(report).getroot();assert parsed.attrib.get('tests')=='6' and all(parsed.attrib.get(k)=='0' for k in ['failures','errors','skipped'])
 assert {c.attrib['name'] for c in parsed.iter('testcase')}=={'AC061_publishExecute_'+route for route in expected}
 return p

def current_context(run_id):
 run_root=ROOT/'.evidence/desktop'/run_id
 from final_java_baseline import load_java_baseline
 java=java_hashes();assert java==load_java_baseline(run_id)
 state=json.loads((ROOT/'docs/implementation/STATE.json').read_text());assert state['current_phase']=='FINAL' and state['run_id']==run_id
 return java,example_hashes(),state['agent_calls']['total_known']
