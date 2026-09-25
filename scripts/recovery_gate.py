#!/usr/bin/env python3
"""Cumulative M0-M5 gate. Real MariaDB suites plus independent-JVM/HTTP recovery proofs."""
import json,os,sys,subprocess,traceback,xml.etree.ElementTree as ET
from gate_common import ROOT,fixed,evidence_path
from crash_boundary import validate_crash_boundary
from recovery_processes import process_acceptance

WINDOWS={'recovery-after-enqueue','recovery-after-admission','recovery-during-external-work','recovery-after-result-release'}
def validate_recovery_proof(proof):
 assert proof['discovery']['unknownFieldsRejected']==3 and proof['discovery']['unchanged'] is True
 assert proof['discovery']['incident']['operationId'] and proof['discovery']['incident']['stepId']
 assert len(proof['races'])==1
 race=proof['races'][0]
 assert len(set(race['pids']))==2 and all(isinstance(p,int) and p>0 for p in race['pids'])
 assert race['sameKeyRequests']==20 and race['sameKeyDecisions']==1 and race['differentActionStatuses']==[202,409]
 assert proof['runningCancel']['externalStatus']=='STOPPED' and proof['runningCancel']['generation']==1
 assert proof['resolve']['state']=='SUCCEEDED:0' and proof['resolve']['audited'] is True
 assert proof['resolve']['counts'][proof['resolve']['existingOperation']]=={'effects':1,'submits':1}
 assert len(proof['crashes'])==4 and {c['window'] for c in proof['crashes']}==WINDOWS
 for c in proof['crashes']:
  validate_crash_boundary(c)
  assert c['killed_pids'] and all(p>0 for p in c['killed_pids']) and c['exit_codes']==[-9]*len(c['killed_pids'])
  assert c['restarted_pid']>0 and c['restarted_pid'] not in c['killed_pids']
  assert c['permit_generation']==2 and c['after_restart']['execution']=='SUCCEEDED:0'
  assert c['new_operation']!=c['old_operation'] and c['new_operation'] in c['after_restart']['attempts']
  assert set(c['counts'])=={c['old_operation'],c['new_operation']}
  assert all(v=={'effects':1,'submits':1} for v in c['counts'].values())
  before=c['before']['execution']
  assert before=={'recovery-after-enqueue':'RECOVERY_QUEUED:0','recovery-after-admission':'RECOVERING:1','recovery-during-external-work':'RECOVERING:1','recovery-after-result-release':'SUCCEEDED:0'}[c['window']]
  assert c['before']==c['after_kill'],'Crash must not mutate persistent state'
  if c['window'] in ('recovery-during-external-work','recovery-after-result-release'):
   assert c['new_operation'] in c['before']['attempts'] and c['before_counts'][c['new_operation']]=={'effects':1,'submits':1}

def validate_boundary_drain(record):
 validate_crash_boundary(record)
 attempts=record['boundary']['quiescence_attempts'];assert len(attempts)>=2
 assert attempts[0]['db_check']['active_transactions']>0 and attempts[0]['db_check']['lock_waits']>0
 assert [p['pid'] for p in attempts[0]['resumes']]==record['killed_pids']
 assert attempts[0]['drain_observations'][-1]['active_transactions']==0
 assert attempts[-1]['db_check']['active_transactions']==attempts[-1]['db_check']['active_commands']==0
 assert record['restarted_pid'] not in record['killed_pids'] and record['after_restart']['execution']=='SUCCEEDED:0'
 assert record['permit_generation']==2 and record['old_operation']!=record['new_operation']
 assert set(record['counts'])=={record['old_operation'],record['new_operation']} and all(v=={'effects':1,'submits':1} for v in record['counts'].values())

OPERATOR_SHAPES={'plain','escaped','nested','field','integer','decimal','true','false','null','credential'}
OPERATOR_METADATA={'resolve-reason','resolve-evidence','resolve-key','resolve-requestId','skip-reason','skip-key','cancel-reason','cancel-key'}
OPERATOR_MODES={'resolve','skip-queue','skip-now','capacity-reject'}
OPERATOR_ABSENT={'null:STOPPED','true:FAILED','false:RETRY','null:CANCEL','true:CANCEL'}
def validate_operator_proof(proof):
 assert proof['syntheticCredentialsOnly'] is True and proof['distinctEngineDatabase'] is True
 cases=proof['cases'];by_name={c['case']:c for c in cases};assert len(cases)==len(by_name)==57
 unsafe={mode+':'+shape for mode in OPERATOR_MODES for shape in OPERATOR_SHAPES}|OPERATOR_METADATA
 expected=unsafe|{'control:'+mode for mode in OPERATOR_MODES}|{'absent:'+value for value in OPERATOR_ABSENT}
 assert set(by_name)==expected
 for name in unsafe:
  c=by_name[name];assert c['status']==422 and c['unchanged'] is True and c['submits']==1
  assert c['state']==('RECONCILING:1' if name.startswith(('resolve','cancel')) else 'MANUAL_WAIT:0')
 for mode in OPERATOR_MODES:
  c=by_name['control:'+mode]
  assert c['status']==(200 if mode=='resolve' else 409 if mode=='capacity-reject' else 202)
  assert c['state']==('MANUAL_WAIT:0' if mode=='capacity-reject' else 'SUCCEEDED:0')
  assert c['replayWithoutCredentialFile'] is True and c['submits']==1
 for value in OPERATOR_ABSENT:
  c=by_name['absent:'+value];action=value.split(':')[1]
  assert c['status']==(200 if action in ('STOPPED','FAILED') else 202) and c['optionalOutputAbsent'] is True
  assert c['state']==('CANCELLED:0' if action=='CANCEL' else 'MANUAL_WAIT:0')

def main():
 base=evidence_path(ROOT,sys.argv[1]);base.mkdir(parents=True,exist_ok=True)
 rc=subprocess.run(['bash','scripts/verify-phase.sh','M4',str(base/'m4')],cwd=ROOT).returncode
 if rc:return rc
 old=fixed.load_json(base/'m4/summary.json')
 result={'phase':'M5','source_fingerprint':os.environ['ROUTE_SOURCE_FINGERPRINT'],'production_authorized':False,
  'checks':[{**c,'evidence':'m4/'+c['evidence']} for c in old['checks']],
  'suites':[{**s,'report':'m4/'+s['report']} for s in old['suites']]}
 try:
  process_acceptance(base/'processes')
  validate_recovery_proof(fixed.load_json(base/'processes/recovery-proof.json'))
  report=base/'processes/junit/TEST-RecoveryProcesses.xml';counts=fixed.junit_counts(report)
  validate_boundary_drain(fixed.load_json(base/'processes/recovery-proof.json')['boundaryDrain'])
  assert counts['tests']==9 and not any(counts[k] for k in ('failures','errors','skipped')),'Recovery process cases incomplete'
  java=[s for s in old['suites'] if s['name']=='TEST-dev.routeengine.RecoveryIT'];assert len(java)==1,'Missing actual RecoveryIT report'
  names=[c.attrib['name'] for c in ET.parse(base/'m4'/java[0]['report']).getroot().iter('testcase')]
  assert sum('allActionsModesRejectAtomically' in n for n in names)==8,'All four actions and two modes mandatory'
  for n in range(42,51):assert any('AC%03d'%n in x for x in names),'Missing M5 actual case AC-%03d'%n
  cancel=[s for s in old['suites'] if s['name']=='TEST-dev.routeengine.RecoveryCancellationIT'];assert len(cancel)==1,'Missing mandatory claim/cancel/execute integration'
  cancel_report=base/'m4'/cancel[0]['report'];cancel_counts=fixed.junit_counts(cancel_report)
  assert cancel_counts=={'tests':1,'failures':0,'errors':0,'skipped':0}
  cancel_xml=ET.parse(cancel_report).getroot()
  assert [n.attrib['name'] for n in cancel_xml.iter('testcase')]==['AC048_claimBeforeCancelRetainsPermitUntilRealTerminalObservationAndStopsNewClaims']
  lines=[line for output in cancel_xml.iter('system-out') for line in (output.text or '').splitlines() if line.startswith('CANCEL_INTERLEAVING_PROOF ')]
  assert len(lines)==1,'Missing actual HTTP cancellation interleaving proof'
  cancel_proof=json.loads(lines[0].split(' ',1)[1]);op=cancel_proof['operationId']
  assert cancel_proof['submitAfterCancel']==1 and cancel_proof['newClaimsAfterCancel']==0 and cancel_proof['permitGeneration']==1
  assert cancel_proof['cancelRequests']==2 and cancel_proof['observations']==2 and cancel_proof['finalState']=='CANCELLED:0'
  assert cancel_proof['heldUntilTerminalObservation'] is True and cancel_proof['distinctEngineDatabase'] is True
  assert cancel_proof['httpEvents']==[method+':'+op for method in ['POST','DELETE','GET','DELETE','GET']]
  fixed.atomic_json(base/'cancel-interleaving-proof.json',cancel_proof)
  protected=[s for s in old['suites'] if s['name']=='TEST-dev.routeengine.RecoveryOutputProtectionIT'];assert len(protected)==1,'Missing mandatory operator output protection suite'
  assert fixed.junit_counts(base/'m4'/protected[0]['report'])=={'tests':57,'failures':0,'errors':0,'skipped':0}
  operator_proof=fixed.load_json(base/'m4/m3/m2/m1/operator-output-proof.json');validate_operator_proof(operator_proof)
  fixed.atomic_json(base/'operator-output-proof.json',operator_proof)
  result['suites'].append({'name':'RecoveryProcesses',**counts,'report':report.relative_to(base).as_posix()})
  for n in range(42,51):
   name='AC-%03d'%n
   (base/(name+'.log')).write_text('Executed real MariaDB RecoveryIT, historical migration and all cumulative suites; independent JVM public API action/idempotency races; four SIGKILL windows with actual HTTP operation/effect counts. Read m4 cumulative raw reports and processes/recovery-proof.json, remote-proof.json, crash-proof.json, raw command/exit/logs. Engineering candidate only, no production authorization.\n')
   result['checks'].append({'id':name,'status':'PASS','evidence':name+'.log'})
 except Exception:
  (base/'failure.log').write_text(traceback.format_exc())
  for n in range(42,51):result['checks'].append({'id':'AC-%03d'%n,'status':'FAIL','evidence':'failure.log'})
 fixed.atomic_json(base/'summary.json',result)
 try:fixed.validate_gate(result,base,fixed.load_json(ROOT/'ai-kit/requirements.json'),'M5',os.environ['ROUTE_SOURCE_FINGERPRINT'])
 except Exception as error:print('M5 FAILED:',error);return 1
 print('M5 cumulative executable gate passed; fresh review pending');return 0
if __name__=='__main__':sys.exit(main())
