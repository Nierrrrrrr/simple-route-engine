#!/usr/bin/env python3
"""M0 structural contracts plus actual doctor and negative-test execution."""
import json, os, pathlib, re, subprocess, sys
from gate_common import ROOT, fixed, evidence_path

M0_DOCS=['README.md','docs/architecture/OVERVIEW.md','docs/architecture/STATE_MACHINES.md',
 'docs/architecture/TRANSACTIONS.md','docs/architecture/FAILURE_RECOVERY.md','docs/adr/0001-stack.md',
 'docs/adr/0002-api-security-dsl.md','docs/api/openapi.yaml','docs/routes/DSL_REFERENCE.md',
 'docs/routes/schema.json','docs/agent/HANDOFF.md','docs/agent/TESTING.md',
 'docs/implementation/STATE.json','docs/implementation/DECISIONS.md','docs/implementation/TRACEABILITY.md']

def validate_documents(root):
    for name in M0_DOCS:
        path=root/name
        assert path.is_file() and path.stat().st_size>0, 'Missing/empty document: '+name
    for path in [root/'README.md',*(root/'docs').rglob('*.md')]:
        content=path.read_text()
        for target in re.findall(r'\]\(([^\s)]+)\)',content):
            if '://' in target or target.startswith('#'):continue
            target=target.split('#')[0]
            resolved=(path.parent/target).resolve()
            assert resolved.is_relative_to(root) and resolved.exists(), 'Broken document link: '+str(path)+' -> '+target
    defaults=fixed.load_json(root/'config/defaults.json')
    assert defaults['totalSlots']==100 and defaults['criticalReserved']==20
    assert defaults['weights']=={'HIGH':6,'NORMAL':3,'LOW':1}
    assert defaults['wrrCycle']=='HHHHHHNNNL' and defaults['isolation']=='READ_COMMITTED'
    assert defaults['runtimeServices']==['spring-boot','mariadb','existing-kubernetes']
    assert defaults['maxParallelDepth']==1
    versions=fixed.load_json(root/'config/versions.json')
    for key in ['java','maven','mavenWrapper','springBoot','mariaDb','mariaDbJdbc','flyway','kubernetesClient','junitJupiter','testcontainers','kind','kubernetes','ansibleRunner','ansibleCore']:
        assert re.fullmatch(r'[0-9]+(?:\.[0-9]+)+(?:\+[0-9]+)?',versions[key]), 'Unpinned version: '+key
    api=fixed.load_json(root/'docs/api/openapi.yaml')  # JSON is valid YAML 1.2
    assert api['openapi']=='3.1.0' and api['security']==[{'bearerAuth':[]}]
    for path in ['/executions','/executions/{id}/recoveries','/executions/{id}/cancel','/executions/{id}/incidents/{incidentId}/resolve','/capacity']:
        assert path in api['paths'], 'Missing API path: '+path
    actions=api['components']['schemas']['RecoveryRequest']['properties']['action']['enum']
    assert actions==['RETRY','SKIP','ROLLBACK','CANCEL']
    assert 'priority' not in api['components']['schemas']['RecoveryRequest']['properties']
    dsl=fixed.load_json(root/'docs/routes/schema.json')
    assert dsl['additionalProperties'] is False
    assert set(dsl['$defs']['node']['properties']['type']['enum'])=={'SEQUENCE','CONDITION','PARALLEL','REST','KUBERNETES','ANSIBLE'}
    states=(root/'docs/architecture/STATE_MACHINES.md').read_text()
    for invariant in ['IN_DOUBT','ALL_SETTLED','MANUAL_WAIT','permit_generation','lease_generation','operation_generation','Manual CANCEL','Running cancel']:
        assert invariant in states, 'Missing state invariant: '+invariant
    transaction=(root/'docs/architecture/TRANSACTIONS.md').read_text()
    assert 'scheduler_pool → execution → incident/admission_request → step' in transaction
    assert 'READ COMMITTED' in transaction and 'affected rows' in transaction
    for wrapper in ['mvnw','mvnw.cmd','.mvn/wrapper/maven-wrapper.jar','.mvn/wrapper/maven-wrapper.properties']:
        assert (root/wrapper).is_file(), 'Missing official wrapper file: '+wrapper
    props=(root/'.mvn/wrapper/maven-wrapper.properties').read_text()
    assert '3.9.11' in props and re.search(r'distributionSha256Sum=[a-f0-9]{64}',props)

def validate_state(root):
    state=fixed.load_json(root/'docs/implementation/STATE.json')
    keys={'schema_version','run_id','current_phase','status','completed_phases','phase_rounds','agent_calls','review_status','pending','evidence_root','engineering_acceptance','external_acceptance','production_authorized','blockers'}
    assert keys <= state.keys(), 'Missing STATE fields: '+str(keys-state.keys())
    assert state['schema_version']==1 and state['current_phase'] in fixed.PHASES
    assert state['production_authorized'] is False and state['external_acceptance']=='NOT_RUN'
    assert isinstance(state['pending'],list) and isinstance(state['completed_phases'],list)
    assert state['agent_calls']['total_known']==state['agent_calls']['main_sessions']+state['agent_calls']['subagent_calls']
    for phase in fixed.PHASES:
        p=root/'docs/implementation/execplans'/f'{phase}.md'
        assert p.is_file() and 'Status:' in p.read_text(), 'Missing phase plan: '+phase
    trace=(root/'docs/implementation/TRACEABILITY.md').read_text()
    for requirement in fixed.load_json(root/'ai-kit/requirements.json')['requirements']:
        assert len(re.findall(r'\| '+requirement['id']+r' \|',trace))==1,'Requirement missing or duplicated: '+requirement['id']
    assert 'NEEDS_FRESH_REVIEW' in json.dumps(state) or state['review_status'] in ['REVIEWED','IN_PROGRESS']

def main():
    base=evidence_path(ROOT,sys.argv[1]);base.mkdir(parents=True,exist_ok=True)
    summary={'phase':'M0','source_fingerprint':os.environ.get('ROUTE_SOURCE_FINGERPRINT',''),'production_authorized':False,'checks':[],'suites':[]}
    def check(rid,action):
        log=base/(rid+'.log')
        try:action();status='PASS';text=rid+' validation completed\n'
        except Exception as exc:status='FAIL';text=rid+' '+repr(exc)+'\n'
        log.write_text(text);summary['checks'].append({'id':rid,'status':status,'evidence':log.name})
    check('AC-001',lambda:validate_documents(ROOT))
    def doctor():
        with (base/'doctor-command.log').open('w') as stream:
            rc=subprocess.run(['bash','scripts/doctor.sh',str(base/'doctor')],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT).returncode
        (base/'doctor-command.exit').write_text(str(rc)+'\n')
        assert rc==0, 'Actual doctor failed; see doctor-command.log'
        from doctor import validate_doctor
        validate_doctor(fixed.load_json(base/'doctor/doctor.json'))
    check('AC-002',doctor)
    def selftests():
        with (base/'selftest.log').open('w') as stream:
            rc=subprocess.run(['python3','-B','scripts/test_gate.py',str(base/'junit/TEST-Gate.xml')],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT).returncode
        (base/'selftest.exit').write_text(str(rc)+'\n')
        report=base/'junit/TEST-Gate.xml';counts=fixed.junit_counts(report)
        summary['suites'].append({'name':'gate-negative-regression',**counts,'report':'junit/TEST-Gate.xml'})
        assert rc==0 and counts['tests']>0 and not any(counts[k] for k in ['failures','errors','skipped']), 'Selftests failed'
    check('AC-003',selftests)
    check('AC-004',lambda:validate_state(ROOT))
    fixed.atomic_json(base/'summary.json',summary)
    try:
        fixed.validate_gate(summary,base,fixed.load_json(ROOT/'ai-kit/requirements.json'),'M0',os.environ.get('ROUTE_SOURCE_FINGERPRINT',''))
    except Exception as exc:print('M0 FAILED:',exc);return 1
    print('M0 executable checks passed; review pending');return 0

if __name__=='__main__':sys.exit(main())
