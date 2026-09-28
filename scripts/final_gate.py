#!/usr/bin/env python3
"""FINAL cumulative execution plus transparent import of a controller-attested fresh handoff."""
import json,os,pathlib,shutil,subprocess,sys,traceback,xml.etree.ElementTree as ET
from gate_common import ROOT,fixed,evidence_path
from final_evidence import validate_handoff,current_context,artifact,manifest_artifact
from final_handoff import sha

FAULT_CASES={
 'atomic-commit':'AC023_resultAndNextPendingAtomicAndInitializationUnique',
 'rollback-before-result-commit':'AC023_completionRollbackLeavesNeitherResultNextPendingNorEvent',
 'after-result-commit-sigkill':'AC023_resultAndNextPendingCommitThenSigkillRestart',
 'parallel-crash':'AC025_AC028_twoJvmParallelBranchCrashReconcilesSameIdentity',
 'response-lost-before-db-result':'AC033_realHttpSideEffectSigkillBeforeResultAndOriginalOperationReconciled',
 'unsafe-unknown':'AC034_unknownWithoutDedupeOrQuerySurvivesSigkillWithoutResubmit',
 'job-created-before-result':'AC036_realJobCreatedThenSigkillKeepsSameUidAndNeverUsesAppPodOwner',
 'recovery-queued':'AC042_AC043_AC050_realHttpRecoveryCrash_after_enqueue',
 'recovery-admitted-before-dispatch':'AC042_AC043_AC050_realHttpRecoveryCrash_after_admission',
 'recovery-external-before-db-result':'AC042_AC043_AC050_realHttpRecoveryCrash_during_external_work',
 'recovery-after-result-release':'AC042_AC043_AC050_realHttpRecoveryCrash_after_result_release',
 'manual-unknown-resolution':'AC049_evidenceResolvesExactRealUnknownOperationWithoutResubmission',
 'shutdown-before-new-claim':'AC053_claimBlockedOnDatabaseMustRecheckShutdown',
 'six-hour-domain-clock':'AC026_sixHourDomainBudgetAndBackoffPersistWithoutChangingDbLeaseClock',
 'short-wall-clock-restart':'AC026_shortWallClockRetryPersistsAcrossKilledJvm'}

def fault_matrix(base,summary):
 index={}
 for suite in summary['suites']:
  report=artifact(base,suite['report']);counts=fixed.junit_counts(report)
  assert counts['tests'] and not any(counts[k] for k in ['failures','errors','skipped'])
  for case in ET.parse(report).getroot().iter('testcase'):index.setdefault(case.attrib['name'].removesuffix('()'),[]).append(suite['report'])
 assert set(FAULT_CASES.values())<=set(index),set(FAULT_CASES.values())-set(index)
 return {'clock_scope':'Six-hour injectable domain-clock test plus short actual wall-clock restart; not a six-hour soak','cases':{key:{'testcase':name,'reports':index[name]} for key,name in FAULT_CASES.items()}}

def prerequisite(base):
 run_id=os.environ['ROUTE_RUN_ID'];fingerprint=os.environ['ROUTE_SOURCE_FINGERPRINT']
 handoff=os.environ.get('ROUTE_FINAL_HANDOFF');receipt_path=os.environ.get('ROUTE_FINAL_HANDOFF_RECEIPT')
 assert handoff and receipt_path,'FINAL requires original fresh handoff evidence and controller receipt before cumulative execution'
 source=pathlib.Path(handoff).resolve();receipt_file=pathlib.Path(receipt_path).resolve();run_root=ROOT/'.evidence/desktop'/run_id
 assert source.is_relative_to(run_root) and receipt_file.is_relative_to(run_root) and not receipt_file.is_relative_to(source)
 assert not source.is_relative_to(base) and not base.is_relative_to(source)
 assert not any(p.is_symlink() for p in source.rglob('*'))
 receipt=json.loads(receipt_file.read_text());java,examples,minimum_call=current_context(run_id)
 proof=validate_handoff(source,receipt,fingerprint,run_id,java,examples,minimum_call)
 return source,receipt,proof

def import_handoff(source,base,receipt,proof):
 shutil.copytree(source,base/'external-handoff')
 for name,digest in proof['files'].items():assert sha(manifest_artifact(base/'external-handoff',name))==digest
 assert sha(base/'external-handoff/handoff-proof.json')==receipt['proof_sha256']
 (base/'handoff-controller-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 (base/'handoff-import.json').write_text(json.dumps({'execution':'PRIOR_EXTERNAL_FRESH_AGENT_EXECUTION_NOT_RERUN_BY_GATE','original_directory':str(source),'proof_sha256':receipt['proof_sha256'],'source_fingerprint':proof['source_fingerprint'],'artifact_hashes':proof['files'],'jar_sha256_at_handoff':proof['jar_sha256'],'freshness_authority':'Controller platform-derived identity plus independent Reviewer, not this script'},indent=2)+'\n')

def main():
 base=evidence_path(ROOT,sys.argv[1]);base.mkdir(parents=True,exist_ok=True)
 try:source,receipt,proof=prerequisite(base)
 except Exception as exc:
  (base/'prerequisite-failure.log').write_text(traceback.format_exc());print('FINAL prerequisite failed:',exc,file=sys.stderr);return 2
 import_handoff(source,base,receipt,proof)
 command=['bash','scripts/verify-phase.sh','M6',str(base/'m6')];(base/'cumulative.command.json').write_text(json.dumps(command)+'\n')
 rc=subprocess.run(command,cwd=ROOT).returncode;(base/'cumulative.exit').write_text(str(rc)+'\n')
 if rc:return rc
 old=fixed.load_json(base/'m6/summary.json');fingerprint=os.environ['ROUTE_SOURCE_FINGERPRINT']
 fixed.validate_gate(old,base/'m6',fixed.load_json(ROOT/'ai-kit/requirements.json'),'M6',fingerprint)
 result={'phase':'FINAL','source_fingerprint':fingerprint,'production_authorized':False,'checks':[{**c,'evidence':'m6/'+c['evidence']} for c in old['checks']],'suites':[{**s,'report':'m6/'+s['report']} for s in old['suites']]}
 final_suite=ET.Element('testsuite',name='FinalEvidence');error=None
 def check(rid,name,fn):
  nonlocal error
  case=ET.SubElement(final_suite,'testcase',classname='FinalEvidence',name=name)
  try:
   value=fn();path=base/(rid+'.json');path.write_text(json.dumps(value,indent=2)+'\n');result['checks'].append({'id':rid,'status':'PASS','evidence':path.name})
  except Exception as exc:
   error=exc;ET.SubElement(case,'failure').text=traceback.format_exc();(base/(rid+'.log')).write_text(traceback.format_exc());result['checks'].append({'id':rid,'status':'FAIL','evidence':rid+'.log'})
 def clean():
  m1=base/'m6/m5/m4/m3/m2/m1';commands=list(m1.glob('raw-*-maven-clean-verify.command.json'));assert len(commands)==1
  path=commands[0];assert json.loads(path.read_text())==['./mvnw','-B','clean','verify']
  assert path.with_name(path.name.replace('.command.json','.exit')).read_text().strip()=='0'
  build=fixed.load_json(base/'m6/build/build-proof.json');assert build['sourceUnchanged'] and build['inputs'] and build['testsRequiredByCumulativeGate']
  isolation=fixed.load_json(m1/'test-database-isolation.json');assert isolation['main_cleanup_verified'] and isolation['engine_cleanup_verified'] and isolation['main']['container_id']!=isolation['engine']['container_id']
  return {'clean_maven_command':str(path.relative_to(base)),'new_workspace_build':'m6/build/build-proof.json','real_isolated_databases':isolation,'real_kind_runner_evidence':'m6/m5/m4','cumulative_reports':len(old['suites']),'handoff_jar_sha256':proof['jar_sha256'],'cumulative_jar_sha256':sha(ROOT/'target/route-engine-0.1.0.jar'),'same_source_does_not_require_identical_jar_bytes':True}
 check('AC-059','AC059_cleanBuildAndAllCumulativeMandatorySuites',clean)
 def handoff_check():
  java,examples,minimum_call=current_context(os.environ['ROUTE_RUN_ID']);validate_handoff(source,receipt,fingerprint,os.environ['ROUTE_RUN_ID'],java,examples,minimum_call)
  return {'external_execution':True,'source_fingerprint':fingerprint,'import':'handoff-import.json','controller_receipt':'handoff-controller-receipt.json','report':'external-handoff/'+proof['suite']['report'],'route6':proof['route6_id'],'five_originals_preserved':True}
 check('AC-061','AC061_originalFreshAgentHandoffValidated',handoff_check)
 check('AC-062','AC062_actualFaultMatrixAndTimingScope',lambda:fault_matrix(base/'m6',old))
 def chain():
  protected=fixed.protected_files(ROOT);fixed.check_protected(ROOT,protected);assert fixed.source_fingerprint(ROOT)==fingerprint
  return {'source_fingerprint':fingerprint,'protected_files':len(protected),'validated_preceding_checks':result['checks'],'required_executable_ids':sorted(fixed.required_for(fixed.load_json(ROOT/'ai-kit/requirements.json'),'FINAL','EXECUTABLE')),'complete_check_and_report_index':'summary.json','traceability':'docs/implementation/TRACEABILITY.md','raw_cumulative_command':'cumulative.command.json','original_handoff_hash':receipt['proof_sha256'],'review_only':['AC-060']}
 check('AC-063','AC063_requirementReportsCommandsAndSourceChain',chain)
 def scope():
  text=(ROOT/'docs/verification/FINAL_ACCEPTANCE.md').read_text();state=fixed.load_json(ROOT/'docs/implementation/STATE.json')
  assert 'Status: CANDIDATE' in text and 'ENGINEERING_ACCEPTANCE=NOT_PASS' in text
  assert 'EXTERNAL_ACCEPTANCE=NOT_RUN' in text and 'PRODUCTION_DEPLOYMENT=NOT_AUTHORIZED' in text
  assert state['engineering_acceptance']=='NOT_PASS' and state['production_authorized'] is False and state['requested_stop_after']=='FINAL'
  return {'engineering_acceptance':'NOT_PASS_PENDING_FRESH_REVIEW','external_acceptance':'NOT_RUN','production_deployment':'NOT_AUTHORIZED','review_requirement':'AC-060','acceptance_authority':'Controller evidence-only FINAL_RESULT.json after new Reviewer'}
 check('AC-064','AC064_externalAndProductionBoundaries',scope)
 (base/'junit').mkdir();ET.ElementTree(final_suite).write(base/'junit/TEST-FinalEvidence.xml',encoding='utf-8',xml_declaration=True)
 result['suites'].append({'name':'final-evidence-validation',**fixed.junit_counts(base/'junit/TEST-FinalEvidence.xml'),'report':'junit/TEST-FinalEvidence.xml'})
 result['suites'].append({'name':'prior-external-fresh-agent-handoff',**{k:proof['suite'][k] for k in ['tests','failures','errors','skipped']},'report':'external-handoff/'+proof['suite']['report']})
 fixed.atomic_json(base/'summary.json',result)
 if error:print('FINAL failed:',error,file=sys.stderr);return 1
 fixed.validate_gate(result,base,fixed.load_json(ROOT/'ai-kit/requirements.json'),'FINAL',fingerprint)
 print('FINAL executable gate passed; independent AC-060 review and controller acceptance remain pending.');return 0
if __name__=='__main__':sys.exit(main())
