"""M6 actual HTTP, database, process, upgrade, backup and RBAC evidence."""
import hashlib,json,os,pathlib,socket,subprocess,time,traceback,urllib.request,urllib.error,uuid,xml.etree.ElementTree as ET
from adapter_fixture import AdapterFixture
from gate_common import ROOT

class HardeningFixture(AdapterFixture):
 def _initialize_database(self,args,deadline):
  # Docker Desktop's host may exclude ports that WSL can bind. Ask the actual
  # publisher to allocate a port without starting MariaDB or mounting DB data.
  # Transfer to an explicit DB mapping preserves the same JDBC URL on restart.
  # The transfer is not atomic: a collision still fails closed, without retry.
  assert not self.initialized and not self.created and not self.apps
  assert args.count('127.0.0.1::3306')==1
  probe=self.name+'-port';purpose='hardening-port-probe';code=-1
  image=(ROOT/'config/mariadb-image.txt').read_text().strip()
  try:
   code,_=self.command_result(['docker','run','--detach','--name',probe,'--label','route-engine.run-id='+self.run,'--label','route-engine.purpose='+purpose,'--tmpfs','/var/lib/mysql','-p','127.0.0.1::3306','--entrypoint','sleep',image,'120'],'port-probe-start',timeout=max(.001,deadline-time.monotonic()))
   assert code==0,'Docker port allocation failed; database not started'
   state=json.loads(self.command(['docker','inspect','--format','{{json .State}}',probe],'port-probe-state'))
   assert state['Running'] and state['Pid']>0
   endpoint=self.command(['docker','port',probe,'3306/tcp'],'port-probe-endpoint')
   host,port_text=endpoint.rsplit(':',1);port=int(port_text)
   assert host=='127.0.0.1' and 0<port<65536
  finally:
   found,owner=self.command_result(['docker','inspect','--format','{{json .Config.Labels}}',probe],'port-probe-owner',timeout=10)
   if found==0:
    labels=json.loads(owner)
    assert labels.get('route-engine.run-id')==self.run and labels.get('route-engine.purpose')==purpose,'Refuse cleanup of unowned port probe'
    self.command(['docker','rm','--force','--volumes',probe],'port-probe-cleanup')
   else:assert code!=0,'Lost successful port probe before ownership validation'
  self.fixed_database_port=port
  self.database_port_selection={'allocator':'Docker','endpoint':endpoint,'probe':probe,'databaseEntrypointUsed':False,'probeRemovedBeforeDatabase':True,'retryOnTransferFailure':False}
  (self.base/'database-port-selection.json').write_text(json.dumps(self.database_port_selection,indent=2)+'\n')
  return super()._initialize_database([('127.0.0.1:'+str(port)+':3306') if arg=='127.0.0.1::3306' else arg for arg in args],deadline)
 def launch(self,label,jar=None,extra=None):
  with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
  env=dict(self.env,ROUTE_PORT=str(port),ROUTE_ENGINE_ENABLED='false',ROUTE_SCHEDULER_ENABLED='false')
  if extra:env.update(extra)
  args=[os.environ['JAVA_HOME']+'/bin/java','-Duser.timezone=UTC','-jar',str(jar or ROOT/'target/route-engine-0.1.0.jar')]
  stream=(self.base/('jvm-'+label+'.log')).open('w');(self.base/('jvm-'+label+'.command.json')).write_text(json.dumps(args)+'\n')
  proc=subprocess.Popen(args,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
  app={'label':label,'port':port,'process':proc,'stream':stream};self.apps.append(app)
  self.wait(lambda: self.ready(app),'application '+label,90);return app
 def ready(self,app):
  assert app['process'].poll() is None,'Application exited: '+app['label']
  try:return self.api(app,'GET','/actuator/health')[0]==200
  except (OSError,urllib.error.URLError):return False
 def token_api(self,app,token,method,path,body=None):
  req=urllib.request.Request('http://127.0.0.1:'+str(app['port'])+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Idempotency-Key':str(uuid.uuid4())})
  try:r=urllib.request.urlopen(req,timeout=20)
  except urllib.error.HTTPError as e:r=e
  with r:return r.status,json.loads(r.read())

def acceptance(base,jar=None,image=None):
 base.mkdir(parents=True,exist_ok=False);f=HardeningFixture(base);suite=ET.Element('testsuite',name='HardeningProcesses');proof={};problem=None
 def case(name,fn):
  c=ET.SubElement(suite,'testcase',classname='HardeningProcesses',name=name)
  try:fn()
  except Exception:ET.SubElement(c,'failure').text=traceback.format_exc();raise
 try:
  f.start()
  proof['databasePortSelection']=f.database_port_selection
  assert f.database_endpoints[-1]['endpoint']==proof['databasePortSelection']['endpoint']
  if image is None and jar is None:
   from runner_image import prepare
   image=prepare(f)
  f.setup_catalog(image)
  def roles():
   caller=uuid.uuid4().hex;operator=uuid.uuid4().hex
   a=f.launch('roles',jar,{'ROUTE_CALLER_TOKEN_SHA256':hashlib.sha256(caller.encode()).hexdigest(),'ROUTE_OPERATOR_TOKEN_SHA256':hashlib.sha256(operator.encode()).hexdigest()})
   assert f.token_api(a,caller,'GET','/routes')[0]==200
   denied=[('POST','/routes'),('PUT','/capacity/config'),('POST','/executions/missing/recoveries'),('GET','/executions/missing/incidents'),('GET','/actuator/metrics')]
   for method,path in denied:assert f.token_api(a,caller,method,path,{})[0]==403,(method,path)
   assert f.token_api(a,operator,'POST','/routes',{})[0]==403
   assert f.token_api(a,operator,'PUT','/capacity/config',{})[0]==403
   assert f.token_api(a,operator,'GET','/actuator/metrics')[0]==200
   assert f.token_api(a,'wrong','GET','/routes')[0]==401
   route=f.publish(a,[])
   status,submitted=f.token_api(a,caller,'POST','/executions',{'routeId':route,'priority':'NORMAL','admissionMode':'QUEUE','input':{}});assert status==202
   id=submitted['executionId'];identity=submitted['admissionRequestId']
   assert f.token_api(a,caller,'GET','/executions/'+id)[0]==200
   assert f.token_api(a,operator,'GET','/executions/'+id)[0]==200
   assert f.token_api(a,operator,'GET','/admission-requests/'+identity)[0]==404
   assert f.token_api(a,caller,'GET','/admission-requests/'+identity)[0]==200
   assert f.token_api(a,operator,'POST','/executions/'+id+'/cancel',{'reason':'operator withdraws caller queue'})[0]==202
   proof['roles']={'callerDenied':len(denied),'operatorDenied':2,'wrongToken':401,'operationalRead':200,'foreignDecisionRead':404,'callerExecution':id,'operatorCancel':202}
   f.kill(a)
   startup=[]
   for label,patch in [('missing',{'ROUTE_ADMIN_TOKEN_SHA256':''}),('ambiguous',{'ROUTE_CALLER_TOKEN_SHA256':f.env['ROUTE_ADMIN_TOKEN_SHA256']})]:
    env=dict(f.env,ROUTE_PORT='0',ROUTE_ENGINE_ENABLED='false',ROUTE_SCHEDULER_ENABLED='false',**patch)
    args=[os.environ['JAVA_HOME']+'/bin/java','-jar',str(ROOT/'target/route-engine-0.1.0.jar')]
    (base/('auth-startup-'+label+'.command.json')).write_text(json.dumps(args))
    with (base/('auth-startup-'+label+'.log')).open('w') as out:r=subprocess.run(args,env=env,cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,timeout=90)
    (base/('auth-startup-'+label+'.exit')).write_text(str(r.returncode));assert r.returncode!=0
    log=(base/('auth-startup-'+label+'.log')).read_text();assert ('Configure authentication before starting' if label=='missing' else 'Invalid or ambiguous authentication configuration') in log
    startup.append({'case':label,'exit':r.returncode})
   proof['roles']['startupRejected']=startup
  case('AC051_actualRoleSeparation',roles)
  if jar:return proof
  def graceful():
   a=f.launch('graceful',extra={'ROUTE_ENGINE_ENABLED':'true','ROUTE_ENGINE_LEASE_SECONDS':'2'})
   id=f.execute(a,[{'id':'active','type':'REST','endpointRef':'async'},{'id':'after','type':'REST','endpointRef':'sync'}])
   f.wait(lambda:f.step(id,'active')=='WAITING_EXTERNAL','active external operation')
   op=f.operation(id,'active');a['process'].terminate();code=a['process'].wait(timeout=25);a['stream'].close()
   assert code==143,code
   assert f.status(id).endswith(':1') and not f.operation(id,'after')
   after=f.snapshot(id);assert after==f.snapshot(id)
   b=f.launch('overlap-a',extra={'ROUTE_ENGINE_ENABLED':'true','ROUTE_ENGINE_LEASE_SECONDS':'2'})
   c=f.launch('overlap-b',extra={'ROUTE_ENGINE_ENABLED':'true','ROUTE_ENGINE_LEASE_SECONDS':'2'})
   f.remote.ready.add(op);f.wait(lambda:f.status(id)=='SUCCEEDED:0','restart convergence')
   assert f.operation(id,'active')==op and f.remote.effects[op]==1
   assert sum(x['operation']==op for x in f.remote.submits)==1
   assert f.sql("SELECT permit_generation FROM executions WHERE id='"+id+"'")=='1'
   proof['graceful']={'exit':code,'oldPid':a['process'].pid,'overlapPids':[b['process'].pid,c['process'].pid],'operation':op,'submits':1,'effects':1,'permitGeneration':1,'afterExit':after}
   f.kill(b);f.kill(c)
  case('AC053_sigtermAndTwoOverlappingJvmRestart',graceful)
  def metrics():
   a=f.launch('metrics')
   route=f.publish(a,[])
   f.configure(a,total=2,reserved=1,enabled=True)
   held=[]
   for priority in ['NORMAL','CRITICAL']:
    held.append(f.api(a,'POST','/executions',{'routeId':route,'priority':priority,'admissionMode':'NOW_OR_REJECT','input':{}},str(uuid.uuid4()),202)[1]['executionId'])
   queued=f.api(a,'POST','/executions',{'routeId':route,'priority':'LOW','admissionMode':'QUEUE','input':{}},str(uuid.uuid4()),202)[1]['executionId']
   f.api(a,'POST','/executions',{'routeId':route,'priority':'NORMAL','admissionMode':'NOW_OR_REJECT','input':{}},str(uuid.uuid4()),409)

   expected={'route.queue.depth':"SELECT COUNT(*) FROM admission_requests WHERE decision='QUEUED'",'route.permits.total':"SELECT COUNT(*) FROM executions WHERE permit_held=TRUE",'route.permits.noncritical':"SELECT COUNT(*) FROM executions WHERE permit_held=TRUE AND priority<>'CRITICAL'"}
   assert int(f.sql(expected['route.queue.depth']))>=1 and int(f.sql(expected['route.permits.total']))==2 and int(f.sql(expected['route.permits.noncritical']))==1
   names=f.api(a,'GET','/actuator/metrics',expected=200)[1]['names']
   required=['route.queue.depth','route.permits.total','route.permits.noncritical','route.admission.rejected','route.retry.wait','route.in.doubt','route.stalled','route.lease.expired','route.reconcile.events','route.scheduler.lag.seconds']
   values={}
   for n in required:
    assert n in names
    value=f.api(a,'GET','/actuator/metrics/'+n,expected=200)[1]['measurements'][0]['value'];assert isinstance(value,(int,float)),n;values[n]=value
    if n in expected:assert value==int(f.sql(expected[n]))
   assert f.api(a,'GET','/actuator/health/readiness',expected=200)[1]['status']=='UP'
   originalEndpoint=f.database_endpoints[-1]['endpoint'];originalPid=a['process'].pid
   f.command(['docker','stop',f.name],'readiness-stop-db')
   assert f.api(a,'GET','/actuator/health/readiness')[0]==503
   f.command(['docker','start',f.name],'readiness-restart-db');f.wait_db();f.record_database_endpoint('metrics-restart')
   assert f.database_endpoints[-1]['endpoint']==originalEndpoint
   f.wait(lambda:f.api(a,'GET','/actuator/health/readiness')[0]==200,'same JVM readiness recovers after database restart',20)
   assert a['process'].pid==originalPid and a['process'].poll() is None
   f.kill(a)
   assert int(f.sql('SELECT COUNT(*) FROM execution_events'))>0
   proof['metrics']={'values':values,'readinessDbOutage':503,'readinessRecoveredSamePid':200,'restartSameEndpoint':True,'recoveredPid':originalPid,'endpoint':originalEndpoint,'auditRecords':int(f.sql('SELECT COUNT(*) FROM execution_events'))}
   converger=f.launch('metrics-converge',extra={'ROUTE_ENGINE_ENABLED':'true','ROUTE_SCHEDULER_ENABLED':'true'})
   for id in held+[queued]:f.wait(lambda:f.status(id)=='SUCCEEDED:0','metric fixture settles')
   f.configure(converger);f.kill(converger)
  case('AC055_metricsAuditAndDatabaseReadiness',metrics)
  def demos():
   assert image,'Genuine kind Runner image required'
   apps_before={app['process'].pid for app in f.apps}
   a=f.launch('demos',extra={'ROUTE_ENGINE_ENABLED':'true','ROUTE_SCHEDULER_ENABLED':'true'})
   f.configure(a,enabled=True)
   records=[]
   for path in sorted((ROOT/'examples/delivery').glob('demo-*.json')):
    d=json.loads(path.read_text());route=d['definition']['routeId']
    f.api(a,'POST','/routes',{'routeId':route,'name':d['name']},expected=201)
    f.api(a,'POST','/routes/'+route+'/versions',{'definition':d['definition']},expected=201)
    f.api(a,'POST','/routes/'+route+'/versions/1/publish',{'stateVersion':0},expected=200)
    id=f.api(a,'POST','/executions',{'routeId':route,'priority':'NORMAL','admissionMode':'QUEUE','input':d['input']},str(uuid.uuid4()),202)[1]['executionId']
    # AC058 is a happy-path delivery proof. Crash windows have dedicated suites.
    assert a['process'].poll() is None
    try:f.wait(lambda:f.status(id)=='SUCCEEDED:0','DEMO '+route,180)
    except Exception:
     # Preserve bounded identity/state diagnostics before owned-resource cleanup.
     diagnostic={'route':route,'execution':id,'pid':a['process'].pid,'exit':a['process'].poll()}
     for key,read in [('snapshot',lambda:f.snapshot(id)),('incidents',lambda:f.sql("SELECT kind,status,step_run_id,attempt_id,operation_id FROM engine_incidents WHERE execution_id='"+id+"'")),('kubernetes',lambda:f.kube('-n',f.namespace,'get','jobs,pods','-o','custom-columns=KIND:.kind,NAME:.metadata.name,UID:.metadata.uid,PHASE:.status.phase,SUCCEEDED:.status.succeeded'))]:
      try:diagnostic[key]=read()
      except Exception as error:diagnostic[key]={'diagnosticErrorType':type(error).__name__}
     (base/('demo-failure-'+route+'.json')).write_text(json.dumps(diagnostic,indent=2)+'\n')
     raise
    records.append({'route':route,'execution':id,'pid':a['process'].pid,'aliveAfterCompletion':a['process'].poll() is None,'snapshot':f.snapshot(id),'state':f.status(id),'definitionHash':f.sql("SELECT definition_hash FROM route_versions WHERE route_id='"+route+"' AND version=1")})
   assert len(records)==5;proof['demos']=records
   proof['demoKubernetes']=f.kube('-n',f.namespace,'get','jobs,deployments','-o','custom-columns=KIND:.kind,NAME:.metadata.name,UID:.metadata.uid,SUCCEEDED:.status.succeeded,AVAILABLE:.status.availableReplicas')
   proof['demoLifecycle']={'startedPids':[app['process'].pid for app in f.apps if app['process'].pid not in apps_before],'exitBeforeAllCompleted':a['process'].poll()}
   assert proof['demoLifecycle']['startedPids']==[a['process'].pid] and a['process'].poll() is None
   f.kill(a)
  case('AC058_fivePublishedRealAdapterDemos',demos)
  def rbac():
   ns=f.namespace;name='engine-restricted'
   f.create_manifest('sa',{'apiVersion':'v1','kind':'ServiceAccount','metadata':{'name':name,'namespace':ns}})
   # Exact production role template copied into this run-owned namespace.
   role=(ROOT/'config/kubernetes/adapter-role.yaml').read_text().replace('namespace: route-engine-work','namespace: '+ns)
   path=f.base/'runtime-role.yaml';path.write_text(role);f.kube('create','-f',str(path))
   f.create_manifest('binding',{'apiVersion':'rbac.authorization.k8s.io/v1','kind':'RoleBinding','metadata':{'name':name,'namespace':ns},'subjects':[{'kind':'ServiceAccount','name':name,'namespace':ns}],'roleRef':{'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':'route-engine-adapters'}})
   identity='system:serviceaccount:'+ns+':'+name;records=[]
   for verb,resource,namespace,allowed in [('create','jobs.batch',ns,True),('get','deployments.apps',ns,True),('get','secrets',ns,False),('create','pods/exec',ns,False),('create','jobs.batch','default',False)]:
    code,text=f.command_result(['kubectl','--context','kind-'+os.environ['ROUTE_CLUSTER'],'auth','can-i',verb,resource,'-n',namespace,'--as='+identity],'rbac-check')
    assert (code==0)==allowed and text==('yes' if allowed else 'no'),text
    records.append({'verb':verb,'resource':resource,'namespace':namespace,'allowed':allowed})
   # Exercise the API authorizer too: actual create/delete and actual forbidden reads.
   job={'apiVersion':'batch/v1','kind':'Job','metadata':{'name':'rbac-proof','namespace':ns,'labels':{'route-engine.run-id':f.run}},'spec':{'backoffLimit':0,'template':{'spec':{'restartPolicy':'Never','automountServiceAccountToken':False,'containers':[{'name':'probe','image':image,'imagePullPolicy':'Never','command':['python','-c','print(42)']}]}}}}
   file=f.base/'rbac-job.json';file.write_text(json.dumps(job))
   f.kube('--as='+identity,'create','-f',str(file));f.kube('--as='+identity,'get','job','rbac-proof','-n',ns)
   denied=[]
   for args in [['get','secret','runner-fixture','-n',ns],['get','job','anything','-n','default'],['create','--raw','/api/v1/namespaces/'+ns+'/pods/no-pod/exec','-f',str(file)]]:
    code,text=f.command_result(['kubectl','--context','kind-'+os.environ['ROUTE_CLUSTER'],'--as='+identity,*args],'rbac-real-denial')
    assert code!=0 and 'Forbidden' in text;denied.append({'args':args,'forbidden':True})
   f.kube('--as='+identity,'delete','job','rbac-proof','-n',ns,'--wait=true','--timeout=60s')
   proof['rbac']={'decisions':records,'actualCreateGetDelete':True,'actualDenied':denied}
  case('AC052_realNamespaceRoleAuthorization',rbac)
  def backup():
   from foundation_gate import LocalFixture
   otherbase=base/'restored';otherbase.mkdir();other=LocalFixture(otherbase)
   try:
    other.start();assert other.name!=f.name
    script='MYSQL_PWD="$MARIADB_PASSWORD" exec mariadb-dump -u "$MARIADB_USER" --single-transaction --skip-comments "$MARIADB_DATABASE"'
    dump=f.command(['docker','exec',f.name,'sh','-c',script],'backup-dump');dumpfile=base/'backup.sql';dumpfile.write_text(dump+'\n')
    args=['docker','exec','-i',other.name,'sh','-c','MYSQL_PWD="$MARIADB_PASSWORD" exec mariadb -u "$MARIADB_USER" "$MARIADB_DATABASE"']
    (base/'restore.command.json').write_text(json.dumps(args))
    with dumpfile.open('rb') as inp,(base/'restore.log').open('w') as out:r=subprocess.run(args,stdin=inp,stdout=out,stderr=subprocess.STDOUT)
    (base/'restore.exit').write_text(str(r.returncode));assert r.returncode==0
    queries=['SELECT COUNT(*) FROM executions','SELECT COUNT(*) FROM execution_events','SELECT GROUP_CONCAT(definition_hash ORDER BY route_id,version) FROM route_versions',"SELECT GROUP_CONCAT(CONCAT(id,':',state,':',permit_held) ORDER BY id) FROM executions"]
    comparisons=[]
    for q in queries:
     before=f.sql(q);after=other.sql(q);assert before==after;comparisons.append({'query':q,'source':before,'restored':after})
    proof['backup']={'source':f.name,'restored':other.name,'comparisons':comparisons,'dumpSha256':hashlib.sha256(dumpfile.read_bytes()).hexdigest()}
   finally:other.cleanup()
  case('AC055_isolatedBackupAndRestore',backup)
 except Exception as e:problem=e;(base/'failure.log').write_text(traceback.format_exc())
 finally:
  (base/'junit').mkdir(exist_ok=True);ET.ElementTree(suite).write(base/'junit/TEST-HardeningProcesses.xml',encoding='utf-8',xml_declaration=True)
  (base/'hardening-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
  f.cleanup()
 if problem:raise problem
 return proof
if __name__=='__main__':
 import sys
 acceptance(pathlib.Path(sys.argv[1]).resolve(),pathlib.Path(sys.argv[2]).resolve() if len(sys.argv)>2 else None)
