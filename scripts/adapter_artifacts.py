"""Actual PVC reads and content scans. Never write an unredacted failed secret scan to evidence."""
import json,subprocess,pathlib
from gate_common import ROOT

def capture_safe(f,args,label):
 path=f.base/label;path.with_suffix('.command.json').write_text(json.dumps(args)+'\n')
 result=subprocess.run(args,cwd=ROOT,env=f.env,capture_output=True,text=True,timeout=90)
 path.with_suffix('.exit').write_text(str(result.returncode)+'\n')
 combined=result.stdout+result.stderr
 if f.runner_secret in combined:
  path.with_suffix('.log').write_text('UNSAFE_CONTENT_REDACTED: fixture secret found\n')
  raise AssertionError('Fixture secret leaked in '+label)
 path.with_suffix('.log').write_text(combined)
 assert result.returncode==0,label+' failed'
 return result.stdout

def collect(f,require_success=True):
 cfg=json.loads(f.catalog.read_text());image=cfg['resources']['runner']['image'];reader='artifact-reader'
 f.create_manifest('artifact-reader',{'apiVersion':'v1','kind':'Pod','metadata':{'name':reader,'namespace':f.namespace,'labels':{'route-engine.run-id':f.run,'route-engine.purpose':'artifact-test'}},'spec':{'restartPolicy':'Never','automountServiceAccountToken':False,'securityContext':{'runAsNonRoot':True,'runAsUser':1000,'runAsGroup':1000,'fsGroup':1000},'containers':[{'name':'reader','image':image,'imagePullPolicy':'Never','command':['python','-c','import time; time.sleep(600)'],'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}},'volumeMounts':[{'name':'artifacts','mountPath':'/artifacts','readOnly':True}]}],'volumes':[{'name':'artifacts','persistentVolumeClaim':{'claimName':'artifacts'}}]}})
 f.kube('-n',f.namespace,'wait','--for=condition=Ready','pod/'+reader,'--timeout=60s')
 proof_path=f.base/'runner-artifact-reference.json';deleted=[]
 if proof_path.exists():
  proof=json.loads(proof_path.read_text());op=proof['operation']
  pods=json.loads(f.kube('-n',f.namespace,'get','pods','-l','route-engine.operation='+op,'-o','json'))['items'];assert pods
  for pod in pods:
   assert pod['metadata']['labels']['route-engine.run-id']==f.run and pod['status']['phase']=='Succeeded'
   assert pod['metadata']['ownerReferences'][0]['uid']==proof['uid']
   deleted.append(pod['metadata']['uid']);f.kube('-n',f.namespace,'delete','pod',pod['metadata']['name'],'--wait=true','--timeout=30s')
  assert not json.loads(f.kube('-n',f.namespace,'get','pods','-l','route-engine.operation='+op,'-o','json'))['items']
 program='import pathlib,json; p=pathlib.Path("/artifacts"); files=[x for x in p.rglob("*") if x.is_file()]; assert sum(x.stat().st_size for x in files)<16777216; print(json.dumps({str(x.relative_to(p)):x.read_text() for x in files}))'
 args=['kubectl','--context','kind-'+f.env['ROUTE_CLUSTER'],'-n',f.namespace,'exec',reader,'--','python','-c',program]
 artifacts=json.loads(capture_safe(f,args,'all-pvc-artifacts'))
 # Runner's command contains its effective environment. Keep and inspect it, never delete it.
 commands=[k for k in artifacts if k.endswith('/command')];assert commands,'Missing real Runner command artifacts'
 for key in commands:
  command=json.loads(artifacts[key]);assert 'env' in command
  assert 'RUNNER_TEST_SECRET' not in command['env']
  assert command['env']['HOME']=='/tmp/route-home'
 # Scan the original raw DB values without persisting a secret if the assertion detects one.
 sql="SELECT CONCAT_WS(' ',definition_json,definition_hash) FROM route_versions; SELECT CONCAT_WS(' ',node_json,input_json,output_json) FROM step_runs; SELECT CONCAT_WS(' ',adapter_plan,external_uid) FROM step_attempts; SELECT CONCAT_WS(' ',event_type,actor,reason) FROM execution_events; SELECT input_json FROM executions"
 capture_safe(f,f.sql_args(sql),'database-nonsecret-scan')
 for logfile in f.base.glob('*.log'):
  assert f.runner_secret not in logfile.read_text(errors='replace'),'Secret in log '+logfile.name
 if not require_success:
  (f.base/'failed-artifact-preservation.json').write_text(json.dumps({'files':len(artifacts),'commands':len(commands),'secretAbsent':True})+'\n');return
 assert proof_path.exists(),'Missing successful DB artifact reference'
 prefix=op+'/'
 assert artifacts[prefix+'rc'].strip()=='0';assert artifacts[prefix+'status'].strip()=='successful'
 assert 'route-engine-probe-complete' in artifacts[prefix+'stdout']
 events=[k for k in artifacts if k.startswith(prefix+'job_events/') and k.endswith('.json')];assert len(events)>=4
 canary=f.canary_operation
 assert artifacts[canary+'/rc'].strip()=='0' and artifacts[canary+'/status'].strip()=='successful'
 assert canary+'/command' in artifacts
 record={'canaryOperationId':canary,'canaryCommandSecretAbsent':True,'operation':op,'deletedPodUids':deleted,'readerPod':reader,'pvc':'artifacts','rc':0,'status':'successful','jobEvents':len(events),'commandsScanned':len(commands),'allArtifactFilesScanned':len(artifacts),'secretAbsent':True,'databaseAndLogSecretAbsent':True,'afterPodDeletion':True}
 (f.base/'artifact-survival-proof.json').write_text(json.dumps(record,indent=2)+'\n')
