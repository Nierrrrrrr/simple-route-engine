#!/usr/bin/env python3
"""Run a separately authored DEMO configuration; never author route6 or claim agent freshness."""
import hashlib,json,os,pathlib,shutil,subprocess,sys,traceback,xml.etree.ElementTree as ET
from gate_common import ROOT,fixed,evidence_path
from hardening_processes import HardeningFixture
from runner_image import prepare
from final_async import FinalAsyncLifecycle,validate_lifecycle
from final_java_baseline import load_java_baseline

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def java_hashes(root=ROOT):return {p.relative_to(root).as_posix():sha(p) for p in sorted((root/'src/main/java').rglob('*.java'))}
def example_hashes(root=ROOT):return {p.relative_to(root).as_posix():sha(p) for p in sorted((root/'examples/delivery').glob('demo-*.json'))}
def run(config,base,*,builder_regression=False):
 run_id=os.environ['ROUTE_RUN_ID'];run_root=ROOT/'.evidence/desktop'/run_id
 config=config.resolve();base=evidence_path(ROOT,base)
 assert config.is_relative_to(run_root) and config.is_file() and not config.is_symlink()
 assert base.is_relative_to(run_root) and not base.exists()
 definition=json.loads(config.read_text());route=definition['definition']['routeId']
 assert definition['name'].startswith('DEMO ') and route.startswith('demo-') and route not in {'demo-delivery-'+str(i) for i in range(1,6)}
 assert definition['definition']['version']==1
 fingerprint=fixed.source_fingerprint(ROOT);assert fingerprint==os.environ['ROUTE_SOURCE_FINGERPRINT']
 protected=fixed.protected_files(ROOT);java=java_hashes();examples=example_hashes()
 assert java==load_java_baseline(run_id)
 base.mkdir();shutil.copyfile(config,base/'authored-route.json')
 build=['./mvnw','-B','-Dmaven.test.skip=true','clean','package'];(base/'build.command.json').write_text(json.dumps(build)+'\n')
 with (base/'build.log').open('w') as stream:r=subprocess.run(build,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
 (base/'build.exit').write_text(str(r.returncode)+'\n');assert r.returncode==0
 jar=ROOT/'target/route-engine-0.1.0.jar';jar_hash=sha(jar)
 fixture_base=base/'fixture';fixture_base.mkdir();f=HardeningFixture(fixture_base)
 lifecycle=FinalAsyncLifecycle(f.remote,base/'async-lifecycle.json');async_proof=None
 suite=ET.Element('testsuite',name='FreshHandoff');records=[];error=None;cleaned=False
 try:
  f.start();image=prepare(f);f.setup_catalog(image)
  app=f.launch('fresh-handoff',extra={'ROUTE_ENGINE_ENABLED':'true','ROUTE_SCHEDULER_ENABLED':'true'})
  f.configure(app,enabled=True)
  for index,path in enumerate([base/'authored-route.json',*sorted((ROOT/'examples/delivery').glob('demo-*.json'))]):
   payload=json.loads(path.read_text());route_id=payload['definition']['routeId'];case=ET.SubElement(suite,'testcase',classname='FreshHandoff',name='AC061_publishExecute_'+route_id)
   try:
    local=base/('config-'+str(index)+'.json');shutil.copyfile(path,local)
    trace=base/('api-'+str(index)+'.json');output=base/('publish-'+str(index)+'.log');command=base/('publish-'+str(index)+'.command.json');exit_path=base/('publish-'+str(index)+'.exit')
    args=['python3','-B','scripts/publish-demo.py',str(local)];command.write_text(json.dumps(args)+'\n')
    env=dict(os.environ,ROUTE_DEMO_BASE='http://127.0.0.1:'+str(app['port']),ROUTE_DEMO_TOKEN=f.token,ROUTE_DEMO_TRACE=str(trace))
    with output.open('w') as stream:result=subprocess.run(args,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=210)
    exit_path.write_text(str(result.returncode)+'\n');assert result.returncode==0
    messages=[json.loads(line) for line in output.read_text().splitlines()];assert len(messages)==2
    accepted,terminal=messages;assert terminal['state']=='SUCCEEDED' and terminal['permitHeld'] is False
    execution=accepted['executionId'];assert f.status(execution)=='SUCCEEDED:0' and app['process'].poll() is None
    records.append({'route_id':route_id,'execution_id':execution,'config':local.name,'config_sha256':sha(local),'trace':trace.name,'stdout':output.name,'command':command.name,'exit':exit_path.name,'pid':app['process'].pid,'terminal':terminal})
   except Exception:ET.SubElement(case,'failure').text=traceback.format_exc();raise
 except Exception as exc:error=exc;(base/'failure.log').write_text(traceback.format_exc())
 finally:
  try:async_proof=lifecycle.close()
  except Exception as exc:error=error or exc;(base/'async-cleanup-failure.log').write_text(traceback.format_exc())
  try:f.cleanup();cleaned=True
  except Exception as exc:error=error or exc;(base/'cleanup-failure.log').write_text(traceback.format_exc())
  suite.set('tests',str(len(suite.findall('testcase'))));suite.set('failures',str(len(list(suite.iter('failure')))));suite.set('errors','0');suite.set('skipped','0')
  (base/'junit').mkdir();ET.ElementTree(suite).write(base/'junit/TEST-FreshHandoff.xml',encoding='utf-8',xml_declaration=True)
 if error:raise error
 fixed.check_protected(ROOT,protected)
 assert fixed.source_fingerprint(ROOT)==fingerprint and java_hashes()==java and example_hashes()==examples
 assert sha(jar)==jar_hash and len(records)==6 and cleaned
 validate_lifecycle(async_proof,f.remote.submits)
 proof={'schema_version':1,'kind':'BUILDER_REGRESSION_NOT_ACCEPTANCE' if builder_regression else 'EXTERNAL_FRESH_HANDOFF_EXECUTION','run_id':run_id,'source_fingerprint':fingerprint,'source_fingerprint_after':fixed.source_fingerprint(ROOT),'java_before':java,'java_after':java_hashes(),'examples_before':examples,'examples_after':example_hashes(),'jar_sha256':jar_hash,'authored_config_source':config.relative_to(ROOT).as_posix(),'authored_config_sha256':sha(config),'route6_id':route,'cases':records,'suite':{'report':'junit/TEST-FreshHandoff.xml',**fixed.junit_counts(base/'junit/TEST-FreshHandoff.xml')},'cleanup_completed':cleaned,'fixture':{'database':f.name,'namespace':f.namespace,'run_id':run_id},'agent_freshness':'NOT_FRESH_ACCEPTANCE' if builder_regression else 'CONTROLLER_ATTESTATION_REQUIRED','build_tests_run':False,'async_lifecycle':'async-lifecycle.json','files':{p.relative_to(base).as_posix():sha(p) for p in sorted(base.rglob('*')) if p.is_file()}}
 (base/'handoff-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
 print('Builder regression only; not independent AC061.' if builder_regression else 'Handoff execution recorded; controller must attest fresh agent identity. No FINAL acceptance claimed.')

if __name__=='__main__':
 assert len(sys.argv)==3 or len(sys.argv)==4 and sys.argv[3]=='--builder-regression','Usage: final_handoff.py AUTHORED_CONFIG NEW_EVIDENCE_DIR [--builder-regression]'
 run(pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]),builder_regression=len(sys.argv)==4)
