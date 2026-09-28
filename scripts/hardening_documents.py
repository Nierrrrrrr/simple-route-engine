"""Executable delivery inventory and consistency checks; not independent review."""
import hashlib,json,re,traceback,xml.etree.ElementTree as ET
from gate_common import ROOT
from m0_validate import validate_documents
DOCS=['README.md','docs/architecture/OVERVIEW.md','docs/architecture/STATE_MACHINES.md','docs/architecture/TRANSACTIONS.md','docs/architecture/FAILURE_RECOVERY.md','docs/api/openapi.yaml','docs/routes/DSL_REFERENCE.md','docs/agent/HANDOFF.md','docs/agent/ADD_ROUTE.md','docs/agent/CHANGE_ROUTE.md','docs/agent/ADD_ADAPTER.md','docs/agent/CHANGE_ENGINE.md','docs/agent/TESTING.md','docs/agent/PROMPT_TEMPLATES.md','docs/operations/RUNBOOK.md','docs/operations/SECURITY.md','docs/operations/DEPLOYMENT.md','docs/operations/EXTERNAL_INTEGRATION_CHECKLIST.md']
def validate(root):
 validate_documents(root)
 for name in DOCS:
  p=root/name;assert p.is_file() and p.stat().st_size>200,name
  assert not re.search(r'\b(TBD|TODO)\b',p.read_text()),name
 for path,symbol in [('api/RequestSecurityFilter.java','allowed'),('engine/ClaimLifecycle.java','stopping'),('operations/EngineMetrics.java','route.permits.total'),('engine/OperationAdapter.java','observe'),('adapters/AdapterBindings.java','binding')]:
  text=(root/'src/main/java/dev/routeengine'/path).read_text();assert symbol in text
 for name in ['hardening_gate.py','hardening_processes.py','hardening_upgrade.py','hardening_shutdown.py','hardening_build.py','build-m5-baseline.py','publish-demo.py','render-deployment.py','ci.sh']:
  assert (root/'scripts'/name).is_file(),name
 api=json.loads((root/'docs/api/openapi.yaml').read_text());assert all('x-roles' in op for p in api['paths'].values() for method,op in p.items() if method in ['get','post','put','patch','delete'])
 deploy=json.loads((root/'config/deployment/app.template.json').read_text());assert deploy['spec']['replicas']==1 and deploy['spec']['strategy']['type']=='Recreate'
 assert '@sha256:' in (root/'config/deployment/Dockerfile').read_text().splitlines()[0]
 assert 'eol=lf' in (root/'.gitattributes').read_text()
 return {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in DOCS}
def demos(root):
 files=sorted((root/'examples/delivery').glob('demo-*.json'));assert len(files)==5
 types=set()
 def walk(n):
  if isinstance(n,dict):
   if 'type' in n:types.add(n['type'])
   for v in n.values():walk(v)
  elif isinstance(n,list):
   for v in n:walk(v)
 for i,p in enumerate(files,1):
  d=json.loads(p.read_text());assert d['name'].startswith('DEMO ') and d['definition']['routeId']=='demo-delivery-'+str(i)
  assert d['definition']['version']==1;walk(d['definition']['root'])
 assert {'REST','CONDITION','PARALLEL','ANSIBLE','KUBERNETES'}<=types
 scope=(root/'docs/operations/EXTERNAL_INTEGRATION_CHECKLIST.md').read_text();assert 'EXTERNAL_ACCEPTANCE=NOT_RUN' in scope and 'PRODUCTION_DEPLOYMENT=NOT_AUTHORIZED' in scope
 return [p.relative_to(root).as_posix() for p in files]
def delivery_scope(root, overrides=None):
 """Cross-check current operational claims against executable repository inputs."""
 overrides=overrides or {}
 def read(name):return overrides.get(name,(root/name).read_text())
 state=json.loads(read('docs/implementation/STATE.json'));phase=state['current_phase']
 dispatcher=read('scripts/verify-phase.sh')
 implemented=re.findall(r'^ (M[0-9]+|FINAL)\) exec ',dispatcher,re.M)
 deferred=re.findall(r'^ (FINAL)\) echo "NOT_IMPLEMENTED',dispatcher,re.M)
 expected={'Candidate phase':phase,'Accepted phases':', '.join(state['completed_phases']),'Executable gates':', '.join(implemented),'Deferred gates':', '.join(deferred) or 'None','Delivery examples':str(len(list((root/'examples/delivery').glob('demo-*.json'))))}
 for name in ['README.md','docs/agent/TESTING.md']:
  text=read(name)
  command=re.search(r'bash scripts/verify-desktop-phase\.sh (M[0-9]+|FINAL) (\S+)',text)
  assert command and command[1]==phase,(name,'default gate differs from current phase')
  assert '/'+phase+'/' in command[2],(name,'evidence phase differs from command')
  headline=re.search(r'Current delivery[^\n]*?\b(M[0-9]+|FINAL)\b',text)
  if headline:assert headline[1]==phase,(name,'current delivery differs from STATE')
  rows=dict(re.findall(r'^\| ([^|]+?) \| ([^|]+?) \|$',text,re.M))
  for key,value in expected.items():assert rows.get(key)==value,(name,key,rows.get(key),value)
  # Current negative availability claims must not deny executable dispatch arms.
  current=text.split('## Historical evidence notes')[0]
  for sentence in re.split(r'(?<=[.!])\s+|\n\n',current):
   if 'NOT_IMPLEMENTED' in sentence:
    named=set(re.findall(r'\b(?:M[0-9]+|FINAL)\b',sentence))
    assert not named.intersection(implemented),(name,'implemented gate declared unavailable',sentence)
  assert not re.search(r'five[^.]*future work',current,re.I),(name,'existing delivery examples called future work')
 for name in ['docs/agent/CHANGE_ROUTE.md','docs/agent/ADD_ADAPTER.md']:
  text=read(name)
  assert not re.search(r'future[^.;\n]*(?:M5|resol)|M4 (?:candidate implementations|adapters are candidates)',text,re.I),(name,'implemented API/adapter declared pending')
 if phase=='FINAL':
  for name in ['docs/architecture/OVERVIEW.md','docs/agent/CHANGE_ROUTE.md','docs/agent/HANDOFF.md','docs/agent/TESTING.md']:
   text=read(name).split('## Historical evidence notes')[0]
   assert 'FINAL is outside the requested run' not in text and 'current M6 hardening awaits' not in text,(name,'stale phase scope')
   assert 'handoff-controller-receipt.json' not in text,(name,'stale receipt filename')
  for name in ['docs/agent/HANDOFF.md','docs/agent/TESTING.md']:
   assert '/FINAL/round-3/fresh-handoff-receipt.json' in read(name),(name,'missing current controller receipt')
 api=json.loads(read('docs/api/openapi.yaml'))
 assert 'post' in api['paths']['/executions/{id}/incidents/{incidentId}/resolve']
 assert 'POST /executions/{id}/incidents/{incidentId}/resolve' in read('docs/agent/CHANGE_ROUTE.md')
 return {'phase':phase,'implemented':implemented,'deferred':deferred,'examples':int(expected['Delivery examples']),'defaultGateDocuments':['README.md','docs/agent/TESTING.md']}

def delivery_scope_negatives(root):
 phase=json.loads((root/'docs/implementation/STATE.json').read_text())['current_phase']
 cases=[('README.md',lambda s:s.replace('verify-desktop-phase.sh '+phase,'verify-desktop-phase.sh M4',1)),('docs/agent/TESTING.md',lambda s:re.sub(r'\| Executable gates \|[^\n]+','| Executable gates | M0, M1, M2, M3 |',s)),('README.md',lambda s:s+'\nThe five delivery DEMOs remain future work.\n'),('docs/agent/CHANGE_ROUTE.md',lambda s:s.replace('available audited resolution','future audited M5 resolution')),('README.md',lambda s:s.replace('Current delivery is **'+phase,'Current delivery is **M4')),('docs/agent/TESTING.md',lambda s:s+'\n'+phase+' remains NOT_IMPLEMENTED and must return nonzero.\n'),('docs/agent/ADD_ADAPTER.md',lambda s:s.replace('Implemented adapters (','M4 candidate implementations ('))]
 if phase=='FINAL':cases.extend([('docs/architecture/OVERVIEW.md',lambda s:'FINAL is outside the requested run.\n'+s),('docs/agent/CHANGE_ROUTE.md',lambda s:'current M6 hardening awaits its gate.\n'+s),('docs/agent/HANDOFF.md',lambda s:s.replace('fresh-handoff-receipt.json','handoff-controller-receipt.json')),('docs/agent/TESTING.md',lambda s:s.replace('fresh-handoff-receipt.json','handoff-controller-receipt.json'))])
 rejected=[]
 for name,mutate in cases:
  old=(root/name).read_text();changed=mutate(old);assert changed!=old
  try:delivery_scope(root,{name:changed})
  except AssertionError:rejected.append(name)
  else:raise AssertionError('Stale delivery claim was accepted: '+name)
 return {'rejectedMutations':rejected}

def acceptance(base):
 base.mkdir(parents=True,exist_ok=False);suite=ET.Element('testsuite',name='DeliveryDocuments');proof={};error=None
 for name,fn in [('AC057_completeDocumentsAndActualSymbols',lambda:validate(ROOT)),('AC058_fiveDemoSchemaAndExternalScope',lambda:demos(ROOT)),('AC057_currentDeliveryMatchesExecutableRepository',lambda:delivery_scope(ROOT)),('AC057_rejectStaleDeliveryClaims',lambda:delivery_scope_negatives(ROOT))]:
  case=ET.SubElement(suite,'testcase',classname='DeliveryDocuments',name=name)
  try:proof[name]=fn()
  except Exception as e:ET.SubElement(case,'failure').text=traceback.format_exc();error=e
 (base/'junit').mkdir();ET.ElementTree(suite).write(base/'junit/TEST-DeliveryDocuments.xml',encoding='utf-8',xml_declaration=True)
 (base/'document-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
 if error:raise error
