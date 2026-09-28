"""Synthetic negative validator fixtures only; never fresh-agent or engine execution evidence."""
import copy,json,pathlib,tempfile,unittest,xml.etree.ElementTree as ET
from gate_common import ROOT
from final_evidence import validate_handoff
from final_handoff import sha
from final_gate import fault_matrix,FAULT_CASES
from final_java_baseline import load_java_baseline

class FinalEvidenceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.evidence',prefix='final-validator-only-');self.root=pathlib.Path(self.tmp.name);self.run='synthetic-validator-only';self.base=self.root/'.evidence/desktop'/self.run/'execution';self.base.mkdir(parents=True)
  self.fp='a'*64;self.java={'src/main/java/Synthetic.java':'b'*64};self.examples={};self.records=[]
  suite=ET.Element('testsuite',name='FreshHandoff',tests='6',failures='0',errors='0',skipped='0')
  for i in range(6):
   route='demo-validator-six' if i==0 else 'demo-delivery-'+str(i);config={'name':'DEMO synthetic validator only','definition':{'routeId':route,'version':1},'input':{}}
   self.write('config-'+str(i)+'.json',config)
   if i==0:
    self.write('authored-route.json',config);authored=self.base.parent/'authored.json';authored.write_bytes((self.base/'authored-route.json').read_bytes())
   else:self.examples['examples/delivery/demo-'+str(i)+'.json']=sha(self.base/('config-'+str(i)+'.json'))
   identity='synthetic-execution-'+str(i);accepted={'executionId':identity};terminal={'executionId':identity,'routeId':route,'state':'SUCCEEDED','permitHeld':False}
   trace=[{'method':method,'path':path,'status':status,'body':body} for method,path,status,body in [('POST','/routes',201,{}),('POST','/routes/'+route+'/versions',201,{}),('POST','/routes/'+route+'/versions/1/publish',200,{}),('POST','/executions',202,accepted),('GET','/executions/'+identity,200,terminal)]]
   self.write('api-'+str(i)+'.json',trace);self.write('publish-'+str(i)+'.command.json',['python3','-B','scripts/publish-demo.py',str(self.base/('config-'+str(i)+'.json'))])
   (self.base/('publish-'+str(i)+'.log')).write_text(json.dumps(accepted)+'\n'+json.dumps(terminal)+'\n');(self.base/('publish-'+str(i)+'.exit')).write_text('0\n')
   self.records.append({'route_id':route,'execution_id':identity,'config':'config-'+str(i)+'.json','config_sha256':sha(self.base/('config-'+str(i)+'.json')),'trace':'api-'+str(i)+'.json','stdout':'publish-'+str(i)+'.log','command':'publish-'+str(i)+'.command.json','exit':'publish-'+str(i)+'.exit','pid':123,'terminal':terminal})
   ET.SubElement(suite,'testcase',classname='FreshHandoff',name='AC061_publishExecute_'+route)
  (self.base/'junit').mkdir();ET.ElementTree(suite).write(self.base/'junit/TEST-FreshHandoff.xml')
  self.proof={'schema_version':1,'kind':'EXTERNAL_FRESH_HANDOFF_EXECUTION','run_id':self.run,'source_fingerprint':self.fp,'source_fingerprint_after':self.fp,'java_before':self.java.copy(),'java_after':self.java.copy(),'examples_before':self.examples.copy(),'examples_after':self.examples.copy(),'jar_sha256':'c'*64,'authored_config_source':authored.relative_to(self.root).as_posix(),'authored_config_sha256':sha(authored),'route6_id':'demo-validator-six','cases':self.records,'suite':{'report':'junit/TEST-FreshHandoff.xml','tests':6,'failures':0,'errors':0,'skipped':0},'cleanup_completed':True,'fixture':{'database':'re-m1-'+self.run+'-123','namespace':'re-m4-synthetic','run_id':self.run},'agent_freshness':'CONTROLLER_ATTESTATION_REQUIRED','build_tests_run':False,'async_lifecycle':'async-lifecycle.json','files':{}}
  self.write('async-lifecycle.json',{'policy':'HTTP_COMPLETE_ONLY_AFTER_WAITING_POLL','events':[],'errors':[]});(self.base/'fixture').mkdir();self.write('fixture/remote-proof.json',{'submits':[]})
  self.receipt={'schema_version':1,'role':'FRESH_ACCEPTANCE','agent_id':'synthetic-validator-not-real-agent','agent_call_number':47,'run_id':self.run,'source_fingerprint':self.fp,'proof_sha256':'','evidence_directory':self.base.relative_to(self.root).as_posix()};self.seal()
 def tearDown(self):self.tmp.cleanup()
 def write(self,name,data):(self.base/name).write_text(json.dumps(data)+'\n')
 def seal(self):
  self.proof['files']={p.relative_to(self.base).as_posix():sha(p) for p in self.base.rglob('*') if p.is_file() and p.name!='handoff-proof.json'};self.write('handoff-proof.json',self.proof);self.receipt['proof_sha256']=sha(self.base/'handoff-proof.json')
 def validate(self):return validate_handoff(self.base,self.receipt,self.fp,self.run,self.java,self.examples,46,root=self.root)
 def reject(self):
  with self.assertRaises((AssertionError,KeyError,FileNotFoundError,ValueError)):self.validate()
 def test_final_synthetic_valid_import_boundary(self):self.validate()
 def test_explicit_security_baseline_rejects_path_substitution_and_missing_file(self):
  statepath=self.root/'docs/implementation/STATE.json';statepath.parent.mkdir(parents=True)
  expected=f'.evidence/desktop/{self.run}/baseline/engine-java-security-repair-round3.json'
  state={'current_phase':'FINAL','run_id':self.run,'final_java_baseline':{'schema_version':1,'path':expected}}
  def save():statepath.write_text(json.dumps(state))
  save()
  with self.assertRaises(FileNotFoundError):load_java_baseline(self.run,self.root)
  baseline=self.root/expected;baseline.parent.mkdir();baseline.write_text(json.dumps(self.java))
  self.assertEqual(self.java,load_java_baseline(self.run,self.root))
  for bad in [expected.replace('security-repair-round3','security-repair-round2'),expected.replace('security-repair-round3','sha256'),expected.replace(self.run,'other-run'),expected.replace('/baseline/','/baseline/../baseline/'),'/tmp/arbitrary.json']:
   state['final_java_baseline']['path']=bad;save()
   with self.assertRaises(AssertionError):load_java_baseline(self.run,self.root)
  state['final_java_baseline']['path']=expected;save();baseline.unlink();baseline.symlink_to(statepath)
  with self.assertRaises(AssertionError):load_java_baseline(self.run,self.root)
 def test_final_empty_auxiliary_command_output_preserves_manifest_integrity(self):
  name='fixture/raw-16-readiness-healthcheck';self.write(name+'.command.json',['synthetic-validator-command']);(self.base/(name+'.exit')).write_text('0\n');(self.base/(name+'.log')).write_bytes(b'');self.seal();self.validate()
  (self.base/(name+'.log')).write_text('tampered');self.reject()
  (self.base/(name+'.log')).write_bytes(b'');(self.base/(name+'.exit')).unlink();self.seal();self.reject()
 def test_final_empty_required_artifacts_rejected_even_with_resealed_hashes(self):
  for name in ['authored-route.json','config-0.json','api-0.json','publish-0.log','publish-0.command.json','publish-0.exit','junit/TEST-FreshHandoff.xml','async-lifecycle.json','fixture/remote-proof.json']:
   path=self.base/name;original=path.read_bytes();path.write_bytes(b'');self.seal();self.reject();path.write_bytes(original)
  self.seal();self.validate()
 def test_final_missing_proof_rejected(self):(self.base/'handoff-proof.json').unlink();self.reject()
 def test_final_stale_source_and_run_rejected(self):
  for key in ['source_fingerprint','source_fingerprint_after','run_id']:
   old=self.proof[key];self.proof[key]='stale';self.seal();self.reject();self.proof[key]=old
 def test_final_missing_or_old_controller_identity_rejected(self):
  for key,value in [('agent_call_number',46),('agent_id',''),('role','BUILDER'),('proof_sha256','0'*64)]:
   old=self.receipt[key];self.receipt[key]=value;self.reject();self.receipt[key]=old
 def test_final_java_and_examples_change_rejected(self):
  for key in ['java_before','java_after','examples_before','examples_after']:
   old=self.proof[key];self.proof[key]={};self.seal();self.reject();self.proof[key]=old
 def test_final_five_original_regression_omission_rejected(self):self.proof['cases'].pop();self.seal();self.reject()
 def test_final_false_suite_counts_rejected(self):self.proof['suite']['tests']=7;self.seal();self.reject()
 def test_final_skipped_xml_and_declared_count_rejected(self):
  p=self.base/'junit/TEST-FreshHandoff.xml';original=p.read_bytes();xml=ET.parse(p);ET.SubElement(xml.getroot()[0],'skipped');xml.write(p);self.seal();self.reject()
  p.write_bytes(original);xml=ET.parse(p);xml.getroot().set('tests','99');xml.write(p);self.seal();self.reject()
 def test_final_artifact_tamper_and_extra_file_rejected(self):
  (self.base/'publish-0.log').write_text('tamper');self.reject()
 def test_final_path_escape_and_absolute_report_rejected(self):
  for path in ['../outside.xml','/tmp/outside.xml','junit\\outside.xml']:
   self.proof['suite']['report']=path;self.seal();self.reject()
 def test_final_report_case_name_and_api_status_rejected(self):
  p=self.base/'junit/TEST-FreshHandoff.xml';xml=ET.parse(p);xml.getroot()[0].set('name','not-executed');xml.write(p);self.seal();self.reject()
 def test_final_api_trace_failure_rejected(self):
  p=self.base/'api-0.json';t=json.loads(p.read_text());t[0]['status']=500;self.write('api-0.json',t);self.seal();self.reject()
 def test_final_nonterminal_output_rejected(self):self.proof['cases'][0]['terminal']['state']='RECONCILING';self.seal();self.reject()
 def test_final_missing_async_proof_and_builder_regression_rejected(self):
  value=self.proof.pop('async_lifecycle');self.seal();self.reject()
  self.proof['async_lifecycle']=value;self.proof['kind']='BUILDER_REGRESSION_NOT_ACCEPTANCE';self.seal();self.reject()
 def test_final_async_completion_without_waiting_poll_rejected(self):
  op='synthetic-async';self.write('fixture/remote-proof.json',{'submits':[{'ref':'async','operation':op}]})
  self.write('async-lifecycle.json',{'policy':'HTTP_COMPLETE_ONLY_AFTER_WAITING_POLL','errors':[],'events':[{'sequence':1,'method':'POST','path':'/async','status':202,'body':{'operationId':op,'status':'WAITING'}},{'sequence':2,'method':'GET','path':'/complete/'+op,'status':200,'body':{'completed':op}},{'sequence':3,'method':'GET','path':'/async/'+op,'status':200,'body':{'operationId':op,'status':'SUCCEEDED'}}]});self.seal();self.reject()
 def test_final_fault_matrix_missing_case_rejected(self):
  p=self.base/'fault.xml';suite=ET.Element('testsuite')
  for name in FAULT_CASES.values():ET.SubElement(suite,'testcase',name=name)
  ET.ElementTree(suite).write(p);summary={'suites':[{'report':'fault.xml'}]};fault_matrix(self.base,summary)
  suite.remove(suite[0]);ET.ElementTree(suite).write(p)
  with self.assertRaises(AssertionError):fault_matrix(self.base,summary)

if __name__=='__main__':unittest.main()
