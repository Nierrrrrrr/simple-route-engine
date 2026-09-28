"""Real loopback HTTP tests of FINAL-only lifecycle; no DB or independent handoff claim."""
import http.client,json,pathlib,tempfile,time,unittest,urllib.error,urllib.request,uuid
from adapter_fixture import RemoteFixture
from final_async import FinalAsyncLifecycle,validate_lifecycle
from gate_common import ROOT

class FinalAsyncTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.evidence',prefix='final-async-test-');self.remote=RemoteFixture();self.driver=FinalAsyncLifecycle(self.remote,pathlib.Path(self.tmp.name)/'lifecycle.json');self.closed=False
 def tearDown(self):
  try:
   if not self.closed:self.driver.close()
  finally:self.remote.close();self.tmp.cleanup()
 def call(self,method,path,body=None,operation=None):
  req=urllib.request.Request('http://127.0.0.1:'+str(self.remote.server.server_port)+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Idempotency-Key':operation or 'unused','Content-Type':'application/json'})
  try:response=urllib.request.urlopen(req,timeout=3)
  except urllib.error.HTTPError as exc:response=exc
  with response:return response.status,json.load(response)
 def submit(self,ref):
  op=str(uuid.uuid4());status,body=self.call('POST','/'+ref,{'operationId':op,'direction':'FORWARD','operationGeneration':1,'input':{}},op);return op,status,body
 def close(self):
  result=self.driver.close();self.closed=True;return result
 def test_final_async_requires_waiting_poll_then_real_http_completion_and_terminal_observation(self):
  op,status,body=self.submit('async');self.assertEqual((status,body['status']),(202,'WAITING'))
  self.assertNotIn(op,self.remote.ready)
  self.assertEqual(self.call('GET','/async/'+op)[0],202)
  deadline=time.monotonic()+4
  while True:
   status,body=self.call('GET','/async/'+op)
   if status==200:break
   self.assertLess(time.monotonic(),deadline);time.sleep(.02)
  self.assertEqual(body['status'],'SUCCEEDED');self.assertEqual(self.remote.effects[op],1)
  self.assertEqual(validate_lifecycle(self.close(),self.remote.submits)['completed_async_operations'],1)
 def test_final_async_does_not_complete_unpolled_or_cancelled_operation(self):
  op,status,_=self.submit('async');time.sleep(.15);self.assertNotIn(op,self.remote.ready)
  self.assertEqual(self.call('DELETE','/async/'+op)[0],202)
  self.assertEqual(self.call('GET','/async/'+op)[1]['status'],'STOPPED')
  proof=self.close();self.assertFalse(any(e['path'].startswith('/complete/') for e in proof['events']))
  with self.assertRaises(AssertionError):validate_lifecycle(proof,self.remote.submits)
 def test_final_async_preserves_failure_unknown_and_malformed_http_behavior(self):
  _,status,body=self.submit('failure');self.assertEqual((status,body['status']),(500,'FAILED'))
  self.assertEqual(self.call('GET','/async/unknown')[0],404)
  req=urllib.request.Request('http://127.0.0.1:'+str(self.remote.server.server_port)+'/async',data=b'{malformed',headers={'Content-Type':'application/json'})
  with self.assertRaises(http.client.RemoteDisconnected):urllib.request.urlopen(req,timeout=3)
  proof=self.close();self.assertEqual(validate_lifecycle(proof,self.remote.submits)['completed_async_operations'],0)

if __name__=='__main__':unittest.main()
