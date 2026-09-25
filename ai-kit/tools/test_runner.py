"""Tests for the delivery helper ONLY, not tests of the future Route Engine.

The end-to-end tests use a clearly labelled fake Codex binary in a temporary PATH.
They never contact an LLM or claim to validate Java/MariaDB/Kubernetes application code.
"""
from __future__ import annotations
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("route_pipeline", HERE / "run_pipeline.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
KIT_ROOT = HERE.parent.parent

class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.requirements = {"requirements": [
            {"id": "AC-001", "phase": "M0", "verification_mode": "EXECUTABLE"},
            {"id": "AC-002", "phase": "M1", "verification_mode": "EXECUTABLE"},
            {"id": "AC-003", "phase": "FINAL", "verification_mode": "REVIEW"}]}
        (self.root / "tests.xml").write_text('<testsuite tests="1"><testcase name="real-assertion"/></testsuite>')
        (self.root / "log.txt").write_text("test stdout evidence\n")
        self.report = {"phase": "M1", "source_fingerprint": "abc", "production_authorized": False,
                       "checks": [{"id": x, "status": "PASS", "evidence": "log.txt"} for x in ["AC-001", "AC-002"]],
                       "suites": [{"name": "one", "tests": 1, "failures": 0, "errors": 0, "skipped": 0, "report": "tests.xml"}]}
    def tearDown(self):
        self.temp.cleanup()
    def validate(self):
        r.validate_gate(self.report, self.root, self.requirements, "M1", "abc")
    def test_valid_report(self):
        self.validate()
    def test_missing_requirement(self):
        self.report["checks"].pop()
        with self.assertRaises(r.PipelineError): self.validate()
    def test_duplicate_requirement(self):
        self.report["checks"].append(copy.deepcopy(self.report["checks"][0]))
        with self.assertRaises(r.PipelineError): self.validate()
    def test_non_pass_is_not_success(self):
        self.report["checks"][0]["status"] = "NOT_RUN"
        with self.assertRaises(r.PipelineError): self.validate()
    def test_fingerprint_mismatch(self):
        self.report["source_fingerprint"] = "stale"
        with self.assertRaises(r.PipelineError): self.validate()
    def test_skipped_tests(self):
        (self.root / "tests.xml").write_text('<testsuite><testcase name="x"><skipped/></testcase></testsuite>')
        self.report["suites"][0]["skipped"] = 1
        with self.assertRaises(r.PipelineError): self.validate()
    def test_false_test_counts(self):
        self.report["suites"][0]["tests"] = 999
        with self.assertRaises(r.PipelineError): self.validate()
    def test_empty_test_set(self):
        (self.root / "tests.xml").write_text('<testsuite tests="0"/>')
        self.report["suites"][0]["tests"] = 0
        with self.assertRaises(r.PipelineError): self.validate()
    def test_non_xml_log_is_not_junit(self):
        self.report["suites"][0]["report"] = "log.txt"
        with self.assertRaises(r.PipelineError): self.validate()
    def test_evidence_traversal(self):
        self.report["checks"][0]["evidence"] = "../outside.txt"
        with self.assertRaises(r.PipelineError): self.validate()
    def test_production_never_authorized(self):
        self.report["production_authorized"] = True
        with self.assertRaises(r.PipelineError): self.validate()
    def test_source_hash_ignores_only_build_outputs(self):
        (self.root / "source.java").write_text("before")
        initial = r.source_fingerprint(self.root)
        (self.root / ".evidence").mkdir()
        (self.root / ".evidence/anything.txt").write_text("log")
        self.assertEqual(initial, r.source_fingerprint(self.root))
        (self.root / "source.java").write_text("after")
        self.assertNotEqual(initial, r.source_fingerprint(self.root))
    def test_reviewer_cannot_complete_with_p1(self):
        result = {"phase":"M1","role":"REVIEWER","status":"COMPLETE","production_authorized":False,
                  "findings":[{"severity":"P1"}],"blockers":[],"evidence_paths":[],"verified_requirements":[]}
        with self.assertRaises(r.PipelineError): r.validate_agent(result,"M1","REVIEWER",self.requirements)
    def test_final_reviewer_requires_review_only_ids(self):
        result = {"phase":"FINAL","role":"REVIEWER","status":"COMPLETE","production_authorized":False,
                  "findings":[],"blockers":[],"evidence_paths":[],"verified_requirements":[]}
        with self.assertRaises(r.PipelineError): r.validate_agent(result,"FINAL","REVIEWER",self.requirements)
        result["verified_requirements"] = ["AC-003"]
        r.validate_agent(result,"FINAL","REVIEWER",self.requirements)

FAKE_CODEX = r'''#!/usr/bin/env python3
# TEST DOUBLE ONLY. Never installed into the user's normal PATH.
import json, os, re, sys
from pathlib import Path
if '--version' in sys.argv:
    print('fake-codex-for-runner-tests-only'); sys.exit(0)
prompt = sys.stdin.read()
phase, role = re.findall(r'Runner context: phase=(M[0-6]|FINAL); role=(BUILDER|REVIEWER)',prompt)[-1]
root=Path.cwd(); local=root/'.local';local.mkdir(exist_ok=True)
if role=='BUILDER':
    scripts=root/'scripts';scripts.mkdir(exist_ok=True)
    (scripts/'verify-phase.sh').write_text(''' + '"""' + r'''#!/usr/bin/env bash
set -eu
python3 scripts/fake_gate.py "$1" "$2"
''' + '"""' + r''')
    (scripts/'fake_gate.py').write_text(''' + '"""' + r'''# TEST DOUBLE ONLY: validates the runner's control flow, not the application.
import json, os, sys
from pathlib import Path
phase=sys.argv[1]; dest=Path(sys.argv[2]);dest.mkdir(parents=True,exist_ok=True)
phases=['M0','M1','M2','M3','M4','M5','M6','FINAL']; data=json.loads(Path('ai-kit/requirements.json').read_text())
marker=Path('.local/gate-failed-once')
if os.environ.get('FAKE_GATE_FAIL_ONCE')=='1' and phase=='M1' and not marker.exists():
 marker.write_text('seen');sys.exit(9)
(dest/'fake.txt').write_text('TEST DOUBLE EVIDENCE, NOT APPLICATION ACCEPTANCE')
(dest/'test.xml').write_text('<testsuite tests="1"><testcase name="fake-control-flow"/></testsuite>')
checks=[{'id':v['id'],'status':'PASS','evidence':'fake.txt'} for v in data['requirements'] if v['verification_mode']=='EXECUTABLE' and phases.index(v['phase'])<=phases.index(phase)]
report={'phase':phase,'source_fingerprint':os.environ['ROUTE_SOURCE_FINGERPRINT'],'production_authorized':False,'checks':checks,'suites':[{'name':'test-double','tests':1,'failures':0,'errors':0,'skipped':0,'report':'test.xml'}]}
(dest/'summary.json').write_text(json.dumps(report))
''' + '"""' + r''')
requirements=json.loads((root/'ai-kit/requirements.json').read_text())
ids=[v['id'] for v in requirements['requirements'] if v['verification_mode']=='REVIEW'] if phase=='FINAL' and role=='REVIEWER' else []
result={'phase':phase,'role':role,'status':'COMPLETE','summary':'TEST DOUBLE ONLY','findings':[],'blockers':[],'evidence_paths':[],'verified_requirements':ids,'production_authorized':False}
marker=local/'review-failed-once'
if os.environ.get('FAKE_REVIEW_FAIL_ONCE')=='1' and role=='REVIEWER' and phase=='M2' and not marker.exists():
 marker.write_text('seen');result['status']='CHANGES_REQUIRED';result['findings']=[{'severity':'P1','requirement_id':'AC-011','location':'fake','description':'test retry','reproduction':'test double','required_fix':'run builder again'}]
if os.environ.get('FAKE_BLOCK')=='1':
 result['status']='BLOCKED';result['blockers']=['simulated tool blocker']
out=Path(sys.argv[sys.argv.index('--output-last-message')+1]);out.write_text(json.dumps(result))
'''

@unittest.skipUnless(shutil.which('git') and shutil.which('bash'), 'local Git/Bash are required for runner integration tests')
class RunnerIntegrationTests(unittest.TestCase):
    def run_fake(self, extra_env=None):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);root=base/'repo';shutil.copytree(KIT_ROOT,root,ignore=shutil.ignore_patterns('__pycache__'))
            subprocess.run(['git','init','-q',str(root)],check=True)
            bindir=base/'bin';bindir.mkdir();fake=bindir/'codex';fake.write_text(FAKE_CODEX);fake.chmod(0o755)
            env=dict(os.environ);env['PATH']=str(bindir)+os.pathsep+env['PATH'];env.update(extra_env or {})
            cmd=[sys.executable,str(root/'ai-kit/tools/run_pipeline.py'),'--repo',str(root),'--execute','--ack-isolated-environment','--timeout-seconds','30']
            result=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=90)
            finalpath=root/'.ai-run/FINAL_RESULT.json'
            final=json.loads(finalpath.read_text()) if finalpath.exists() else {}
            return result,final
    def test_full_orchestration_with_fake_codex(self):
        result,final=self.run_fake()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(final['agent_calls'],16)
        self.assertEqual(final['engineering_acceptance'],'PASS')
        self.assertEqual(final['production_deployment'],'NOT_AUTHORIZED')
    def test_test_failure_returns_to_builder(self):
        result,final=self.run_fake({'FAKE_GATE_FAIL_ONCE':'1'})
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(final['agent_calls'],17)
    def test_review_failure_returns_to_builder(self):
        result,final=self.run_fake({'FAKE_REVIEW_FAIL_ONCE':'1'})
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(final['agent_calls'],18)
    def test_block_is_not_pass(self):
        result,final=self.run_fake({'FAKE_BLOCK':'1'})
        self.assertEqual(result.returncode,2,result.stdout+result.stderr)
        self.assertEqual(final.get('engineering_acceptance'),'BLOCKED')

if __name__=='__main__':
    unittest.main(verbosity=2)
