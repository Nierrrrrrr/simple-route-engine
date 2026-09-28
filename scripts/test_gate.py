#!/usr/bin/env python3
"""Negative regression tests of validators; synthetic fixtures are not engine evidence."""
import copy, json, os, pathlib, shutil, sys, tempfile, unittest, xml.etree.ElementTree as ET
from gate_common import ROOT, fixed
from desktop_gate import run_gate
from m0_validate import validate_documents, validate_state
from doctor import validate_doctor

class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.evidence',prefix='validator-test-')
        self.root=pathlib.Path(self.tmp.name)
        for name in ['ai-kit','docs','config','.mvn']:
            shutil.copytree(ROOT/name,self.root/name,ignore=shutil.ignore_patterns('__pycache__'))
        for name in ['AGENTS.md','README.md','pom.xml','mvnw','mvnw.cmd']:
            shutil.copyfile(ROOT/name,self.root/name)
        (self.root/'scripts').mkdir()
        self.base=self.root/'.evidence/gate'
    def tearDown(self):self.tmp.cleanup()
    def failure(self,action):
        with self.assertRaises((AssertionError,KeyError,fixed.PipelineError)) as captured:action()
        print('EXPECTED FAILURE:',str(captured.exception))
    def fake_gate(self,phase='M0',change=None,omit_proof=False,xml='<testsuite><testcase name="synthetic-validator-case"/></testsuite>',script_extra=''):
        """A synthetic gate producer strictly confined to a throwaway evidence fixture."""
        requirement=fixed.load_json(self.root/'ai-kit/requirements.json')
        report={'phase':phase,'source_fingerprint':'INJECT','production_authorized':False,
                'checks':[{'id':rid,'status':'PASS','evidence':'proof.log'} for rid in sorted(fixed.required_for(requirement,phase,'EXECUTABLE'))],
                'suites':[]}
        (self.root/'report.xml').write_text(xml)
        counts=fixed.junit_counts(self.root/'report.xml')
        report['suites']=[{'name':'synthetic-validator-fixture',**counts,'report':'report.xml'}]
        if change:change(report)
        (self.root/'report.json').write_text(json.dumps(report))
        script='''#!/usr/bin/env bash
set -euo pipefail
python3 - "$2" <<'PY'
import json,os,pathlib,shutil,sys
base=pathlib.Path(sys.argv[1]);root=pathlib.Path.cwd()
report=json.loads((root/'report.json').read_text())
if report['source_fingerprint']=='INJECT':report['source_fingerprint']=os.environ['ROUTE_SOURCE_FINGERPRINT']
(base/'summary.json').write_text(json.dumps(report))
shutil.copyfile(root/'report.xml',base/'report.xml')
PY
'''
        if not omit_proof:script+='printf "synthetic validator fixture only\\n" > "$2/proof.log"\n'
        script+=script_extra
        (self.root/'scripts/verify-phase.sh').write_text(script)
    def operator_proof(self):
        from recovery_gate import OPERATOR_SHAPES,OPERATOR_METADATA,OPERATOR_MODES,OPERATOR_ABSENT
        cases=[]
        for name in {m+':'+s for m in OPERATOR_MODES for s in OPERATOR_SHAPES}|OPERATOR_METADATA:
            cases.append({'case':name,'status':422,'unchanged':True,'submits':1,'state':'RECONCILING:1' if name.startswith(('resolve','cancel')) else 'MANUAL_WAIT:0'})
        for mode in OPERATOR_MODES:
            cases.append({'case':'control:'+mode,'status':200 if mode=='resolve' else 409 if mode=='capacity-reject' else 202,'state':'MANUAL_WAIT:0' if mode=='capacity-reject' else 'SUCCEEDED:0','replayWithoutCredentialFile':True,'submits':1})
        for value in OPERATOR_ABSENT:
            action=value.split(':')[1];cases.append({'case':'absent:'+value,'status':200 if action in ('STOPPED','FAILED') else 202,'optionalOutputAbsent':True,'state':'CANCELLED:0' if action=='CANCEL' else 'MANUAL_WAIT:0'})
        return {'syntheticCredentialsOnly':True,'distinctEngineDatabase':True,'cases':cases}
    def test_operator_validator_accepts_complete_synthetic_fixture(self):
        from recovery_gate import validate_operator_proof
        validate_operator_proof(self.operator_proof())
    def test_operator_validator_missing_case_fails(self):
        from recovery_gate import validate_operator_proof
        p=self.operator_proof();p['cases'].pop();self.failure(lambda:validate_operator_proof(p))
    def test_operator_validator_unsafe_status_fails(self):
        from recovery_gate import validate_operator_proof
        p=self.operator_proof();p['cases'][0]['status']=202;self.failure(lambda:validate_operator_proof(p))
    def test_operator_validator_persisted_mutation_fails(self):
        from recovery_gate import validate_operator_proof
        p=self.operator_proof();p['cases'][0]['unchanged']=False;self.failure(lambda:validate_operator_proof(p))
    def test_operator_validator_rejected_ordinary_control_fails(self):
        from recovery_gate import validate_operator_proof
        p=self.operator_proof();next(c for c in p['cases'] if c['case']=='control:resolve')['status']=422;self.failure(lambda:validate_operator_proof(p))
    def test_operator_validator_shared_database_fails(self):
        from recovery_gate import validate_operator_proof
        p=self.operator_proof();p['distinctEngineDatabase']=False;self.failure(lambda:validate_operator_proof(p))
    def crash_boundary(self,pid=123):
        return {'method':'SIGSTOP_ALL_OWNED_WRITERS','live_fixture_pids':[pid],
                'processes':[{'pid':pid,'parent_pid':99,'start_ticks':100,'cwd':str(ROOT),'executable':str((ROOT/'.tools/java/bin/java').resolve()),'command':[str(ROOT/'.tools/java/bin/java'),'-Duser.timezone=UTC','-jar','target/route-engine-0.1.0.jar'],'stopped_threads':[{'tid':pid,'state':'T'}]}],
                'snapshot_isolation':'REPEATABLE READ READ ONLY WITH CONSISTENT SNAPSHOT',
                'db_checks':[{'phase':'before_snapshot','monotonic_ns':20,'database_clock':'2026-09-25 00:00:00.000001','active_transactions':0,'active_commands':0},{'phase':'after_snapshot','monotonic_ns':50,'database_clock':'2026-09-25 00:00:00.000002','active_transactions':0,'active_commands':0}],
                'events':[{'name':'stopped','monotonic_ns':10},{'name':'snapshot_start','monotonic_ns':30},{'name':'snapshot_end','monotonic_ns':40},{'name':'kill','monotonic_ns':60,'pid':pid},{'name':'after_snapshot_start','monotonic_ns':70},{'name':'after_snapshot_end','monotonic_ns':80}]}
    def test_crash_boundary_missing_proof_fails(self):
        from recovery_gate import validate_recovery_proof
        p=self.recovery_proof();del p['crashes'][0]['boundary'];self.failure(lambda:validate_recovery_proof(p))
    def test_crash_boundary_unstopped_thread_fails(self):
        from recovery_gate import validate_recovery_proof
        p=self.recovery_proof();p['crashes'][0]['boundary']['processes'][0]['stopped_threads'][0]['state']='S';self.failure(lambda:validate_recovery_proof(p))
    def test_crash_boundary_unstopped_writer_fails(self):
        from recovery_gate import validate_recovery_proof
        p=self.recovery_proof();p['crashes'][0]['boundary']['live_fixture_pids'].append(999);self.failure(lambda:validate_recovery_proof(p))
    def test_crash_boundary_wrong_pid_fails(self):
        from recovery_gate import validate_recovery_proof
        p=self.recovery_proof();p['crashes'][0]['boundary']['processes'][0]['pid']=999;self.failure(lambda:validate_recovery_proof(p))
    def test_crash_boundary_active_transaction_fails(self):
        from recovery_gate import validate_recovery_proof
        p=self.recovery_proof();p['crashes'][0]['boundary']['db_checks'][0]['active_transactions']=1;self.failure(lambda:validate_recovery_proof(p))
    def test_crash_boundary_incorrect_event_order_fails(self):
        from recovery_gate import validate_recovery_proof
        p=self.recovery_proof();p['crashes'][0]['boundary']['events'][3]['monotonic_ns']=35;self.failure(lambda:validate_recovery_proof(p))
    def test_crash_boundary_nonconsistent_snapshot_fails(self):
        from recovery_gate import validate_recovery_proof
        p=self.recovery_proof();p['crashes'][0]['boundary']['snapshot_isolation']='multiple-autocommit-queries';self.failure(lambda:validate_recovery_proof(p))
    def test_crash_boundary_snapshot_mutation_fails(self):
        from recovery_gate import validate_recovery_proof
        p=self.recovery_proof();p['crashes'][0]['after_kill']['steps']='changed';self.failure(lambda:validate_recovery_proof(p))
    def test_crash_boundary_missing_drain_proof_fails(self):
        from recovery_gate import validate_boundary_drain
        self.failure(lambda:validate_boundary_drain(self.recovery_proof()['crashes'][0]))
    def test_crash_boundary_fake_drain_proof_fails(self):
        from recovery_gate import validate_boundary_drain
        p=self.recovery_proof()['crashes'][0];p['boundary']['quiescence_attempts']=[{'db_check':{'active_transactions':0}}]
        self.failure(lambda:validate_boundary_drain(p))
    def recovery_proof(self):
        from recovery_gate import WINDOWS
        counts={'old':{'effects':1,'submits':1},'new':{'effects':1,'submits':1}}
        before={'recovery-after-enqueue':'RECOVERY_QUEUED:0','recovery-after-admission':'RECOVERING:1','recovery-during-external-work':'RECOVERING:1','recovery-after-result-release':'SUCCEEDED:0'}
        crashes=[]
        for window in WINDOWS:
            state={'execution':before[window],'attempts':'old new'}
            crashes.append({'window':window,'boundary':self.crash_boundary(),'killed_pids':[123],'exit_codes':[-9],'restarted_pid':456,'permit_generation':2,'old_operation':'old','new_operation':'new','before':state,'after_kill':state.copy(),'after_restart':{'execution':'SUCCEEDED:0','attempts':'old new'},'counts':copy.deepcopy(counts),'before_counts':copy.deepcopy(counts)})
        return {'discovery':{'unknownFieldsRejected':3,'unchanged':True,'incident':{'operationId':'op','stepId':'step'}},'races':[{'pids':[123,456],'sameKeyRequests':20,'sameKeyDecisions':1,'differentActionStatuses':[202,409]}],'runningCancel':{'externalStatus':'STOPPED','generation':1},'resolve':{'state':'SUCCEEDED:0','audited':True,'existingOperation':'old','counts':counts},'crashes':crashes}
    def test_recovery_validator_accepts_complete_synthetic_proof_only(self):
        from recovery_gate import validate_recovery_proof
        validate_recovery_proof(self.recovery_proof())
    def test_recovery_validator_missing_crash_fails(self):
        from recovery_gate import validate_recovery_proof
        p=self.recovery_proof();p['crashes'].pop();self.failure(lambda:validate_recovery_proof(p))
    def test_recovery_validator_missing_evidence_fails(self):
        from recovery_gate import validate_recovery_proof
        p=self.recovery_proof();del p['resolve'];self.failure(lambda:validate_recovery_proof(p))
    def test_recovery_validator_duplicate_effect_fails(self):
        from recovery_gate import validate_recovery_proof
        p=self.recovery_proof();p['crashes'][0]['counts']['new']['effects']=2;self.failure(lambda:validate_recovery_proof(p))
    def test_recovery_validator_fake_crash_fails(self):
        from recovery_gate import validate_recovery_proof
        p=self.recovery_proof();p['crashes'][0]['exit_codes']=[0];self.failure(lambda:validate_recovery_proof(p))
    def test_recovery_validator_same_process_race_fails(self):
        from recovery_gate import validate_recovery_proof
        p=self.recovery_proof();p['races'][0]['pids']=[123,123];self.failure(lambda:validate_recovery_proof(p))
    def test_recovery_wrapper_missing_coverage_fails(self):
        self.fake_gate(phase='M5',change=lambda r:r['checks'].pop());self.failure(lambda:run_gate(self.root,'M5',self.base))
    def test_recovery_wrapper_skipped_case_fails(self):
        self.fake_gate(phase='M5',xml='<testsuite><testcase name="recovery"><skipped/></testcase></testsuite>');self.failure(lambda:run_gate(self.root,'M5',self.base))
    def test_recovery_wrapper_wrong_fingerprint_fails(self):
        self.fake_gate(phase='M5',change=lambda r:r.update(source_fingerprint='0'*64));self.failure(lambda:run_gate(self.root,'M5',self.base))
    def test_valid_m0_documents_and_state(self):validate_documents(self.root);validate_state(self.root)
    def test_missing_document(self):
        (self.root/'docs/architecture/TRANSACTIONS.md').unlink();self.failure(lambda:validate_documents(self.root))
    def test_broken_document_link(self):
        with (self.root/'README.md').open('a') as f:f.write('\n[broken](docs/does-not-exist.md)\n')
        self.failure(lambda:validate_documents(self.root))
    def test_missing_state_field(self):
        path=self.root/'docs/implementation/STATE.json';data=json.loads(path.read_text());del data['current_phase'];path.write_text(json.dumps(data))
        self.failure(lambda:validate_state(self.root))
    def test_missing_tool_requirement(self):
        self.failure(lambda:validate_doctor({'checks':{'java':{'exit':127,'output':'missing'}}}))
    def test_forbidden_runtime_service(self):
        path=self.root/'config/defaults.json';data=json.loads(path.read_text());data['runtimeServices'].append('redis');path.write_text(json.dumps(data))
        self.failure(lambda:validate_documents(self.root))
    def test_missing_requirement_trace(self):
        path=self.root/'docs/implementation/TRACEABILITY.md';path.write_text(path.read_text().replace('| AC-064 |','| REMOVED |'))
        self.failure(lambda:validate_state(self.root))
    def test_valid_synthetic_wrapper_report(self):
        self.fake_gate();result=run_gate(self.root,'M0',self.base);self.assertEqual(len(result),64)
    def test_wrapper_missing_evidence(self):
        self.fake_gate(omit_proof=True);self.failure(lambda:run_gate(self.root,'M0',self.base))
    def test_wrapper_wrong_fingerprint(self):
        self.fake_gate(change=lambda r:r.update(source_fingerprint='0'*64));self.failure(lambda:run_gate(self.root,'M0',self.base))
    def test_wrapper_empty_test_suite(self):
        self.fake_gate(phase='M1',xml='<testsuite/>');self.failure(lambda:run_gate(self.root,'M1',self.base))
    def test_wrapper_skipped_case(self):
        self.fake_gate(xml='<testsuite><testcase name="skipped"><skipped/></testcase></testsuite>');self.failure(lambda:run_gate(self.root,'M0',self.base))
    def test_wrapper_missing_ac(self):
        self.fake_gate(change=lambda r:r['checks'].pop());self.failure(lambda:run_gate(self.root,'M0',self.base))
    def test_wrapper_count_mismatch(self):
        self.fake_gate(change=lambda r:r['suites'][0].update(tests=100));self.failure(lambda:run_gate(self.root,'M0',self.base))
    def test_wrapper_failed_test(self):
        self.fake_gate(xml='<testsuite><testcase name="failure"><failure>deliberate</failure></testcase></testsuite>');self.failure(lambda:run_gate(self.root,'M0',self.base))
    def test_wrapper_command_failure(self):
        self.fake_gate(script_extra='exit 7\n');self.failure(lambda:run_gate(self.root,'M0',self.base))
    def test_wrapper_missing_summary(self):
        (self.root/'scripts/verify-phase.sh').write_text('#!/usr/bin/env bash\nexit 0\n');self.failure(lambda:run_gate(self.root,'M0',self.base))
    def test_wrapper_source_mutation(self):
        self.fake_gate(script_extra='printf "mutation\\n" >> README.md\n');self.failure(lambda:run_gate(self.root,'M0',self.base))
    def test_wrapper_protected_mutation(self):
        self.fake_gate(script_extra='printf "mutation\\n" >> AGENTS.md\n');self.failure(lambda:run_gate(self.root,'M0',self.base))
    def test_wrapper_path_escape(self):
        self.fake_gate(change=lambda r:r['checks'][0].update(evidence='../outside.log'));self.failure(lambda:run_gate(self.root,'M0',self.base))
    def test_wrapper_refuses_reused_evidence(self):
        self.fake_gate();run_gate(self.root,'M0',self.base);self.failure(lambda:run_gate(self.root,'M0',self.base))
    def test_final_dispatcher_missing_handoff_fails_before_cumulative(self):
        import subprocess
        for phase in fixed.PHASES[7:]:
            env=dict(os.environ,ROUTE_SOURCE_FINGERPRINT='a'*64)
            env.pop('ROUTE_FINAL_HANDOFF',None);env.pop('ROUTE_FINAL_HANDOFF_RECEIPT',None)
            env['ROUTE_RUN_ID']='synthetic-validator-only'
            p=subprocess.run(['bash',str(ROOT/'scripts/verify-phase.sh'),phase,str(self.base)],cwd=ROOT,env=env,capture_output=True,text=True)
            self.assertEqual(p.returncode,2,p.stdout+p.stderr)
            self.assertIn('FINAL requires original fresh handoff evidence',p.stderr)
            self.assertFalse((self.base/'m6').exists())
    def test_m1_missing_real_integration_fails(self):
        from foundation_gate import validate_m1_reports
        report=self.base/'junit/TEST-DefinitionRulesTest.xml';report.parent.mkdir(parents=True)
        report.write_text('<testsuite>'+''.join('<testcase name="AC%03d_fixture"/>'%n for n in range(5,11))+'</testsuite>')
        self.failure(lambda:validate_m1_reports(self.base))
    def test_m1_missing_process_coverage_fails(self):
        from foundation_gate import validate_m1_reports
        report=self.base/'junit/TEST-FoundationIT.xml';report.parent.mkdir(parents=True)
        report.write_text('<testsuite>'+''.join('<testcase name="AC%03d_fixture"/>'%n for n in range(5,10))+'</testsuite>')
        self.failure(lambda:validate_m1_reports(self.base))
    def test_m2_missing_process_suite_fails(self):
        from admission_gate import validate_m2_reports
        path=self.base/'m1/junit/TEST-dev.routeengine.AdmissionIT.xml';path.parent.mkdir(parents=True)
        path.write_text('<testsuite>'+''.join('<testcase name="AC%03d_synthetic_validator_fixture"/>'%n for n in range(11,23))+'</testsuite>')
        with self.assertRaisesRegex(fixed.PipelineError,r"Invalid JUnit XML: .*TEST-AdmissionProcesses[.]xml"):validate_m2_reports(self.base)
    def test_m3_missing_engine_process_evidence_fails(self):
        from engine_gate import validate_m3_reports
        for name in ['dev.routeengine.EngineIT','dev.routeengine.registry.EngineDslTest']:
            path=self.base/('m2/m1/junit/TEST-'+name+'.xml');path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('<testsuite>'+''.join('<testcase name="AC%03d_synthetic_validator_fixture"/>'%n for n in range(23,32))+'</testsuite>')
        with self.assertRaisesRegex(fixed.PipelineError,r"Invalid JUnit XML: .*TEST-EngineProcesses[.]xml"):validate_m3_reports(self.base)
    def test_engine_isolation_proof_missing_fails(self):
        from foundation_gate import validate_test_database_isolation
        with self.assertRaises(FileNotFoundError):validate_test_database_isolation(self.base)
    def test_engine_isolation_shared_database_fails(self):
        from foundation_gate import validate_test_database_isolation
        self.base.mkdir(parents=True,exist_ok=True)
        (self.base/'test-database-isolation.json').write_text(json.dumps({'main':{'container_id':'same','url':'jdbc:same'},'engine':{'container_id':'same','url':'jdbc:same'}}))
        with self.assertRaises(AssertionError):validate_test_database_isolation(self.base)
    def test_engine_isolation_cross_suite_rows_fail(self):
        from foundation_gate import validate_test_database_isolation
        self.base.mkdir(parents=True,exist_ok=True)
        (self.base/'test-database-isolation.json').write_text(json.dumps({'main':{'container_id':'main','url':'jdbc:main'},'engine':{'container_id':'engine','url':'jdbc:engine'},'main_engine_executions':1,'engine_admission_executions':0}))
        with self.assertRaises(AssertionError):validate_test_database_isolation(self.base)
    def m4_validator_fixture(self):
        # Synthetic validator data only, never executable adapter acceptance evidence.
        from adapter_gate import JAVA_SUITES,SCALAR_BLOCKED_CASES,SCALAR_CONTROL_CASES
        import hashlib
        base=self.base;folder=base/'integration';(folder/'junit').mkdir(parents=True)
        cases=[{'case':name,'blocked':name in SCALAR_BLOCKED_CASES,'state':'RECONCILING:1' if name in SCALAR_BLOCKED_CASES else 'SUCCEEDED:0','secretPersisted':False,'inDoubtIncidents':1 if name in SCALAR_BLOCKED_CASES else 0,'downstreamAttempts':0 if name in SCALAR_BLOCKED_CASES else 1,'outputAbsent':name in SCALAR_BLOCKED_CASES,'auditSecretAbsent':True,'responseBodyLogged':False} for name in sorted(SCALAR_BLOCKED_CASES|SCALAR_CONTROL_CASES)]
        (self.base/'integration/scalar-secret-boundary.json').write_text(json.dumps({'actualHttpSubmits':len(cases),'cases':cases}))

        names=['dev.routeengine.'+n for n in JAVA_SUITES]+['AdapterArtifacts']
        for name in names:
            (folder/'junit'/('TEST-'+name+'.xml')).write_text('<testsuite>'+''.join('<testcase name="AC%03d_synthetic_validator_fixture"/>'%n for n in range(32,42))+'</testsuite>')
        (base/'processes/junit').mkdir(parents=True)
        (base/'processes/junit/TEST-AdapterProcesses.xml').write_text('<testsuite><testcase name="synthetic_validator_fixture"/></testsuite>')
        actual={p.relative_to(ROOT/'config/runner').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'config/runner').rglob('*')) if p.is_file()}
        (folder/'runner-context.json').write_text(json.dumps(actual))
        (folder/'runner-image-ref.txt').write_text('docker.io/route-engine/runner@sha256:'+'a'*64)
        for name in ['runner-image-build','runner-image-load','runner-digest-alias','runner-versions']:
            for suffix,value in [('.exit','0'),('.command.json','["synthetic"]'),('.log','synthetic validator only')]:
                (folder/('raw-01-'+name+suffix)).write_text(value)
        proofs={
          'decoded-secret-boundary':{'actualHttpSubmits':6,'cases':[{'state':'RECONCILING:1','secretPersisted':False} for _ in range(6)]},
          **{'queued-binding-'+change:{'sameDefinitionHash':True,'rebound':False,'state':'RECONCILING:1','newVersion':2,'newVersionAdoptsCurrentBinding':True} for change in ['playbook','image','target']},
          'retry-binding-proof':{'actualHttpSubmits':1,'oldState':'RECONCILING:1','newVersionAdoptsCurrentBinding':True},
          'binding-immutability-proof':{'directSqlRejected':2,'sqlState':'45000','originalUnchanged':True},
          'reference-publication-proof':{'rejected':10,'draftPreserved':True,'noDevelopmentBypass':True},
          'reference-runtime-proof':{'rejected':3,'noExternalIo':True},
          'artifact-survival-proof':{'canaryOperationId':'synthetic','canaryCommandSecretAbsent':True,'rc':0,'status':'successful','jobEvents':4,'commandsScanned':1,'allArtifactFilesScanned':9,'deletedPodUids':['synthetic'],'afterPodDeletion':True,'secretAbsent':True,'databaseAndLogSecretAbsent':True},
          'deployment-uid-generation-conflict':{'actualConflict':409,'uid':'synthetic','generation':1,'state':'SUCCEEDED:0'},
          'failed-rollout-stopped':{'pods':0,'state':'MANUAL_WAIT:0'},
          'job-missing-retained':{'uid':'synthetic','state':'RECONCILING:1'},
          'runner-cancel-task-started':{'event':'runner_on_start','task':'Bounded synchronous wait','operationId':'synthetic'},
          'runner-cancel-converged':{'operation':'synthetic','permitGeneration':1,'state':'CANCELLED:0'}}
        for name,value in proofs.items():(folder/(name+'.json')).write_text(json.dumps(value))
        crashes=[{'window':window,'boundary':self.crash_boundary(1),'after_kill':{'attempts':'synthetic'},'killed_pids':[1],'exit_codes':[-9],'restarted_pid':2,'operation':'synthetic','before':{'attempts':'synthetic'},'after_restart':{'attempts':'synthetic'},'job_uid':'synthetic','job_count':1,'side_effects':1,'submits':1} for window in ['real-http-side-effect-before-result-db','non-dedupe-http-unknown','real-job-created-before-result-db']]
        (base/'processes/crash-proof.json').write_text(json.dumps(crashes))
    def test_m4_validator_valid_synthetic_fixture(self):
        from adapter_gate import validate_m4_reports
        self.m4_validator_fixture();self.assertEqual(7,len(validate_m4_reports(self.base)))
    def test_m4_missing_publication_binding_proof_fails(self):
        from adapter_gate import validate_m4_reports
        self.m4_validator_fixture();(self.base/'integration/queued-binding-image.json').unlink()
        with self.assertRaisesRegex(fixed.PipelineError,r"Cannot read JSON .*queued-binding-image[.]json"):validate_m4_reports(self.base)
    def test_m4_decoded_secret_leak_proof_fails(self):
        from adapter_gate import validate_m4_reports
        self.m4_validator_fixture();p=self.base/'integration/decoded-secret-boundary.json';v=json.loads(p.read_text());v['cases'][1]['secretPersisted']=True;p.write_text(json.dumps(v))
        self.failure(lambda:validate_m4_reports(self.base))
    def test_m4_missing_actual_report_fails(self):
        from adapter_gate import validate_m4_reports
        self.m4_validator_fixture();(self.base/'integration/junit/TEST-dev.routeengine.KubernetesAcceptance.xml').unlink()
        self.failure(lambda:validate_m4_reports(self.base))
    def test_m4_empty_report_fails(self):
        from adapter_gate import validate_m4_reports
        self.m4_validator_fixture();(self.base/'integration/junit/TEST-dev.routeengine.KubernetesAcceptance.xml').write_text('<testsuite/>')
        self.failure(lambda:validate_m4_reports(self.base))
    def test_m4_skipped_report_fails(self):
        from adapter_gate import validate_m4_reports
        self.m4_validator_fixture();(self.base/'integration/junit/TEST-dev.routeengine.KubernetesAcceptance.xml').write_text('<testsuite><testcase><skipped/></testcase></testsuite>')
        self.failure(lambda:validate_m4_reports(self.base))
    def test_m4_missing_requirement_fails(self):
        from adapter_gate import validate_m4_reports
        self.m4_validator_fixture()
        for p in (self.base/'integration/junit').glob('*.xml'):p.write_text(p.read_text().replace('AC037_','REMOVED_'))
        self.failure(lambda:validate_m4_reports(self.base))
    def test_m4_missing_scalar_proof_fails(self):
        from adapter_gate import validate_m4_reports
        self.m4_validator_fixture();(self.base/'integration/scalar-secret-boundary.json').unlink()
        with self.assertRaisesRegex(fixed.PipelineError,r"Cannot read JSON .*scalar-secret-boundary[.]json"):validate_m4_reports(self.base)
    def test_m4_scalar_secret_leak_fails(self):
        from adapter_gate import validate_m4_reports
        self.m4_validator_fixture();p=self.base/'integration/scalar-secret-boundary.json';v=json.loads(p.read_text());v['cases'][0]['secretPersisted']=True;p.write_text(json.dumps(v))
        self.failure(lambda:validate_m4_reports(self.base))
    def test_m4_scalar_control_rejection_fails(self):
        from adapter_gate import validate_m4_reports
        self.m4_validator_fixture();p=self.base/'integration/scalar-secret-boundary.json';v=json.loads(p.read_text())
        next(c for c in v['cases'] if c['case']=='control-null')['state']='RECONCILING:1';p.write_text(json.dumps(v))
        self.failure(lambda:validate_m4_reports(self.base))
    def test_m4_scalar_missing_variant_fails(self):
        from adapter_gate import validate_m4_reports
        self.m4_validator_fixture();p=self.base/'integration/scalar-secret-boundary.json';v=json.loads(p.read_text());v['cases'].pop();p.write_text(json.dumps(v))
        self.failure(lambda:validate_m4_reports(self.base))
    def test_m4_missing_artifact_proof_fails(self):
        from adapter_gate import validate_m4_reports
        self.m4_validator_fixture();(self.base/'integration/artifact-survival-proof.json').unlink()
        with self.assertRaisesRegex(fixed.PipelineError,r"Cannot read JSON .*artifact-survival-proof[.]json"):validate_m4_reports(self.base)
    def test_m4_wrong_image_context_fails(self):
        from adapter_gate import validate_m4_reports
        self.m4_validator_fixture();(self.base/'integration/runner-context.json').write_text('{}')
        self.failure(lambda:validate_m4_reports(self.base))
    def test_m4_missing_image_build_proof_fails(self):
        from adapter_gate import validate_m4_reports
        self.m4_validator_fixture();(self.base/'integration/raw-01-runner-image-build.exit').unlink()
        self.failure(lambda:validate_m4_reports(self.base))
    def test_m4_secret_scan_failure_fails(self):
        from adapter_gate import validate_m4_reports
        self.m4_validator_fixture();p=self.base/'integration/artifact-survival-proof.json';v=json.loads(p.read_text());v['secretAbsent']=False;p.write_text(json.dumps(v))
        self.failure(lambda:validate_m4_reports(self.base))
    def m6_proofs(self):
        p={'databasePortSelection':{'allocator':'Docker','endpoint':'127.0.0.1:34567','databaseEntrypointUsed':False,'probeRemovedBeforeDatabase':True,'retryOnTransferFailure':False},'roles':{'callerDenied':5,'operatorDenied':2,'wrongToken':401,'operationalRead':200,'foreignDecisionRead':404,'operatorCancel':202,'startupRejected':[{'exit':1}]*2},'graceful':{'exit':143,'overlapPids':[2,3],'oldPid':1,'effects':1,'submits':1,'permitGeneration':1},'metrics':{'endpoint':'127.0.0.1:34567','readinessDbOutage':503,'readinessRecoveredSamePid':200,'restartSameEndpoint':True,'auditRecords':1,'values':{'route.queue.depth':1,'route.permits.total':2,'route.permits.noncritical':1,**{'metric'+str(i):0 for i in range(7)}}},'demos':[{'route':'demo-delivery-'+str(i),'state':'SUCCEEDED:0','definitionHash':'a'*64,'pid':10,'aliveAfterCompletion':True} for i in range(1,6)],'demoLifecycle':{'startedPids':[10],'exitBeforeAllCompleted':None},'rbac':{'actualCreateGetDelete':True,'actualDenied':[{'forbidden':True}]*3,'decisions':[{'allowed':x} for x in [True,True,False,False,False]]},'backup':{'source':'a','restored':'b','dumpSha256':'a'*64,'comparisons':[{'source':'x','restored':'x'}]*4}}
        u={'oldSourceFingerprint':'437f8be7254c3d2685a87b33c5aaaab0191fdca5814ff7834dde2092bfa89fb5','oldRuntimeMode':'EXACT_ACCEPTED_ARTIFACT','oldJarSha256':'0dbeee3eca2ee43e86d9a97bf089263bd007c722f9b8557ee71f1be901ec6072','acceptedJarSha256':'0dbeee3eca2ee43e86d9a97bf089263bd007c722f9b8557ee71f1be901ec6072','oldPid':1,'newPid':2,'versionsBefore':list(map(str,range(1,8))),'versionsAfter':list(map(str,range(1,9))),'definitionsAndBindingsUnchanged':True,'beforeDefinitionRows':'fixture','afterDefinitionRows':'fixture','manualBefore':{'execution':'MANUAL_WAIT:0'},'queuedBefore':{'execution':'QUEUED:0'},'manualAfter':{'execution':'SUCCEEDED:0'},'queuedAfter':{'execution':'SUCCEEDED:0'},'queuedPriority':'LOW','manualPermitGeneration':2}
        s={'blocked':{'lock_waits':1},'attemptsAfterShutdown':0,'submitsAfterShutdown':0,'exit':143,'stateAfterShutdown':'ADMITTED:1','pid':1,'restartPid':2,'finalState':'SUCCEEDED:0','restartSubmits':1,'restartEffects':1}
        return p,u,s
    def test_m6_missing_actual_proof_fails(self):
        from hardening_gate import validate_reports
        self.failure(lambda:validate_reports(self.base))
    def test_m6_each_material_proof_negative_fails(self):
        from hardening_gate import validate_proofs
        validate_proofs(*self.m6_proofs())
        mutations=[lambda p,u,s:p.pop('databasePortSelection'),lambda p,u,s:p['databasePortSelection'].update(allocator='WSL'),lambda p,u,s:p['databasePortSelection'].update(databaseEntrypointUsed=True),lambda p,u,s:p['databasePortSelection'].update(probeRemovedBeforeDatabase=False),lambda p,u,s:p['databasePortSelection'].update(retryOnTransferFailure=True),lambda p,u,s:p['databasePortSelection'].update(endpoint='127.0.0.1:34568'),lambda p,u,s:p['roles'].update(operationalRead=404),lambda p,u,s:p['metrics']['values'].update({'route.permits.total':0}),lambda p,u,s:p['rbac'].update(actualCreateGetDelete=False),lambda p,u,s:p['demos'].pop(),lambda p,u,s:p['demoLifecycle'].update(startedPids=[10,11]),lambda p,u,s:p['demoLifecycle'].update(exitBeforeAllCompleted=-9),lambda p,u,s:p['demos'][0].update(pid=11),lambda p,u,s:p['demos'][0].update(aliveAfterCompletion=False),lambda p,u,s:u.update(oldJarSha256='a'*64),lambda p,u,s:u.update(afterDefinitionRows='changed'),lambda p,u,s:u.update(queuedPriority='CRITICAL'),lambda p,u,s:s.update(attemptsAfterShutdown=1),lambda p,u,s:s.update(restartEffects=2),lambda p,u,s:p['backup'].update(restored='a')]
        for mutate in mutations:
            p,u,s=self.m6_proofs();mutate(p,u,s);self.failure(lambda:validate_proofs(p,u,s))
    def test_m6_empty_skipped_and_missing_checks_fail(self):
        for xml in ['<testsuite/>','<testsuite><testcase name="m6"><skipped/></testcase></testsuite>']:
            self.fake_gate(phase='M6',xml=xml);self.failure(lambda:run_gate(self.root,'M6',self.base))
            shutil.rmtree(self.base)
        self.fake_gate(phase='M6',change=lambda r:r['checks'].pop());self.failure(lambda:run_gate(self.root,'M6',self.base))
    def test_dispatcher_requires_fingerprint(self):
        import subprocess
        env=dict(os.environ);env.pop('ROUTE_SOURCE_FINGERPRINT',None)
        for phase in ['M0','M5']:
            p=subprocess.run(['bash',str(ROOT/'scripts/verify-phase.sh'),phase,str(self.base)],cwd=ROOT,env=env,capture_output=True,text=True)
            self.assertEqual(p.returncode,2);self.assertIn('FINGERPRINT',p.stderr)

class JunitResult(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.cases=[]
    def startTest(self,test):super().startTest(test);self.cases.append((test,ET.Element('testcase',{'classname':type(test).__name__,'name':test._testMethodName})))
    def addFailure(self,test,err):super().addFailure(test,err);ET.SubElement(self.cases[-1][1],'failure').text=self._exc_info_to_string(err,test)
    def addError(self,test,err):super().addError(test,err);ET.SubElement(self.cases[-1][1],'error').text=self._exc_info_to_string(err,test)
    def addSkip(self,test,reason):super().addSkip(test,reason);ET.SubElement(self.cases[-1][1],'skipped').text=reason

if __name__=='__main__':
    dest=pathlib.Path(sys.argv[1]);dest.parent.mkdir(parents=True,exist_ok=True)
    from test_final_evidence import FinalEvidenceTests
    from test_final_async import FinalAsyncTests
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(GateTests),unittest.defaultTestLoader.loadTestsFromTestCase(FinalEvidenceTests),unittest.defaultTestLoader.loadTestsFromTestCase(FinalAsyncTests)])
    result=unittest.TextTestRunner(verbosity=2,resultclass=JunitResult).run(suite)
    xml=ET.Element('testsuite',{'name':'GateTests','tests':str(result.testsRun),'failures':str(len(result.failures)),'errors':str(len(result.errors)),'skipped':str(len(result.skipped))})
    for _,case in result.cases:xml.append(case)
    ET.ElementTree(xml).write(dest,encoding='utf-8',xml_declaration=True)
    sys.exit(0 if result.wasSuccessful() else 1)
