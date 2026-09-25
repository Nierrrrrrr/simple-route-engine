#!/usr/bin/env python3
"""M4 cumulative real HTTP/MariaDB/kind/Runner acceptance; no unavailable-environment fallback."""
import json,os,sys,subprocess,shutil,traceback,hashlib,re,xml.etree.ElementTree as ET
from gate_common import ROOT,fixed,evidence_path
from adapter_fixture import AdapterFixture
from adapter_artifacts import collect
from adapter_processes import process_acceptance
from runner_image import prepare
from crash_boundary import validate_crash_boundary

JAVA_SUITES=['AdapterContractTest','RestAdapterTest','RestEngineAcceptance','KubernetesAcceptance','AdapterBoundaryAcceptance']
SCALAR_BLOCKED_CASES={'numeric-text','integer','nested-integer','decimal','canonical-exponent','boolean-true','nested-true','boolean-false','nested-false','null-value','nested-null'}
SCALAR_CONTROL_CASES={'control-integer','control-decimal','control-true','control-false','control-null'}

def validate_scalar_proof(proof):
 expected=SCALAR_BLOCKED_CASES|SCALAR_CONTROL_CASES
 cases=proof['cases'];assert proof['actualHttpSubmits']==len(expected) and len(cases)==len(expected),'Missing actual scalar HTTP cases'
 assert {c['case'] for c in cases}==expected,'Missing scalar boundary variant'
 for c in cases:
  blocked=c['case'] in SCALAR_BLOCKED_CASES
  assert c['blocked'] is blocked and c['secretPersisted'] is False,'Scalar credential persisted'
  assert c['auditSecretAbsent'] is True and c['responseBodyLogged'] is False,'Scalar secret audit/log leak'
  assert c['state']==('RECONCILING:1' if blocked else 'SUCCEEDED:0'),'Scalar outcome or permit mismatch'
  assert c['outputAbsent'] is blocked and c['inDoubtIncidents']==(1 if blocked else 0),'Scalar output or incident mismatch'
  assert c['downstreamAttempts']==(0 if blocked else 1),'Unsafe dispatch or legitimate scalar rejected'

def integration_acceptance(base,image=None):
 base.mkdir(parents=True,exist_ok=False);f=AdapterFixture(base);problem=None;suite=ET.Element('testsuite',name='AdapterArtifacts')
 try:
  f.start()
  if image is None:image=prepare(f)
  else:(base/'runner-image-ref.txt').write_text(image+'\n')
  f.setup_catalog(image)
  f.runner_canary(image)
  rc,_=f.command_result(['./mvnw','-B','-Dtest=RestAdapterTest,AdapterContractTest','-Dit.test=RestEngineAcceptance,KubernetesAcceptance,AdapterBoundaryAcceptance','verify'],'maven-adapters')
  if rc:
   try:collect(f,require_success=False)
   except Exception:(base/'failed-artifact-read.log').write_text(traceback.format_exc())
   raise AssertionError('Real adapter Maven suite failed: exit '+str(rc))
  case=ET.SubElement(suite,'testcase',classname='AdapterArtifacts',name='AC041_successfulRunnerArtifactsSurvivePodDeletionAndAllContentsExcludeSecret')
  try:
   collect(f,require_success=True)
   ET.SubElement(suite,'testcase',classname='AdapterArtifacts',name='AC041_inheritedCanaryNeverEntersRunnerCommandArtifact')
  except Exception:ET.SubElement(case,'failure').text=traceback.format_exc();raise
 except Exception as error:problem=error;(base/'failure.log').write_text(traceback.format_exc())
 finally:
  (base/'junit').mkdir(exist_ok=True)
  for name in JAVA_SUITES:
   source=ROOT/'target'/('failsafe-reports' if name.endswith('Acceptance') else 'surefire-reports')/('TEST-dev.routeengine.'+name+'.xml')
   if source.exists():shutil.copyfile(source,base/'junit'/source.name)
  ET.ElementTree(suite).write(base/'junit/TEST-AdapterArtifacts.xml',encoding='utf-8',xml_declaration=True)
  try:f.cleanup()
  except Exception as error:problem=problem or error;(base/'cleanup-failure.log').write_text(traceback.format_exc())
 if problem:raise problem
 return image

def validate_m4_reports(base):
 reports=[base/'integration/junit'/('TEST-dev.routeengine.'+n+'.xml') for n in JAVA_SUITES]+[base/'integration/junit/TEST-AdapterArtifacts.xml',base/'processes/junit/TEST-AdapterProcesses.xml']
 context=fixed.load_json(base/'integration/runner-context.json')
 actual={p.relative_to(ROOT/'config/runner').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'config/runner').rglob('*')) if p.is_file()}
 assert context==actual,'Runner image context differs from current source'
 image=(base/'integration/runner-image-ref.txt').read_text().strip();assert re.fullmatch('docker.io/route-engine/runner@sha256:[a-f0-9]{64}',image)
 for name in ['runner-image-build','runner-image-load','runner-digest-alias','runner-versions']:
  paths=list((base/'integration').glob('raw-*-'+name+'.exit'));assert paths,'Missing actual image command '+name
  for path in paths:assert path.read_text().strip()=='0' and path.with_suffix('.command.json').stat().st_size>0 and path.with_suffix('.log').stat().st_size>0,'Image command failed or missing evidence'
 names=[];suites=[]
 for path in reports:
  counts=fixed.junit_counts(path);assert counts['tests']>0 and not any(counts[k] for k in ('failures','errors','skipped')),str(path)
  names.extend(c.attrib.get('name','') for c in ET.parse(path).getroot().iter('testcase'))
  suites.append({'name':path.stem,**counts,'report':path.relative_to(base).as_posix()})
 for n in range(32,42):assert any('AC%03d_'%n in name for name in names),'Missing actual M4 testcase AC-%03d'%n
 validate_scalar_proof(fixed.load_json(base/'integration/scalar-secret-boundary.json'))
 decoded=fixed.load_json(base/'integration/decoded-secret-boundary.json')
 assert decoded['actualHttpSubmits']==6 and len(decoded['cases'])==6
 assert all(c['state']=='RECONCILING:1' and c['secretPersisted'] is False for c in decoded['cases'])
 for change in ['playbook','image','target']:
  bound=fixed.load_json(base/('integration/queued-binding-'+change+'.json'))
  assert bound['sameDefinitionHash'] is True and bound['rebound'] is False and bound['state']=='RECONCILING:1'
  assert bound['newVersion']==2 and bound['newVersionAdoptsCurrentBinding'] is True
 bound=fixed.load_json(base/'integration/retry-binding-proof.json')
 assert bound['actualHttpSubmits']==1 and bound['oldState']=='RECONCILING:1' and bound['newVersionAdoptsCurrentBinding'] is True
 bound=fixed.load_json(base/'integration/binding-immutability-proof.json')
 assert bound['directSqlRejected']==2 and bound['sqlState']=='45000' and bound['originalUnchanged'] is True
 bound=fixed.load_json(base/'integration/reference-publication-proof.json')
 assert bound['rejected']>=10 and bound['draftPreserved'] is True and bound['noDevelopmentBypass'] is True
 bound=fixed.load_json(base/'integration/reference-runtime-proof.json')
 assert bound['rejected']>=3 and bound['noExternalIo'] is True
 proof=fixed.load_json(base/'integration/artifact-survival-proof.json')
 assert proof['canaryOperationId'] and proof['canaryCommandSecretAbsent'] is True
 assert proof['rc']==0 and proof['status']=='successful' and proof['jobEvents']>=4 and proof['commandsScanned']>=1 and proof['allArtifactFilesScanned']>proof['jobEvents']
 assert proof['deletedPodUids'] and proof['afterPodDeletion'] is True and proof['secretAbsent'] is True and proof['databaseAndLogSecretAbsent'] is True
 proof=fixed.load_json(base/'integration/deployment-uid-generation-conflict.json');assert proof['actualConflict']==409 and proof['uid'] and proof['generation']==1 and proof['state']=='SUCCEEDED:0'
 proof=fixed.load_json(base/'integration/failed-rollout-stopped.json');assert proof['pods']==0 and proof['state']=='MANUAL_WAIT:0'
 proof=fixed.load_json(base/'integration/job-missing-retained.json');assert proof['uid'] and proof['state']=='RECONCILING:1'
 marker=fixed.load_json(base/'integration/runner-cancel-task-started.json');assert marker['event']=='runner_on_start' and marker['task']=='Bounded synchronous wait'
 proof=fixed.load_json(base/'integration/runner-cancel-converged.json');assert proof['operation']==marker['operationId'] and proof['permitGeneration']>0 and proof['state']=='CANCELLED:0'
 crashes=json.loads((base/'processes/crash-proof.json').read_text())
 assert isinstance(crashes,list),'Crash proof must contain actual process records'
 for window in ['real-http-side-effect-before-result-db','non-dedupe-http-unknown','real-job-created-before-result-db']:
  entries=[c for c in crashes if c['window']==window];assert len(entries)==1
  c=entries[0];validate_crash_boundary(c);assert c['killed_pids'] and all(code==-9 for code in c['exit_codes']) and c['restarted_pid'] not in c['killed_pids']
  assert c['operation'] in c['before']['attempts'] and c['operation'] in c['after_restart']['attempts']
  if window.startswith('real-job'):assert c['job_uid'] and c['job_count']==1
  else:assert c['side_effects']==c['submits']==1
 return suites

def main():
 base=evidence_path(ROOT,sys.argv[1]);base.mkdir(parents=True,exist_ok=True)
 rc=subprocess.run(['bash','scripts/verify-phase.sh','M3',str(base/'m3')],cwd=ROOT).returncode
 if rc:return rc
 old=fixed.load_json(base/'m3/summary.json')
 result={'phase':'M4','source_fingerprint':os.environ['ROUTE_SOURCE_FINGERPRINT'],'production_authorized':False,
  'checks':[{**c,'evidence':'m3/'+c['evidence']} for c in old['checks']],'suites':[{**s,'report':'m3/'+s['report']} for s in old['suites']]}
 try:
  image=integration_acceptance(base/'integration');process_acceptance(base/'processes',image)
  result['suites']+=validate_m4_reports(base)
  for n in range(32,42):
   name='AC-%03d'%n
   (base/(name+'.log')).write_text('Actual real HTTP/MariaDB/kind/Runner suites and SIGKILL/restart passed. See integration/junit, processes/junit, raw command logs/exits, real UID/generation/conflict/stop proofs, all-pvc-artifacts.log, artifact-survival-proof.json and crash-proof.json. No production/external acceptance or exactly-once guarantee.\n')
   result['checks'].append({'id':name,'status':'PASS','evidence':name+'.log'})
 except Exception:
  (base/'failure.log').write_text(traceback.format_exc())
  for n in range(32,42):result['checks'].append({'id':'AC-%03d'%n,'status':'FAIL','evidence':'failure.log'})
 fixed.atomic_json(base/'summary.json',result)
 try:fixed.validate_gate(result,base,fixed.load_json(ROOT/'ai-kit/requirements.json'),'M4',os.environ['ROUTE_SOURCE_FINGERPRINT'])
 except Exception as error:print('M4 FAILED:',error);return 1
 print('M4 cumulative executable gate passed; independent review pending');return 0
if __name__=='__main__':sys.exit(main())
