"""Build/load only the labelled test image and the explicitly owned kind node."""
import hashlib,json,os,re
from gate_common import ROOT
def prepare(f):
 run=os.environ['ROUTE_RUN_ID'];cluster=os.environ['ROUTE_CLUSTER'];tag='docker.io/route-engine/runner:'+run.lower()+'-m4'
 context=ROOT/'config/runner'
 files={p.relative_to(context).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(context.rglob('*')) if p.is_file()}
 (f.base/'runner-context.json').write_text(json.dumps(files,indent=2)+'\n')
 f.command(['docker','build','--label','route-engine.run-id='+run,'--label','route-engine.purpose=adapter-runner-test','-t',tag,str(context)],'runner-image-build')
 labels=json.loads(f.command(['docker','image','inspect',tag,'--format','{{json .Config.Labels}}'],'runner-image-owner'));assert labels['route-engine.run-id']==run and labels['route-engine.purpose']=='adapter-runner-test'
 nodes=f.command(['kind','get','nodes','--name',cluster],'kind-nodes').splitlines();assert nodes
 for node in nodes:
  labels=json.loads(f.command(['docker','inspect',node,'--format','{{json .Config.Labels}}'],'kind-node-owner'));assert labels['io.x-k8s.kind.cluster']==cluster
 f.command(['kind','load','docker-image',tag,'--name',cluster],'runner-image-load')
 refs=[]
 for node in nodes:
  inventory=f.command(['docker','exec',node,'ctr','--namespace','k8s.io','images','list'],'runner-image-inventory')
  matches=[line.split() for line in inventory.splitlines() if line.split() and line.split()[0]==tag];assert len(matches)==1
  digest=matches[0][2];assert re.fullmatch('sha256:[a-f0-9]{64}',digest)
  ref='docker.io/route-engine/runner@'+digest
  f.command(['docker','exec',node,'ctr','--namespace','k8s.io','images','tag','--force',tag,ref],'runner-digest-alias');refs.append(ref)
 assert len(set(refs))==1
 (f.base/'runner-image-ref.txt').write_text(refs[0]+'\n')
 # A read-only, offline ephemeral version probe; no application credential environment is supplied.
 versions=f.command(['docker','run','--rm','--network','none','--read-only','--label','route-engine.run-id='+run,'--label','route-engine.purpose=adapter-version-test','--entrypoint','python',tag,'-c','import sys,importlib.metadata as m; print(sys.version); print(m.version("ansible-runner")); print(m.version("ansible-core"))'],'runner-versions')
 assert '3.12.12' in versions and '2.4.1' in versions and '2.19.2' in versions
 return refs[0]
