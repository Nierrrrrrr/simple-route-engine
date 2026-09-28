"""Real loopback HTTP tests for the handoff helper's URL and redirect boundary."""
import http.server,json,os,pathlib,secrets,subprocess,sys,threading,traceback,xml.etree.ElementTree as ET
from gate_common import ROOT

def acceptance(base):
 base.mkdir(parents=True,exist_ok=False);suite=ET.Element('testsuite',name='DemoBoundary');seen=[];source=[];token=secrets.token_urlsafe(32);problem=None
 class Sink(http.server.BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_GET(self):
   seen.append({'path':self.path,'credentialReceived':self.headers.get('Authorization')=='Bearer '+token});data=b'{}';self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 class Redirect(http.server.BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_POST(self):
   source.append(self.path);self.send_response(302);self.send_header('Location','http://127.0.0.1:'+str(sink.server_port)+'/capture');self.send_header('Content-Length','0');self.end_headers()
 sink=http.server.ThreadingHTTPServer(('127.0.0.1',0),Sink);redirect=http.server.ThreadingHTTPServer(('127.0.0.1',0),Redirect)
 for server in [sink,redirect]:threading.Thread(target=server.serve_forever,daemon=True).start()
 def run(label,url):
  env=dict(os.environ,ROUTE_DEMO_BASE=url,ROUTE_DEMO_TOKEN=token);args=[sys.executable,'-B','scripts/publish-demo.py','examples/delivery/demo-1.json']
  (base/(label+'.command.json')).write_text(json.dumps(args))
  r=subprocess.run(args,cwd=ROOT,env=env,capture_output=True,text=True,timeout=20)
  assert token not in r.stdout+r.stderr
  (base/(label+'.log')).write_text(r.stdout+r.stderr);(base/(label+'.exit')).write_text(str(r.returncode));return r
 for name,label,url in [('AC052_demoHelperRejectsUserinfo','userinfo','http://127.0.0.1:80@localhost:'+str(redirect.server_port)),('AC052_demoHelperDoesNotForwardRedirectCredentials','redirect','http://127.0.0.1:'+str(redirect.server_port))]:
  c=ET.SubElement(suite,'testcase',classname='DemoBoundary',name=name)
  try:
   r=run(label,url);assert r.returncode!=0
   if label=='userinfo':assert 'Invalid local demo URL' in r.stderr and not source
   else:assert len(source)==1 and not seen,'Redirect target must receive no request or credential'
  except Exception as e:problem=e;ET.SubElement(c,'failure').text=traceback.format_exc()
 for server in [sink,redirect]:server.shutdown();server.server_close()
 (base/'junit').mkdir();ET.ElementTree(suite).write(base/'junit/TEST-DemoBoundary.xml',encoding='utf-8',xml_declaration=True)
 (base/'demo-boundary-proof.json').write_text(json.dumps({'redirectSourceRequests':len(source),'sinkRequests':seen,'syntheticCredentialOnly':True},indent=2)+'\n')
 if problem:raise problem
if __name__=='__main__':acceptance(pathlib.Path(sys.argv[1]).resolve())
