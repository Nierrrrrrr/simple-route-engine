"""AC056 clean build in a new evidence-owned directory; cumulative gates run tests separately."""
import hashlib,json,os,pathlib,shutil,subprocess,xml.etree.ElementTree as ET
from gate_common import ROOT

def acceptance(base):
 base.mkdir(parents=True,exist_ok=False);work=base/'workspace';work.mkdir();inputs={}
 for name in ['pom.xml','mvnw','mvnw.cmd','.mvn','src']:
  source=ROOT/name;dest=work/name
  if source.is_dir():shutil.copytree(source,dest)
  else:shutil.copyfile(source,dest)
 for p in work.rglob('*'):
  if p.is_file():inputs[p.relative_to(work).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
 os.chmod(work/'mvnw',0o755)
 # Package is a reproducibility check only. Real acceptance tests run in the cumulative gate.
 args=['./mvnw','-B','-Dmaven.test.skip=true','package'];(base/'command.json').write_text(json.dumps(args))
 with (base/'build.log').open('w') as out:r=subprocess.run(args,cwd=work,env=dict(os.environ),stdout=out,stderr=subprocess.STDOUT)
 (base/'build.exit').write_text(str(r.returncode));suite=ET.Element('testsuite',name='CleanBuild');case=ET.SubElement(suite,'testcase',classname='CleanBuild',name='AC056_newWorkDirectoryBuild')
 if r.returncode:ET.SubElement(case,'failure').text='Actual Maven package failed'
 (base/'junit').mkdir();ET.ElementTree(suite).write(base/'junit/TEST-CleanBuild.xml',encoding='utf-8',xml_declaration=True)
 assert r.returncode==0
 jar=work/'target/route-engine-0.1.0.jar';assert jar.stat().st_size>10000000
 assert all(hashlib.sha256((work/name).read_bytes()).hexdigest()==value for name,value in inputs.items())
 (base/'build-proof.json').write_text(json.dumps({'inputs':inputs,'workdir':str(work),'sourceUnchanged':True,'jarSha256':hashlib.sha256(jar.read_bytes()).hexdigest(),'testsRunHere':False,'testsRequiredByCumulativeGate':True},indent=2)+'\n')

 import importlib.util
 def helper(name):
  spec=importlib.util.spec_from_file_location(name.replace('-','_'),ROOT/'scripts'/(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
 imageproof=helper('build-app-image').build(base/'image')
 (base/'image-proof.json').write_text(json.dumps(imageproof,indent=2))
 helper('build-m5-baseline').build(base/'historical')
