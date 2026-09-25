"""Run-owned real HTTP/MariaDB/kind/Runner fixtures. No mock external adapter."""
import http.server,json,threading,time,uuid,hashlib,os,pathlib,socket,subprocess,urllib.error,urllib.request,secrets
from engine_gate import EngineFixture
from gate_common import ROOT

class RemoteFixture:
 def __init__(self):
  self.operations={};self.submits=[];self.effects={};self.lock=threading.Lock();self.ready=set();self.redirects=0
  owner=self
  class Handler(http.server.BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def respond(self,code,body):
    data=json.dumps(body).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers()
    try:self.wfile.write(data)
    except (BrokenPipeError,ConnectionResetError):pass
   def do_POST(self):
    body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));op=body['operationId'];ref=self.path.strip('/')
    assert self.headers.get('Idempotency-Key')==op
    with owner.lock:
     owner.submits.append({'operation':op,'ref':ref,'direction':body['direction'],'generation':body['operationGeneration']})
     if op not in owner.operations or ref=='unsafe':owner.effects[op]=owner.effects.get(op,0)+1
     status='FAILED' if ref in ('failure','notify-fail') or ref in ('flaky','notify-flaky') and body['operationGeneration']==1 else 'WAITING' if ref in ('async','notify-async') else 'SUCCEEDED'
     owner.operations[op]={'operationId':op,'status':status,'output':{'value':'fixture-complete'},'retryable':ref in ('flaky','notify-flaky','notify-fail')}
    if ref in ('lost','unsafe'):
     self.close_connection=True;return
    if ref=='timeout':time.sleep(2)
    self.respond(202 if status=='WAITING' else 500 if status=='FAILED' else 200,owner.operations[op])
   def do_GET(self):
    if self.path=='/stats':self.respond(200,owner.snapshot());return
    if self.path.startswith('/complete/'):
     op=self.path.split('/')[-1];owner.ready.add(op);self.respond(200,{'completed':op});return
    parts=self.path.strip('/').split('/');op=parts[-1]
    with owner.lock:body=owner.operations.get(op)
    if body is None:self.respond(404,{'status':'UNKNOWN'});return
    if op in owner.ready:body=dict(body,status='SUCCEEDED')
    self.respond(202 if body['status']=='WAITING' else 200,body)
   def do_DELETE(self):
    op=self.path.strip('/').split('/')[-1]
    with owner.lock:
     if op in owner.operations:owner.operations[op]['status']='STOPPED'
    self.respond(202,{'operationId':op,'status':'WAITING'})
  self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def snapshot(self):
  with self.lock:return {'submits':list(self.submits),'effects':dict(self.effects),'operations':dict(self.operations)}
 def close(self):self.server.shutdown();self.server.server_close()

class AdapterFixture(EngineFixture):
 def __init__(self,base):
  super().__init__(base);self.remote=RemoteFixture();self.namespace='re-m4-'+uuid.uuid4().hex[:12];self.created_namespace=False;self.runner_secret=secrets.token_urlsafe(32);self.catalog=None
 def kube(self,*args):return self.command(['kubectl','--context','kind-'+os.environ['ROUTE_CLUSTER'],*args],'kubernetes')
 def create_manifest(self,name,body):
  path=self.base/(name+'.json');path.write_text(json.dumps(body)+'\n');return self.kube('create','-f',str(path))
 def setup_catalog(self,image=None):
  endpoints={}
  for ref in ('sync','async','lost','unsafe','timeout','failure','flaky','notify-ok','notify-fail','notify-flaky','notify-async'):
   endpoints[ref]={'baseUri':'http://127.0.0.1:'+str(self.remote.server.server_port)+'/'+ref,'allowedHost':'127.0.0.1','allowLoopbackHttp':True,'query':ref!='unsafe','cancel':ref!='unsafe','timeoutMillis':500,'maxResponseBytes':65536}
  cfg={'endpoints':endpoints}
  if image:
   labels={'route-engine.run-id':self.run,'route-engine.purpose':'adapter-test'}
   self.create_manifest('namespace',{'apiVersion':'v1','kind':'Namespace','metadata':{'name':self.namespace,'labels':labels}});self.created_namespace=True
   self.create_manifest('pvc',{'apiVersion':'v1','kind':'PersistentVolumeClaim','metadata':{'name':'artifacts','namespace':self.namespace,'labels':labels},'spec':{'accessModes':['ReadWriteOnce'],'resources':{'requests':{'storage':'1Gi'}}}})
   secret=self.secret_dir/'runner-secret';secret.write_text(self.runner_secret)
   self.kube('-n',self.namespace,'create','secret','generic','runner-fixture','--from-file=value='+str(secret))
   self.kube('-n',self.namespace,'label','secret','runner-fixture',*[k+'='+v for k,v in labels.items()])
   digest='sha256:'+hashlib.sha256((ROOT/'config/runner/playbooks/probe.yml').read_bytes()).hexdigest()
   common={'namespace':self.namespace,'runId':self.run,'image':image,'imagePullPolicy':'Never'}
   cfg['resources']={
    'deployment':dict(common,kind='DEPLOYMENT',progressDeadlineSeconds=20),
    'deployment-fail':dict(common,kind='DEPLOYMENT',image='docker.io/route-engine/missing@sha256:'+'0'*64,progressDeadlineSeconds=10),
    'job':dict(common,kind='JOB'),
    'runner':dict(common,kind='ANSIBLE',pvc='artifacts',playbook='probe',artifactDigest=digest,secretName='runner-fixture'),
    'runner-wait':dict(common,kind='ANSIBLE',pvc='artifacts',playbook='wait',artifactDigest='sha256:'+hashlib.sha256((ROOT/'config/runner/playbooks/wait.yml').read_bytes()).hexdigest()),
    'runner-fail':dict(common,kind='ANSIBLE',pvc='artifacts',playbook='fail',artifactDigest='sha256:'+hashlib.sha256((ROOT/'config/runner/playbooks/fail.yml').read_bytes()).hexdigest())
   }
   cfg['kubernetes']={'kubeconfig':os.environ['KUBECONFIG'],'context':'kind-'+os.environ['ROUTE_CLUSTER']}
  self.catalog=self.base/'adapter-catalog.json';self.catalog.write_text(json.dumps(cfg,indent=2)+'\n')
  self.env.update(ROUTE_ADAPTERS_CONFIG=str(self.catalog),ROUTE_ADAPTER_CATALOG=str(self.catalog),ROUTE_ADAPTER_NAMESPACE=self.namespace,ROUTE_HTTP_FIXTURE='http://127.0.0.1:'+str(self.remote.server.server_port),ROUTE_ADAPTER_EVIDENCE=str(self.base))
  return cfg
 def runner_canary(self,image):
  # Deliberately inject a test canary in inherited env. Production adapters never do this.
  # Runner must strip it before writing its command artifact; actual credential comes from a file.
  self.canary_operation=str(uuid.uuid4())
  self.create_manifest('runner-env-canary',{'apiVersion':'batch/v1','kind':'Job','metadata':{'name':'runner-env-canary','namespace':self.namespace,'labels':{'route-engine.run-id':self.run,'route-engine.purpose':'artifact-test'}},'spec':{'backoffLimit':0,'activeDeadlineSeconds':120,'template':{'metadata':{'labels':{'route-engine.run-id':self.run,'route-engine.purpose':'artifact-test'}},'spec':{'restartPolicy':'Never','automountServiceAccountToken':False,'securityContext':{'runAsNonRoot':True,'runAsUser':1000,'runAsGroup':1000,'fsGroup':1000},'containers':[{'name':'runner','image':image,'imagePullPolicy':'Never','securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}},'env':[{'name':'MODE','value':'runner'},{'name':'PLAYBOOK','value':'probe'},{'name':'OPERATION_ID','value':self.canary_operation},{'name':'RUNNER_TEST_SECRET','valueFrom':{'secretKeyRef':{'name':'runner-fixture','key':'value'}}}],'volumeMounts':[{'name':'tmp','mountPath':'/tmp'},{'name':'artifacts','mountPath':'/artifacts'},{'name':'credential','mountPath':'/run/route-secrets','readOnly':True}]}],'volumes':[{'name':'tmp','emptyDir':{}},{'name':'artifacts','persistentVolumeClaim':{'claimName':'artifacts'}},{'name':'credential','secret':{'secretName':'runner-fixture','defaultMode':288}}]}}}})
  self.kube('-n',self.namespace,'wait','--for=condition=complete','job/runner-env-canary','--timeout=120s')
 def start_adapter(self,label,pause='',scheduler='false',engine='true',after=''):
  with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
  stream=(self.base/('jvm-'+label+'.log')).open('w')
  env=dict(self.env,ROUTE_PORT=str(port),ROUTE_SCHEDULER_ENABLED=scheduler,ROUTE_ENGINE_ENABLED=engine,ROUTE_ENGINE_PAUSE_AFTER_NODE=after,ROUTE_ENGINE_LEASE_SECONDS='2',SPRING_PROFILES_ACTIVE='engine-development',ROUTE_ENGINE_FIXTURE_DIRECTORY=str(self.external),ROUTE_ENGINE_PAUSE_BEFORE_RESULT_NODE=pause)
  args=['bash','scripts/local-run.sh'];(self.base/('jvm-'+label+'.command.json')).write_text(json.dumps(args)+'\n')
  process=subprocess.Popen(args,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT);app={'label':label,'port':port,'process':process,'stream':stream};self.apps.append(app)
  self.process_proofs.append({'label':label,'pid':process.pid,'real_adapters':True,'database':self.database_endpoints[-1]})
  deadline=time.monotonic()+90
  while time.monotonic()<deadline:
   assert process.poll() is None,'Adapter app exited '+label
   try:
    if self.api(app,'GET','/actuator/health')[0]==200:return app
   except (OSError,urllib.error.URLError):pass
   time.sleep(.2)
  raise AssertionError('Adapter app readiness timeout')
 def cleanup(self):
  for a in self.apps:self.kill(a)
  (self.base/'remote-proof.json').write_text(json.dumps(self.remote.snapshot(),indent=2)+'\n');self.remote.close()
  if self.created_namespace:
   actual=json.loads(self.kube('get','namespace',self.namespace,'-o','json'))
   labels=actual['metadata']['labels'];assert labels.get('route-engine.run-id')==self.run and labels.get('route-engine.purpose')=='adapter-test'
   self.kube('delete','namespace',self.namespace,'--wait=true','--timeout=180s')
  super().cleanup()
