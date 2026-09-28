#!/usr/bin/env python3
"""Publish/execute a versioned example against an explicitly supplied local fixture API."""
import json,os,pathlib,sys,time,urllib.request,urllib.parse,uuid
assert len(sys.argv)==2,'example file'
base=os.environ['ROUTE_DEMO_BASE']
try:
 parsed=urllib.parse.urlsplit(base)
 assert parsed.scheme=='http' and parsed.hostname=='127.0.0.1' and parsed.username is None and parsed.password is None
 assert parsed.port is not None and 1<=parsed.port<=65535 and parsed.path in ('','/') and not parsed.query and not parsed.fragment
except (ValueError,AssertionError):raise ValueError('Invalid local demo URL') from None
base=base.rstrip('/')
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):return None
opener=urllib.request.build_opener(NoRedirect())
token=os.environ['ROUTE_DEMO_TOKEN'];example=json.loads(pathlib.Path(sys.argv[1]).read_text());d=example['definition'];route=d['routeId']
trace=[]
def call(method,path,body=None):
 r=urllib.request.Request(base+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Idempotency-Key':str(uuid.uuid4())})
 with opener.open(r,timeout=30) as response:
  data=json.load(response)
  trace.append({'method':method,'path':path,'status':response.status,'body':data})
  if os.environ.get('ROUTE_DEMO_TRACE'):pathlib.Path(os.environ['ROUTE_DEMO_TRACE']).write_text(json.dumps(trace,indent=2)+'\n')
  return data
call('POST','/routes',{'routeId':route,'name':example['name']})
call('POST','/routes/'+route+'/versions',{'definition':d});call('POST','/routes/'+route+'/versions/'+str(d['version'])+'/publish',{'stateVersion':0})
result=call('POST','/executions',{'routeId':route,'priority':'NORMAL','admissionMode':'QUEUE','input':example['input']})
print(json.dumps(result));deadline=time.monotonic()+180
while time.monotonic()<deadline:
 status=call('GET','/executions/'+result['executionId'])
 if status['state']=='SUCCEEDED':print(json.dumps(status));break
 assert status['state'] not in ['MANUAL_WAIT','FAILED','CANCELLED','RECONCILING'],status
 time.sleep(.2)
else:raise TimeoutError('Execution did not succeed before local demo timeout')
