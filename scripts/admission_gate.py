#!/usr/bin/env python3
"""M2 real two-JVM admission and transport/crash faults. Only run-owned test data is modified."""
import concurrent.futures, http.server, json, os, pathlib, shutil, socket, subprocess, sys, threading, time, traceback, urllib.error, urllib.request, uuid
import xml.etree.ElementTree as ET
from foundation_gate import LocalFixture
from gate_common import ROOT, fixed, evidence_path

class AdmissionFixture(LocalFixture):
 def __init__(self,base):
  super().__init__(base);self.apps=[];self.responses=[];self.process_proofs=[]
 def start_process(self,label,scheduler=False):
  with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
  stream=(self.base/('jvm-'+label+'.log')).open('w')
  env=dict(self.env,ROUTE_PORT=str(port),ROUTE_SCHEDULER_ENABLED=str(scheduler).lower(),ROUTE_ENGINE_ENABLED="false")
  args=['bash','scripts/local-run.sh']
  (self.base/('jvm-'+label+'.command.json')).write_text(json.dumps(args)+'\n')
  process=subprocess.Popen(args,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
  app={'label':label,'port':port,'process':process,'stream':stream};self.apps.append(app)
  self.process_proofs.append({'label':label,'pid':process.pid,'scheduler':scheduler,'database':self.database_endpoints[-1]})
  deadline=time.monotonic()+90
  while time.monotonic()<deadline:
   assert process.poll() is None,'Application exited: '+label
   try:
    if self.api(app,'GET','/actuator/health')[0]==200:return app
   except (OSError,urllib.error.URLError):pass
   time.sleep(.25)
  raise AssertionError('App readiness timeout '+label)
 def kill(self,app):
  if app['process'].poll() is None:
   app['process'].kill();code=app['process'].wait(timeout=15)
   (self.base/('jvm-'+app['label']+'.exit')).write_text(str(code)+'\n');app['stream'].close()
 def api(self,app,method,path,body=None,key=None,expected=None,port=None):
  headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json','X-Request-ID':'process-admission-test'}
  if key is not None:headers['Idempotency-Key']=key
  request=urllib.request.Request('http://127.0.0.1:'+str(port or app['port'])+path,data=None if body is None else json.dumps(body).encode(),method=method,headers=headers)
  try:response=urllib.request.urlopen(request,timeout=45)
  except urllib.error.HTTPError as e:response=e
  with response:
   data=json.loads(response.read());status=response.status
   self.responses.append({'jvm':app['label'],'method':method,'path':path,'key':key,'status':status,'body':data,'admissionIdentity':response.headers.get('X-Admission-Request-ID')})
  if expected is not None:assert status==expected,(status,data)
  return status,data
 def request(self,p='CRITICAL',mode='NOW_OR_REJECT'):
  return {'routeId':'demo-process-admission','priority':p,'admissionMode':mode,'input':{}}
 def submit(self,app,p='CRITICAL',mode='NOW_OR_REJECT',key=None,status=202):
  return self.api(app,'POST','/executions',self.request(p,mode),key or str(uuid.uuid4()),status)[1]
 def configure(self,app,total=100,reserved=20,enabled=True):
  cap=self.api(app,'GET','/capacity',expected=200)[1]
  self.api(app,'PUT','/capacity/config',{'totalSlots':total,'criticalReserved':reserved,'highWeight':6,'normalWeight':3,'lowWeight':1,'admissionEnabled':enabled,'configVersion':cap['configVersion'],'reason':'isolated process acceptance'},expected=200)
 def close_fixture_holders(self):
  # No M2 external workers exist. This simulates safe completed test holders, never a production API.
  self.sql("START TRANSACTION; SELECT id FROM scheduler_pool WHERE id=1 FOR UPDATE; UPDATE executions SET permit_held=FALSE,state='SUCCEEDED',state_version=state_version+1 WHERE permit_held=TRUE; COMMIT;")
 def retire_fixture_queue(self):
  self.sql("START TRANSACTION; SELECT id FROM scheduler_pool WHERE id=1 FOR UPDATE; UPDATE admission_requests SET decision='WITHDRAWN' WHERE decision='QUEUED'; UPDATE executions SET state='CANCELLED' WHERE state='QUEUED'; COMMIT;")
 def wait_permit(self,execution):
  deadline=time.monotonic()+20
  while time.monotonic()<deadline:
   if self.sql("SELECT CONCAT(state,':',permit_held) FROM executions WHERE id='"+execution+"'")=='ADMITTED:1':return
   time.sleep(.2)
  raise AssertionError('Queue not admitted: '+execution)
 def cleanup(self):
  for app in self.apps:self.kill(app)
  (self.base/'http-responses.json').write_text(json.dumps(self.responses,indent=2)+'\n')
  (self.base/'independent-jvms.json').write_text(json.dumps(self.process_proofs,indent=2)+'\n')
  super().cleanup()

def process_acceptance(base):
 base.mkdir(parents=True,exist_ok=False);f=AdmissionFixture(base);suite=ET.Element('testsuite',name='AdmissionProcesses');problem=None
 def case(name,action):
  item=ET.SubElement(suite,'testcase',classname='AdmissionProcesses',name=name)
  try:action()
  except Exception:
   ET.SubElement(item,'failure').text=traceback.format_exc();raise
 try:
  f.start();a=f.start_process('a');b=f.start_process('b')
  assert a['process'].pid!=b['process'].pid
  f.api(a,'POST','/routes',{'routeId':'demo-process-admission','name':'DEMO admission processes'},expected=201)
  d={'routeId':'demo-process-admission','version':1,'dslVersion':'1','engineSemanticsVersion':'1','adapterContractVersion':'1','root':{'id':'root','type':'SEQUENCE','children':[]}}
  f.api(a,'POST','/routes/demo-process-admission/versions',{'definition':d},expected=201)
  f.api(a,'POST','/routes/demo-process-admission/versions/1/publish',{'stateVersion':0},expected=200)
  def race():
   for i in range(99):f.submit(a)
   barrier=threading.Barrier(201)
   def one(i):
    barrier.wait(timeout=30)
    return f.api(a if i%2==0 else b,'POST','/executions',f.request(),key='race-'+str(i))
   with concurrent.futures.ThreadPoolExecutor(max_workers=200) as executor:
    futures=[executor.submit(one,i) for i in range(200)];barrier.wait(timeout=30)
    results=[future.result(timeout=60) for future in futures]
   assert sum(status==202 for status,_ in results)==1
   assert sum(status==409 and data['code']=='ADMISSION_REJECTED' for status,data in results)==199
   assert f.sql("SELECT CONCAT(COUNT(*),':',COALESCE(SUM(priority<>'CRITICAL'),0)) FROM executions WHERE permit_held=TRUE")=='100:0'
   assert f.sql("SELECT COUNT(*) FROM admission_requests WHERE idempotency_key LIKE 'race-%'")=='200'
   (base/'two-jvm-race.json').write_text(json.dumps({'pids':[a['process'].pid,b['process'].pid],'barrier_participants':200,'requests_each_jvm':100,'statuses':[status for status,_ in results]},indent=2)+'\n')
  case('AC011_AC021_twoIndependentJvmsTwoHundredCompeteForFinalPermit',race)
  def duplicate():
   f.close_fixture_holders();barrier=threading.Barrier(41)
   def one(i):barrier.wait(timeout=20);return f.api(a if i%2==0 else b,'POST','/executions',f.request(),key='same-two-jvm')
   with concurrent.futures.ThreadPoolExecutor(max_workers=40) as executor:
    futures=[executor.submit(one,i) for i in range(40)];barrier.wait(timeout=20);results=[future.result(timeout=60) for future in futures]
   assert all(r==results[0] for r in results) and results[0][0]==202
   assert f.sql("SELECT COUNT(*) FROM admission_requests WHERE idempotency_key='same-two-jvm'")=='1'
   assert f.sql("SELECT COUNT(*) FROM executions WHERE permit_held=TRUE")=='1'
  case('AC018_sameIdentityAcrossIndependentJvms',duplicate)
  def restart():
   f.close_fixture_holders();f.configure(a,total=1,reserved=0)
   for i in range(6):f.submit(a,'HIGH');f.close_fixture_holders()
   assert f.sql('SELECT wrr_cursor FROM scheduler_pool')=='6'
   high=f.submit(a,'HIGH','QUEUE',key='restart-high');n1=f.submit(a,'NORMAL','QUEUE',key='restart-n1');n2=f.submit(a,'NORMAL','QUEUE',key='restart-n2')
   f.sql("UPDATE admission_requests SET enqueued_at='2026-01-01 00:00:00' WHERE decision='QUEUED'")
   f.kill(a);active=f.start_process('scheduler-before-crash',True);f.wait_permit(n1['executionId'])
   assert f.sql('SELECT wrr_cursor FROM scheduler_pool')=='7';assert f.api(b,'GET','/admission-requests/'+n1['admissionRequestId'],expected=200)[1]==n1
   assert f.submit(b,'NORMAL','QUEUE',key='restart-n1')==n1
   f.kill(active);f.close_fixture_holders();active=f.start_process('scheduler-after-crash',True);f.wait_permit(n2['executionId']);f.kill(active)
   assert f.sql('SELECT wrr_cursor FROM scheduler_pool')=='8'
   assert f.sql("SELECT CONCAT(state,':',permit_held) FROM executions WHERE id='"+high['executionId']+"'")=='QUEUED:0'
   f.retire_fixture_queue();f.close_fixture_holders()
  case('AC014_AC015_AC017_queueFifoAndWrrCursorSurviveKilledJvm',restart)
  def response_loss():
   f.configure(b,total=100,reserved=20);saved={};body=f.request();fixture=f
   class Drop(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
     self.rfile.read(int(self.headers['Content-Length']))
     saved['result']=fixture.api(b,'POST','/executions',body,key='response-lost',expected=202)
     self.close_connection=True
     self.connection.shutdown(socket.SHUT_RDWR);self.connection.close()
    def log_message(self,*args):pass
   server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Drop);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
   try:
    try:f.api(b,'POST','/executions',body,key='response-lost',port=server.server_address[1]);raise AssertionError('Proxy must drop response')
    except (OSError,urllib.error.URLError):pass
   finally:server.shutdown();server.server_close();thread.join(5)
   assert saved['result'][0]==202;original=saved['result'][1];f.kill(b)
   restarted=f.start_process('after-response-loss')
   assert f.api(restarted,'GET','/admission-requests?key=response-lost',expected=200)[1]==original
   assert f.submit(restarted,key='response-lost')==original
   assert f.sql("SELECT COUNT(*) FROM admission_requests WHERE idempotency_key='response-lost'")=='1'
   assert f.sql("SELECT COUNT(*) FROM executions WHERE id='"+original['executionId']+"' AND permit_held=TRUE")=='1'
   (base/'response-loss-proof.json').write_text(json.dumps({'http_proxy_dropped_after_upstream_commit':True,'killed_pid':b['process'].pid,'restart_pid':restarted['process'].pid,'original':original},indent=2)+'\n')
  case('AC018_commitResponseLostThenKillLookupAndReplayOriginalIdentity',response_loss)
  active=f.apps[-1]
  def deadlock():
   f.close_fixture_holders();f.sql('CREATE TABLE fixture_deadlock_weight(id INT PRIMARY KEY,n INT) ENGINE=InnoDB; INSERT INTO fixture_deadlock_weight SELECT seq,0 FROM seq_1_to_1000;')
   script='MYSQL_PWD="$MARIADB_PASSWORD" exec mariadb -u "$MARIADB_USER" "$MARIADB_DATABASE" -N --unbuffered'
   args=['docker','exec','-i',f.name,'sh','-c',script]
   (base/'deadlock.command.json').write_text(json.dumps(args)+'\n')
   lock=subprocess.Popen(args,cwd=ROOT,env=f.env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
   try:
    lock.stdin.write("SET innodb_lock_wait_timeout=10; START TRANSACTION; UPDATE fixture_deadlock_weight SET n=n+1; SELECT route_id FROM routes WHERE route_id='demo-process-admission' FOR UPDATE;\n");lock.stdin.flush()
    assert lock.stdout.readline().strip()=='demo-process-admission'
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
     response=executor.submit(f.api,active,'POST','/executions',f.request(),'real-deadlock')
     time.sleep(.5);assert not response.done(),'Admission did not wait for route lock'
     lock.stdin.write('SELECT id FROM scheduler_pool WHERE id=1 FOR UPDATE; COMMIT;\n');lock.stdin.flush()
     status,data=response.result(timeout=20);assert status==503 and data['code']=='DATABASE_UNAVAILABLE',(status,data)
    lock.stdin.close();output=lock.stdout.read();error=lock.stderr.read();code=lock.wait(timeout=15)
    (base/'deadlock.log').write_text(output+'\n'+error);(base/'deadlock.exit').write_text(str(code)+'\n');assert code==0
   finally:
    if lock.poll() is None:lock.kill();lock.wait(timeout=10)
   assert f.sql("SELECT COUNT(*) FROM admission_requests WHERE idempotency_key='real-deadlock'")=='0'
   f.submit(active,key='real-deadlock')
   assert f.sql("SELECT COUNT(*) FROM admission_requests WHERE idempotency_key='real-deadlock'")=='1'
  case('AC022_realMariaDbDeadlockVictimReturns503AndRetryDoesNotDuplicate',deadlock)
  def outage():
   before=f.sql("SELECT COUNT(*) FROM executions");identity=f.database_endpoints[-1]['container_id']
   f.command(['docker','stop','--time','5',f.name],'database-outage')
   status,data=f.api(active,'POST','/executions',f.request(),key='outage-key');assert status==503 and data['code']=='DATABASE_UNAVAILABLE';assert data['admissionRequestId']
   assert f.api(active,'GET','/capacity')[0]==503
   for app in f.apps:f.kill(app)
   f.command(['docker','start',f.name],'database-recover');f.wait_db();f.record_database_endpoint('outage-recovered')
   assert f.database_endpoints[-1]['container_id']==identity
   assert f.sql('SELECT COUNT(*) FROM executions')==before
   restarted=f.start_process('after-database-outage');result=f.submit(restarted,key='outage-key');assert result['admissionRequestId']==data['admissionRequestId']
   assert f.sql("SELECT COUNT(*) FROM admission_requests WHERE idempotency_key='outage-key'")=='1'
  case('AC022_databaseOutageNoCachedPermitAndOriginalIdentityRecoverable',outage)
 except Exception as e:problem=e;(base/'failure.log').write_text(traceback.format_exc())
 finally:
  try:f.cleanup()
  except Exception as e:problem=problem or e;(base/'cleanup-failure.log').write_text(traceback.format_exc())
  (base/'junit').mkdir(exist_ok=True);ET.ElementTree(suite).write(base/'junit/TEST-AdmissionProcesses.xml',encoding='utf-8',xml_declaration=True)
 if problem:raise problem
 return fixed.junit_counts(base/'junit/TEST-AdmissionProcesses.xml')

def validate_m2_reports(base):
 reports=[base/'m1/junit/TEST-dev.routeengine.AdmissionIT.xml',base/'processes/junit/TEST-AdmissionProcesses.xml'];names=[]
 for report in reports:
  counts=fixed.junit_counts(report);assert counts['tests']>0 and not any(counts[k] for k in ['failures','errors','skipped']),str(report)
  names += [c.attrib.get('name','') for c in ET.parse(report).getroot().iter('testcase')]
 for n in range(11,23):assert any(('AC%03d_'%n) in name for name in names),'Missing actual M2 testcase AC-%03d'%n
 proof=json.loads((base/'processes/two-jvm-race.json').read_text());assert len(set(proof['pids']))==2 and proof['barrier_participants']>=200

def main():
 base=evidence_path(ROOT,sys.argv[1]);base.mkdir(parents=True,exist_ok=True)
 rc=subprocess.run(['bash','scripts/verify-phase.sh','M1',str(base/'m1')],cwd=ROOT).returncode
 if rc:return rc
 previous=fixed.load_json(base/'m1/summary.json')
 summary={'phase':'M2','source_fingerprint':os.environ['ROUTE_SOURCE_FINGERPRINT'],'production_authorized':False,'checks':[{**c,'evidence':'m1/'+c['evidence']} for c in previous['checks']],'suites':[{**s,'report':'m1/'+s['report']} for s in previous['suites']]}
 try:
  counts=process_acceptance(base/'processes');validate_m2_reports(base)
  summary['suites'].append({'name':'AdmissionProcesses',**counts,'report':'processes/junit/TEST-AdmissionProcesses.xml'})
  for n in range(11,23):
   rid='AC-%03d'%n;proof=base/(rid+'.log');proof.write_text('Actual AdmissionIT assertions and AdmissionProcesses HTTP/database faults completed. See m1/junit/TEST-dev.routeengine.AdmissionIT.xml, processes/junit/TEST-AdmissionProcesses.xml, processes/http-responses.json, raw commands/log/exit, and independent-jvms.json.\n');summary['checks'].append({'id':rid,'status':'PASS','evidence':proof.name})
 except Exception:
  (base/'failure.log').write_text(traceback.format_exc())
  for n in range(11,23):summary['checks'].append({'id':'AC-%03d'%n,'status':'FAIL','evidence':'failure.log'})
 fixed.atomic_json(base/'summary.json',summary)
 try:fixed.validate_gate(summary,base,fixed.load_json(ROOT/'ai-kit/requirements.json'),'M2',os.environ['ROUTE_SOURCE_FINGERPRINT'])
 except Exception as e:print('M2 FAILED:',e);return 1
 print('M2 cumulative checks passed; fresh review pending');return 0
if __name__=='__main__':sys.exit(main())