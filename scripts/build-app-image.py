#!/usr/bin/env python3
"""Build the pinned app image from a self-contained, run-owned context. No registry push."""
import json,os,pathlib,shutil,subprocess,sys
from gate_common import ROOT,evidence_path

def build(base):
 base=evidence_path(ROOT,base);base.mkdir(parents=True,exist_ok=False);context=base/'context';context.mkdir()
 shutil.copytree(pathlib.Path(os.environ['JAVA_HOME']).resolve(),context/'java',symlinks=False)
 shutil.copyfile(ROOT/'target/route-engine-0.1.0.jar',context/'app.jar');shutil.copyfile(ROOT/'config/deployment/Dockerfile',context/'Dockerfile')
 tag='docker.io/route-engine/app:'+os.environ['ROUTE_RUN_ID'].lower()
 commands=[['docker','build','--label','route-engine.run-id='+os.environ['ROUTE_RUN_ID'],'--label','route-engine.purpose=m6-app-test','-t',tag,str(context)],['docker','run','--rm','--network','none','--read-only','--entrypoint','/opt/java/bin/java',tag,'-version']]
 for i,args in enumerate(commands):
  (base/f'image-{i}.command.json').write_text(json.dumps(args))
  with (base/f'image-{i}.log').open('w') as out:r=subprocess.run(args,cwd=ROOT,env=dict(os.environ),stdout=out,stderr=subprocess.STDOUT)
  (base/f'image-{i}.exit').write_text(str(r.returncode));assert r.returncode==0
 imageid=subprocess.check_output(['docker','image','inspect',tag,'--format','{{.Id}}'],text=True).strip();assert imageid.startswith('sha256:')
 proof={'tag':tag,'imageId':imageid,'pinnedBase':(ROOT/'config/deployment/Dockerfile').read_text().splitlines()[0],'javaVersion':(base/'image-1.log').read_text()}
 (base/'image-proof.json').write_text(json.dumps(proof,indent=2));return proof
if __name__=='__main__':build(pathlib.Path(sys.argv[1]).resolve())
