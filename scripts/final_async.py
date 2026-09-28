"""FINAL-only fixture completion after an actual engine WAITING poll; shared crash fixtures stay manual."""
import copy,json,pathlib,queue,threading,time,urllib.request

POLICY='HTTP_COMPLETE_ONLY_AFTER_WAITING_POLL'
ASYNC={'async','notify-async'}

def validate_lifecycle(proof,submits):
 assert set(proof)=={'policy','events','errors'} and proof['policy']==POLICY and proof['errors']==[]
 events=proof['events'];assert [e['sequence'] for e in events]==list(range(1,len(events)+1))
 expected={s['operation'] for s in submits if s['ref'] in ASYNC}
 posts=[e for e in events if e['method']=='POST' and e['path'].strip('/') in ASYNC]
 assert {e['body']['operationId'] for e in posts}==expected
 completions=[e for e in events if e['method']=='GET' and e['path'].startswith('/complete/')]
 assert len(completions)==len(expected) and {e['path'].rsplit('/',1)[1] for e in completions}==expected
 for op in expected:
  accepted=[e for e in posts if e['body']['operationId']==op];assert len(accepted)==1
  start=accepted[0];assert start['status']==202 and start['body']['status']=='WAITING'
  path=start['path']+'/'+op
  waiting=[e for e in events if e['method']=='GET' and e['path']==path and e['status']==202 and e['body'].get('operationId')==op and e['body'].get('status')=='WAITING'];assert waiting
  complete=next(e for e in completions if e['path']=='/complete/'+op);assert complete['status']==200 and complete['body']=={'completed':op}
  terminal=[e for e in events if e['method']=='GET' and e['path']==path and e['status']==200 and e['body'].get('operationId')==op and e['body'].get('status')=='SUCCEEDED'];assert terminal
  assert start['sequence']<waiting[0]['sequence']<complete['sequence']<terminal[-1]['sequence']
 return {'completed_async_operations':len(expected),'policy':POLICY}

class FinalAsyncLifecycle:
 def __init__(self,remote,path):
  self.remote=remote;self.path=path;self.lock=threading.RLock();self.events=[];self.errors=[];self.queued=set();self.pending=queue.Queue();self.stop=threading.Event();self.original=remote.server.RequestHandlerClass
  controller=self
  class ObservedHandler(self.original):
   def do_GET(self):
    with controller.lock:super().do_GET()
   def do_POST(self):
    with controller.lock:super().do_POST()
   def do_DELETE(self):
    with controller.lock:super().do_DELETE()
   def respond(self,code,body):
    super().respond(code,body)
    with controller.lock:
     controller.events.append({'sequence':len(controller.events)+1,'method':self.command,'path':self.path,'status':code,'body':copy.deepcopy(body)})
     parts=self.path.strip('/').split('/')
     if self.command=='GET' and len(parts)==2 and parts[0] in ASYNC and code==202 and body.get('operationId')==parts[1] and body.get('status')=='WAITING' and parts[1] not in controller.queued:
      controller.queued.add(parts[1]);controller.pending.put(parts[1])
  remote.server.RequestHandlerClass=ObservedHandler
  self.worker=threading.Thread(target=self.drive,name='final-async-completion',daemon=True);self.worker.start()
 def drive(self):
  while not self.stop.is_set():
   try:operation=self.pending.get(timeout=.1)
   except queue.Empty:continue
   try:
    url='http://127.0.0.1:'+str(self.remote.server.server_port)+'/complete/'+operation
    with urllib.request.urlopen(url,timeout=5) as response:
     assert response.status==200 and json.load(response)=={'completed':operation}
   except Exception as exc:
    with self.lock:self.errors.append(type(exc).__name__+': '+str(exc))
   finally:self.pending.task_done()
 def close(self):
  self.stop.set();self.worker.join(timeout=6);assert not self.worker.is_alive(),'Completion driver did not stop'
  self.remote.server.RequestHandlerClass=self.original
  with self.lock:proof={'policy':POLICY,'events':copy.deepcopy(self.events),'errors':list(self.errors)}
  self.path.write_text(json.dumps(proof,indent=2)+'\n')
  assert self.pending.unfinished_tasks==0 and not self.errors,'Incomplete or failed HTTP completion driver'
  return proof
