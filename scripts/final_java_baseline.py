"""Explicit security-repair baseline; controller creates it once after Builder freeze."""
import json,pathlib,re
from gate_common import ROOT

def load_java_baseline(run_id,root=ROOT):
 assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,49}',run_id)
 state=json.loads((root/'docs/implementation/STATE.json').read_text())
 assert state['current_phase']=='FINAL' and state['run_id']==run_id
 selected=state['final_java_baseline']
 expected=f'.evidence/desktop/{run_id}/baseline/engine-java-security-repair-round3.json'
 assert selected=={'schema_version':1,'path':expected},'Only the explicit round3 security repair baseline is allowed'
 path=root/expected
 assert not any(p.is_symlink() for p in [path,*path.parents]) and path.resolve().is_relative_to((root/'.evidence/desktop'/run_id/'baseline').resolve())
 data=json.loads(path.read_text());assert isinstance(data,dict) and data
 assert all(re.fullmatch(r'src/main/java/[A-Za-z0-9_./-]+\.java',k) and '..' not in pathlib.PurePosixPath(k).parts and re.fullmatch(r'[a-f0-9]{64}',v) for k,v in data.items())
 return data
