import os,pathlib,tempfile,shutil,time,sys,json
# UID1000 + read-only root filesystem: all per-process state belongs on the /tmp emptyDir.
os.environ['HOME']='/tmp/route-home'
os.environ['ANSIBLE_HOME']='/tmp/route-home/.ansible'
os.environ['ANSIBLE_LOCAL_TEMP']='/tmp/route-home/.ansible/tmp'
pathlib.Path(os.environ['ANSIBLE_LOCAL_TEMP']).mkdir(parents=True,exist_ok=True)
mode=os.environ.get('MODE','runner')
if mode=='server':
 from http.server import HTTPServer,BaseHTTPRequestHandler
 class Handler(BaseHTTPRequestHandler):
  def do_GET(self):
   body=b'route-engine-controlled-fixture\n'
   self.send_response(200);self.send_header('Content-Type','text/plain');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
  def log_message(self,*args):pass
 HTTPServer(('0.0.0.0',8080),Handler).serve_forever()
elif mode=='wait':
 time.sleep(120)
else:
 import ansible_runner
 operation=os.environ['OPERATION_ID']
 assert len(operation)==36 and all(c in 'abcdef0123456789-' for c in operation)
 playbook=os.environ['PLAYBOOK'];assert playbook in ('probe','wait','fail')
 # Runner records its command environment on PVC. Never inherit secret values into it.
 os.environ.clear()
 os.environ.update(PATH='/usr/local/bin:/usr/bin:/bin',HOME='/tmp/route-home',ANSIBLE_HOME='/tmp/route-home/.ansible',ANSIBLE_LOCAL_TEMP='/tmp/route-home/.ansible/tmp',LANG='C.UTF-8',PYTHONDONTWRITEBYTECODE='1')
 private=pathlib.Path(tempfile.mkdtemp(prefix='route-runner-'))
 (private/'project').mkdir()
 shutil.copyfile('/opt/route/playbooks/'+playbook+'.yml',private/'project/playbook.yml')
 def event(event):
  # Minimal non-secret marker proves Ansible has entered the synchronous task on localhost.
  if event.get('event')=='runner_on_start' and event.get('event_data',{}).get('task')=='Bounded synchronous wait':
   path=pathlib.Path('/artifacts')/operation/'wait-started.json';path.parent.mkdir(parents=True,exist_ok=True)
   temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps({'operationId':operation,'event':'runner_on_start','task':'Bounded synchronous wait'}));temporary.replace(path)
  return True
 # No remote inventory, arbitrary playbooks or untracked async work.
 inventory={'all':{'hosts':{'localhost':{'ansible_connection':'local','ansible_python_interpreter':'/usr/local/bin/python'}}}}
 result=ansible_runner.run(private_data_dir=str(private),playbook='playbook.yml',inventory=inventory,artifact_dir='/artifacts',ident=operation,quiet=True,event_handler=event)
 sys.exit(result.rc if result.rc is not None else 99)
