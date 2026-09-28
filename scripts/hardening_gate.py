#!/usr/bin/env python3
"""Cumulative M0-M6 executable gate. No FINAL or review-pass fabrication."""
import importlib.util,json,os,subprocess,sys,traceback,xml.etree.ElementTree as ET
from gate_common import ROOT,fixed,evidence_path
from hardening_processes import acceptance as processes
from hardening_shutdown import acceptance as shutdown
from hardening_upgrade import acceptance as upgrade
from hardening_build import acceptance as build
from hardening_documents import acceptance as documents
from demo_boundary import acceptance as demo_boundary

REQUIRED_CASES={'DemoBoundary':{'AC052_demoHelperRejectsUserinfo','AC052_demoHelperDoesNotForwardRedirectCredentials'},'HardeningProcesses':{'AC051_actualRoleSeparation','AC053_sigtermAndTwoOverlappingJvmRestart','AC055_metricsAuditAndDatabaseReadiness','AC058_fivePublishedRealAdapterDemos','AC052_realNamespaceRoleAuthorization','AC055_isolatedBackupAndRestore'},'ShutdownClaim':{'AC053_claimBlockedOnDatabaseMustRecheckShutdown'},'UpgradeProcesses':{'AC054_genuineM5RuntimeQueuedAndManualSurviveV8'},'CleanBuild':{'AC056_newWorkDirectoryBuild'},'DeliveryDocuments':{'AC057_completeDocumentsAndActualSymbols','AC058_fiveDemoSchemaAndExternalScope','AC057_currentDeliveryMatchesExecutableRepository','AC057_rejectStaleDeliveryClaims'}}

def validate_proofs(p,u,s):
 port=p['databasePortSelection'];assert port['allocator']=='Docker' and port['databaseEntrypointUsed'] is False and port['probeRemovedBeforeDatabase'] is True and port['retryOnTransferFailure'] is False
 assert port['endpoint']==p['metrics']['endpoint'] and port['endpoint'].startswith('127.0.0.1:')
 assert p['roles']['callerDenied']>=5 and p['roles']['operatorDenied']>=2 and p['roles']['wrongToken']==401
 assert len(p['roles']['startupRejected'])==2 and all(x['exit']!=0 for x in p['roles']['startupRejected'])
 assert p['roles']['operationalRead']==200 and p['roles']['foreignDecisionRead']==404 and p['roles']['operatorCancel']==202
 g=p['graceful'];assert g['exit']==143 and len(set(g['overlapPids']))==2 and g['oldPid'] not in g['overlapPids']
 assert g['effects']==g['submits']==g['permitGeneration']==1
 m=p['metrics'];assert m['readinessDbOutage']==503 and m['readinessRecoveredSamePid']==200 and m['restartSameEndpoint'] is True and m['auditRecords']>0
 assert m['values']['route.queue.depth']>=1 and m['values']['route.permits.total']==2 and m['values']['route.permits.noncritical']==1
 assert len(m['values'])==10 and all(isinstance(v,(int,float)) for v in m['values'].values())
 d=p['demos'];assert len(d)==5 and {x['route'] for x in d}=={'demo-delivery-'+str(i) for i in range(1,6)}
 assert all(x['state']=='SUCCEEDED:0' and len(x['definitionHash'])==64 for x in d)
 l=p['demoLifecycle'];assert len(l['startedPids'])==1 and l['exitBeforeAllCompleted'] is None
 assert all(x['pid']==l['startedPids'][0] and x['aliveAfterCompletion'] is True for x in d)
 r=p['rbac'];assert r['actualCreateGetDelete'] is True and len(r['actualDenied'])==3 and all(x['forbidden'] for x in r['actualDenied'])
 assert [x['allowed'] for x in r['decisions']]==[True,True,False,False,False]
 b=p['backup'];assert b['source']!=b['restored'] and len(b['dumpSha256'])==64 and len(b['comparisons'])==4
 assert all(x['source']==x['restored'] for x in b['comparisons'])
 assert u['oldSourceFingerprint']=='437f8be7254c3d2685a87b33c5aaaab0191fdca5814ff7834dde2092bfa89fb5'
 assert u['oldRuntimeMode'] in ('EXACT_ACCEPTED_ARTIFACT','PINNED_HISTORICAL_SOURCE_REBUILD')
 if u['oldRuntimeMode']=='EXACT_ACCEPTED_ARTIFACT':assert u['oldJarSha256']==u['acceptedJarSha256']=='0dbeee3eca2ee43e86d9a97bf089263bd007c722f9b8557ee71f1be901ec6072'
 assert u['oldPid']!=u['newPid'] and u['versionsBefore']==list(map(str,range(1,8))) and u['versionsAfter']==list(map(str,range(1,9)))
 assert u['definitionsAndBindingsUnchanged'] is True and u['beforeDefinitionRows']==u['afterDefinitionRows']
 assert u['manualBefore']['execution']=='MANUAL_WAIT:0' and u['queuedBefore']['execution']=='QUEUED:0'
 assert u['manualAfter']['execution']==u['queuedAfter']['execution']=='SUCCEEDED:0' and u['queuedPriority']=='LOW' and u['manualPermitGeneration']==2
 assert s['blocked']['lock_waits']>0 and s['attemptsAfterShutdown']==s['submitsAfterShutdown']==0 and s['exit']==143
 assert s['stateAfterShutdown']=='ADMITTED:1' and s['restartPid']!=s['pid'] and s['finalState']=='SUCCEEDED:0' and s['restartSubmits']==s['restartEffects']==1

def validate_reports(base):
 dp=fixed.load_json(base/'demo-boundary/demo-boundary-proof.json');assert dp['redirectSourceRequests']==1 and dp['sinkRequests']==[] and dp['syntheticCredentialOnly'] is True
 validate_proofs(fixed.load_json(base/'processes/hardening-proof.json'),fixed.load_json(base/'upgrade/upgrade-proof.json'),fixed.load_json(base/'shutdown/shutdown-proof.json'))
 validate_proofs(fixed.load_json(base/'processes/hardening-proof.json'),fixed.load_json(base/'upgrade-rebuilt/upgrade-proof.json'),fixed.load_json(base/'shutdown/shutdown-proof.json'))
 suites=[]
 for folder,name in [('demo-boundary','DemoBoundary'),('processes','HardeningProcesses'),('upgrade','UpgradeProcesses'),('upgrade-rebuilt','UpgradeProcesses'),('shutdown','ShutdownClaim'),('build','CleanBuild'),('documents','DeliveryDocuments')]:
  path=base/folder/'junit'/('TEST-'+name+'.xml');counts=fixed.junit_counts(path)
  assert counts['tests']>0 and not any(counts[k] for k in ('failures','errors','skipped'))
  names={c.attrib['name'] for c in ET.parse(path).getroot().iter('testcase')};assert names==REQUIRED_CASES[name],(name,names)
  suites.append({'name':folder+'-'+name,**counts,'report':path.relative_to(base).as_posix()})
 bp=fixed.load_json(base/'build/build-proof.json');assert bp['sourceUnchanged'] and bp['inputs'] and len(bp['jarSha256'])==64 and not bp['testsRunHere']
 ip=fixed.load_json(base/'build/image-proof.json');assert '@sha256:' in ip['pinnedBase'] and '21.0.12' in ip['javaVersion']
 hp=fixed.load_json(base/'build/historical/provenance.json');assert hp['mode']=='PINNED_HISTORICAL_SOURCE_REBUILD' and hp['sourceFingerprint']=='437f8be7254c3d2685a87b33c5aaaab0191fdca5814ff7834dde2092bfa89fb5' and not hp['claimsExactAcceptedJar']
 return suites

def main():
 base=evidence_path(ROOT,sys.argv[1]);base.mkdir(parents=True,exist_ok=True)
 rc=subprocess.run(['bash','scripts/verify-phase.sh','M5',str(base/'m5')],cwd=ROOT).returncode
 if rc:return rc
 old=fixed.load_json(base/'m5/summary.json');result={'phase':'M6','source_fingerprint':os.environ['ROUTE_SOURCE_FINGERPRINT'],'production_authorized':False,'checks':[{**c,'evidence':'m5/'+c['evidence']} for c in old['checks']],'suites':[{**s,'report':'m5/'+s['report']} for s in old['suites']]}
 try:
  documents(base/'documents');demo_boundary(base/'demo-boundary');shutdown(base/'shutdown');upgrade(base/'upgrade');processes(base/'processes');build(base/'build');upgrade(base/'upgrade-rebuilt',base/'build/historical/provenance.json')
  result['suites']+=validate_reports(base)
  for n in range(51,59):result['checks'].append({'id':'AC-%03d'%n,'status':'PASS','evidence':'processes/hardening-proof.json' if n in (51,52,55,58) else 'shutdown/shutdown-proof.json' if n==53 else 'upgrade/upgrade-proof.json' if n==54 else 'build/build-proof.json' if n==56 else 'documents/document-proof.json'})
 except Exception:
  (base/'failure.log').write_text(traceback.format_exc())
  for n in range(51,59):result['checks'].append({'id':'AC-%03d'%n,'status':'FAIL','evidence':'failure.log'})
 fixed.atomic_json(base/'summary.json',result)
 try:fixed.validate_gate(result,base,fixed.load_json(ROOT/'ai-kit/requirements.json'),'M6',os.environ['ROUTE_SOURCE_FINGERPRINT'])
 except Exception as e:print('M6 FAILED:',e);return 1
 print('M6 cumulative executable gate passed; fresh review pending');return 0
if __name__=='__main__':sys.exit(main())
