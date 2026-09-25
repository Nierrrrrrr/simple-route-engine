#!/usr/bin/env python3
"""Thin desktop gate wrapper; no agent orchestration and no source modifications."""
import json, os, pathlib, subprocess, sys
from gate_common import ROOT, fixed, evidence_path

def run_gate(root, phase, base):
    if phase not in fixed.PHASES:
        raise fixed.PipelineError('Unknown phase: '+phase)
    base=evidence_path(root,base)
    base.mkdir(parents=True,exist_ok=True)
    if (base/'summary.json').exists() or (base/'desktop-result.json').exists():
        raise fixed.PipelineError('Evidence already contains a gate result; use a fresh directory')
    baseline=fixed.protected_files(root)
    fingerprint=fixed.source_fingerprint(root)
    fixed.atomic_json(base/'protected-baseline.json',baseline)
    (base/'source-fingerprint.txt').write_text(fingerprint+'\n')
    requirements=fixed.load_json(root/'ai-kit/requirements.json')
    env=dict(os.environ)
    env['ROUTE_SOURCE_FINGERPRINT']=fingerprint
    env['PYTHONDONTWRITEBYTECODE']='1'
    env.pop('OPENAI_API_KEY',None); env.pop('CODEX_API_KEY',None)
    command=['bash',str(root/'scripts/verify-phase.sh'),phase,str(base)]
    (base/'command.json').write_text(json.dumps(command)+'\n')
    with (base/'verify.log').open('w') as stream:
        result=subprocess.run(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT)
    (base/'verify.exit').write_text(str(result.returncode)+'\n')
    fixed.check_protected(root,baseline)
    after=fixed.source_fingerprint(root)
    if after != fingerprint:
        raise fixed.PipelineError('Gate changed source/config/docs')
    if result.returncode:
        raise fixed.PipelineError('Verification exit code '+str(result.returncode))
    fixed.validate_gate(fixed.load_json(base/'summary.json'),base,requirements,phase,fingerprint)
    fixed.atomic_json(base/'desktop-result.json',{'phase':phase,'status':'GATE_PASS_REVIEW_PENDING','source_fingerprint':fingerprint,'production_authorized':False,'verify_exit':result.returncode})
    return fingerprint

def main():
    if len(sys.argv)!=3:
        print('Usage: verify-desktop-phase.sh PHASE EVIDENCE_DIR',file=sys.stderr);return 2
    try:
        print('Executable gate passed; fresh review is still required. fingerprint='+run_gate(ROOT,sys.argv[1],sys.argv[2]))
        return 0
    except Exception as exc:
        print('DESKTOP GATE FAILED: '+str(exc),file=sys.stderr);return 1

if __name__=='__main__': sys.exit(main())
