#!/usr/bin/env python3
"""Real isolated MariaDB, Maven tests and packaged HTTP process acceptance. No mock fallback."""
import contextlib, hashlib, json, os, pathlib, re, secrets, shutil, socket, subprocess, sys, time, traceback, urllib.error, urllib.request, uuid
import xml.etree.ElementTree as ET
from gate_common import ROOT, fixed, evidence_path

class DatabaseStartupFailure(RuntimeError):
    def __init__(self, reason, state=None):
        super().__init__('Isolated MariaDB startup failed: '+reason)
        self.reason=reason
        self.state=state or {}

class LocalFixture:
    def __init__(self, base):
        self.base=base
        self.run=os.environ['ROUTE_RUN_ID']
        self.name='re-m1-'+self.run.lower()+'-'+uuid.uuid4().hex[:8]
        self.env=dict(os.environ)
        self.token=secrets.token_urlsafe(40)
        self.secret_dir=ROOT/'.local'/self.name
        self.process=None
        self.created=False
        self.sequence=0
        self.database_endpoints=[]
        self.initialized=False
        self.initializing=False
    def command_result(self, args, name, env=None, timeout=None):
        self.sequence+=1
        path=self.base/('raw-%02d-%s'%(self.sequence,name))
        path.with_suffix('.command.json').write_text(json.dumps(args)+'\n')
        with path.with_suffix('.log').open('w') as out:
            try:
                result=subprocess.run(args,cwd=ROOT,env=env or self.env,stdout=out,stderr=subprocess.STDOUT,timeout=timeout)
                code=result.returncode
            except subprocess.TimeoutExpired:
                out.write('Command exceeded remaining fixture readiness budget\n');code=124
        path.with_suffix('.exit').write_text(str(code)+'\n')
        return code,path.with_suffix('.log').read_text().strip()
    def command(self, args, name, env=None):
        code,output=self.command_result(args,name,env)
        if code:raise RuntimeError(name+' exited '+str(code)+'; see raw-%02d-'%self.sequence+name+'.log')
        return output
    def database_diagnostics(self):
        state_code,state=self.command_result(['docker','inspect','--format','{{json .State}}',self.name],'database-state')
        _,logs=self.command_result(['docker','logs',self.name],'database-server')
        return json.loads(state) if state_code==0 else {},logs
    def _remove_failed_initialization(self):
        assert self.initializing and not self.initialized and self.process is None,'Never recreate a used database'
        owner=self.command(['docker','inspect','--format','{{json .Config.Labels}}',self.name],'initialization-owner')
        labels=json.loads(owner)
        assert labels.get('route-engine.run-id')==self.run and labels.get('route-engine.purpose')=='foundation-test','Refuse recreation without exact owner and purpose'
        mounts=json.loads(self.command(['docker','inspect','--format','{{json .Mounts}}',self.name],'initialization-volumes'))
        assert len(mounts)==1 and mounts[0]['Type']=='volume' and mounts[0]['Destination']=='/var/lib/mysql' and re.fullmatch('[a-f0-9]{64}',mounts[0]['Name']),'Only fresh anonymous database volume may be removed'
        self.command(['docker','rm','--force','--volumes',self.name],'failed-initialization-cleanup')
        self.created=False
    def _initialize_database(self,args,deadline):
        assert not self.initialized and not self.created,'Database initialization must be fresh'
        self.initializing=True
        try:
            for attempt in range(2):
                if time.monotonic()>=deadline:raise DatabaseStartupFailure('deadline')
                code,_=self.command_result(args,'database-start',timeout=max(.001,deadline-time.monotonic()))
                if code:
                    # A timed-out Docker client can leave a created container on the daemon.
                    found,labels=self.command_result(['docker','inspect','--format','{{json .Config.Labels}}',self.name],'failed-create-owner',timeout=10)
                    if found==0:
                        labels=json.loads(labels)
                        if labels.get('route-engine.run-id')==self.run and labels.get('route-engine.purpose')=='foundation-test':
                            self.created=True
                            self.database_diagnostics()
                    raise DatabaseStartupFailure('docker-run')
                self.created=True
                try:
                    self.wait_db(deadline)
                    return
                except DatabaseStartupFailure as error:
                    # Only an unused initialization whose entrypoint exited with this exact TLS error.
                    if attempt or error.reason!='tls-not-yet-valid' or error.state.get('Status')!='exited' or time.monotonic()>=deadline:raise
                    self._remove_failed_initialization()
        finally:self.initializing=False
    def start(self):
        deadline=time.monotonic()+90
        self.secret_dir.mkdir(parents=True,exist_ok=False)
        os.chmod(self.secret_dir,0o700)
        pw=secrets.token_urlsafe(40)
        secret=self.secret_dir/'database.env'
        secret.write_text('MARIADB_ROOT_PASSWORD='+secrets.token_urlsafe(40)+'\nMARIADB_DATABASE=route_test\nMARIADB_USER=route_test\nMARIADB_PASSWORD='+pw+'\n')
        os.chmod(secret,0o600)
        image=(ROOT/'config/mariadb-image.txt').read_text().strip()
        self._initialize_database(['docker','run','--detach','--name',self.name,'--label','route-engine.run-id='+self.run,'--label','route-engine.purpose=foundation-test','--env-file',str(secret),'-p','127.0.0.1::3306',image,'--transaction-isolation=READ-COMMITTED','--default-time-zone=+00:00'],deadline)
        port=self.command(['docker','port',self.name,'3306/tcp'],'database-port').split(':')[-1]
        self.env.update(ROUTE_DB_URL='jdbc:mariadb://127.0.0.1:'+port+'/route_test',ROUTE_DB_USER='route_test',ROUTE_DB_PASSWORD=pw,ROUTE_ADMIN_TOKEN_SHA256=hashlib.sha256(self.token.encode()).hexdigest(),ROUTE_TEST_TOKEN=self.token)
        self.record_database_endpoint('initial')
        self.wait_db(deadline,initial_schema=True)
        self.initialized=True
        (self.base/'empty-database.log').write_text('Real MariaDB schema has zero tables before application migration.\n')
    def record_database_endpoint(self, stage):
        endpoint=self.command(['docker','port',self.name,'3306/tcp'],'database-port-'+stage)
        host,port=endpoint.rsplit(':',1)
        deadline=time.monotonic()+20
        while True:
            try:
                with socket.create_connection((host,int(port)),timeout=2) as connection:
                    connection.settimeout(2)
                    assert len(connection.recv(4))==4,'MariaDB handshake header not ready'
                break
            except (OSError,AssertionError):
                if time.monotonic()>=deadline:raise RuntimeError('Published MariaDB endpoint did not become ready')
                time.sleep(0.2)
        self.env['ROUTE_DB_URL']='jdbc:mariadb://'+endpoint+'/route_test'
        identity=self.command(['docker','inspect','--format','{{.Id}}',self.name],'database-identity-'+stage)
        self.database_endpoints.append({'stage':stage,'endpoint':endpoint,'container_id':identity})
    def sql_args(self,sql):
        script='MYSQL_PWD="$MARIADB_PASSWORD" exec mariadb -u "$MARIADB_USER" "$MARIADB_DATABASE" -N -e "$1"'
        return ['docker','exec',self.name,'sh','-c',script,'_',sql]
    def sql(self,sql):
        return self.command(self.sql_args(sql),'database-query')
    def wait_db(self,deadline=None,*,initial_schema=False):
        if initial_schema and (not self.created or self.initialized or self.process is not None or getattr(self,'apps',[])):
            raise DatabaseStartupFailure('initial-schema-requires-fresh-unused-database')
        probe='SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()' if initial_schema else 'SELECT 1'
        expected='0' if initial_schema else '1'
        # Healthcheck explicitly skips SSL verification; it cannot establish SQL readiness.
        end=deadline if deadline is not None else time.monotonic()+90
        try:
            while time.monotonic()<end:
                remaining=lambda:max(.001,end-time.monotonic())
                state_code,state_text=self.command_result(['docker','inspect','--format','{{json .State}}',self.name],'readiness-state',timeout=remaining())
                if state_code:raise DatabaseStartupFailure('container-state')
                state=json.loads(state_text)
                if state['Status']=='exited':
                    _,logs=self.command_result(['docker','logs',self.name],'readiness-exited-server',timeout=remaining())
                    reason='tls-not-yet-valid' if 'TLS/SSL error: certificate is not yet valid' in logs else 'entrypoint-exited'
                    raise DatabaseStartupFailure(reason,state)
                code,_=self.command_result(['docker','exec',self.name,'healthcheck.sh','--connect','--innodb_initialized'],'readiness-healthcheck',timeout=remaining())
                if code==0:
                    code,output=self.command_result(self.sql_args(probe),'initial-schema-sql' if initial_schema else 'readiness-sql',timeout=remaining())
                    if code==0:
                        if output!=expected:raise DatabaseStartupFailure('unexpected-sql-result',state)
                        return
                    if output!='ERROR 2026 (HY000): TLS/SSL error: certificate is not yet valid':
                        raise DatabaseStartupFailure('sql-error',state)
                time.sleep(min(.5,remaining()))
            raise DatabaseStartupFailure('deadline')
        except Exception:
            self.database_diagnostics()
            raise
    def start_app(self, suffix):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
        self.env['ROUTE_PORT']=str(self.port)
        self.stream=(self.base/('application-'+suffix+'.log')).open('w')
        args=['bash','scripts/local-run.sh']
        (self.base/('application-'+suffix+'.command.json')).write_text(json.dumps(args)+'\n')
        self.process=subprocess.Popen(args,cwd=ROOT,env=self.env,stdout=self.stream,stderr=subprocess.STDOUT)
        end=time.monotonic()+90
        while time.monotonic()<end:
            if self.process.poll() is not None:raise RuntimeError('Application exited during startup; see application-'+suffix+'.log')
            try:
                status,data=self.http('GET','/actuator/health')
                if status==200 and data['status']=='UP':return
            except (OSError,urllib.error.URLError):pass
            time.sleep(0.25)
        raise RuntimeError('Packaged application health timeout')
    def stop_app(self):
        if self.process:
            self.process.terminate()
            try:code=self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:self.process.kill();code=self.process.wait(timeout=10)
            (self.base/'application-exits.log').open('a').write(str(code)+'\n')
            self.process=None;self.stream.close()
    def http(self,method,path,body=None):
        data=None if body is None else json.dumps(body).encode()
        request=urllib.request.Request('http://127.0.0.1:'+str(self.port)+path,data=data,method=method,headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json','X-Request-ID':'packaged-app-test'})
        try:response=urllib.request.urlopen(request,timeout=5)
        except urllib.error.HTTPError as e:response=e
        with response:
            assert response.headers['X-Request-ID']=='packaged-app-test'
            result=json.loads(response.read())
            return response.status,result
    def smoke(self):
        self.start_app('before-restart')
        status,route=self.http('POST','/routes',{'routeId':'demo-process-restart','name':'DEMO process restart'})
        assert status==201,(status,route)
        definition={'routeId':'demo-process-restart','version':1,'dslVersion':'1','engineSemanticsVersion':'1','adapterContractVersion':'1','root':{'id':'root','type':'SEQUENCE','children':[]}}
        status,draft=self.http('POST','/routes/demo-process-restart/versions',{'definition':definition});assert status==201
        status,published=self.http('POST','/routes/demo-process-restart/versions/1/publish',{'stateVersion':0});assert status==200
        status,reject=self.http('POST','/executions',{});assert status==422 and reject['code']=='INVALID_REQUEST'
        status,recovery=self.http('POST','/executions/future/recoveries',{});assert status==422 and recovery['code']=='INVALID_REQUEST'
        self.stop_app()
        before=self.sql("SELECT CONCAT(definition_hash,':',status) FROM route_versions WHERE route_id='demo-process-restart' AND version=1")
        self.command(['docker','restart',self.name],'real-database-restart')
        self.wait_db()
        self.record_database_endpoint('after-restart')
        assert self.database_endpoints[0]['container_id']==self.database_endpoints[-1]['container_id'],'Restart must retain the same database container'
        after=self.sql("SELECT CONCAT(definition_hash,':',status) FROM route_versions WHERE route_id='demo-process-restart' AND version=1")
        assert before==after and after.endswith(':PUBLISHED')
        self.start_app('after-restart')
        status,read=self.http('GET','/routes/demo-process-restart/versions/1')
        assert status==200 and read==published
        status,health=self.http('GET','/actuator/health');assert status==200 and health['status']=='UP'
        (self.base/'process-restart-proof.json').write_text(json.dumps({'database_image':(ROOT/'config/mariadb-image.txt').read_text().strip(),'database_container':self.name,'actual_database_restart':True,'database_endpoints':self.database_endpoints,'separate_application_processes':True,'definition_hash':read['definitionHash'],'before_database_restart':before,'after_database_restart':after,'route_version':read},indent=2)+'\n')
    def cleanup(self):
        self.stop_app()
        if self.created:
            owner=json.loads(self.command(['docker','inspect','--format','{{json .Config.Labels}}',self.name],'resource-owner'))
            assert owner.get('route-engine.run-id')==self.run and owner.get('route-engine.purpose')=='foundation-test','Refuse cleanup without exact owner and purpose'
            self.command(['docker','rm','--force','--volumes',self.name],'test-resource-cleanup')
        if self.secret_dir.exists():
            assert self.secret_dir.resolve().is_relative_to((ROOT/'.local').resolve())
            shutil.rmtree(self.secret_dir)

def validate_test_database_isolation(base):
    isolation=json.loads((base/'test-database-isolation.json').read_text())
    assert isolation['main']['container_id']!=isolation['engine']['container_id'] and isolation['main']['url']!=isolation['engine']['url']
    assert isolation['main_engine_executions']==0 and isolation['engine_admission_executions']==0
    assert isolation['engine_executions']>0 and isolation['main_admission_executions']>0
    assert isolation['main_cleanup_verified'] and isolation['engine_cleanup_verified']

def validate_initial_schema_proof(proof,expired):
    assert proof['controlled_certificate_transition'] is True and proof['natural_failure_cause_claimed'] is False
    assert proof['expired'] is expired and proof['initialized'] is (not expired)
    assert proof['same_container'] is True and proof['readiness_preceded_certificate_transition'] is True
    assert proof['tls_verification_preserved'] is True and proof['original_deadline_seconds']==90
    assert 0<proof['elapsed']<90 and proof['not_before'] and proof['not_after']

def validate_m1_reports(base):
    suites=[];names=[]
    for report in sorted((base/'junit').glob('TEST-*.xml')):
        counts=fixed.junit_counts(report)
        if counts['tests']<=0 or any(counts[k] for k in ['failures','errors','skipped']):raise AssertionError('Failed or empty mandatory suite '+report.name)
        suites.append({'name':report.stem,**counts,'report':'junit/'+report.name})
        names += [n.attrib.get('name','') for n in ET.parse(report).getroot().iter('testcase')]
    for rid in ['AC005','AC006','AC007','AC008','AC009','AC010']:
        assert any(name.startswith(rid+'_') for name in names),'Missing actual testcase for '+rid
    assert any('FoundationIT' in s['name'] for s in suites),'No real MariaDB integration suite'
    assert any('DefinitionRulesTest' in s['name'] for s in suites),'No unit suite'
    assert any('FixtureStartup' in s['name'] for s in suites),'No verified TLS startup regression suite'
    assert any('EngineHistoryIT' in s['name'] for s in suites),'No actual legacy migration regression'
    for suffix,expired in [('future',False),('expired',True)]:
        required='test_initial_schema_'+suffix+'_certificate_after_verified_readiness_'+('fails_closed' if expired else 'waits_within_original_deadline')
        assert required in names,'Missing actual initial-schema TLS transition regression'
        location=base/'fixture-startup'/('initial-'+suffix)
        validate_initial_schema_proof(fixed.load_json(location/'initial-schema-proof.json'),expired)
        peer=fixed.load_json(location/'tls-peer-proof.json')
        assert peer['expected_sha256']==peer['actual_sha256'] and peer['verification_enabled'] is True
    validate_test_database_isolation(base)
    return suites

def main():
    base=evidence_path(ROOT,sys.argv[1]);base.mkdir(parents=True,exist_ok=True)
    previous=base/'m0'
    rc=subprocess.run(['bash','scripts/verify-phase.sh','M0',str(previous)],cwd=ROOT).returncode
    if rc:return rc
    report=fixed.load_json(previous/'summary.json')
    summary={'phase':'M1','source_fingerprint':os.environ['ROUTE_SOURCE_FINGERPRINT'],'production_authorized':False,'checks':[{**c,'evidence':'m0/'+c['evidence']} for c in report['checks']],'suites':[{**s,'report':'m0/'+s['report']} for s in report['suites']]}
    fixture=LocalFixture(base)
    engine_base=base/'engine-database';engine_base.mkdir(exist_ok=False)
    engine_fixture=LocalFixture(engine_base)
    isolation={}
    problem=None
    local_xml=ET.Element('testsuite',name='PackagedProcessAcceptance')
    try:
        try:
            fixture.command(['python3','-B','scripts/test_fixture_startup.py',str(base/'fixture-startup')],'fixture-startup-regressions')
        finally:
            report=base/'fixture-startup/TEST-FixtureStartup.xml'
            if report.exists():
                (base/'junit').mkdir(exist_ok=True)
                shutil.copyfile(report,base/'junit/TEST-FixtureStartup.xml')
        fixture.start()
        engine_fixture.start()
        isolation={'main':{'container_id':fixture.database_endpoints[0]['container_id'],'url':fixture.env['ROUTE_DB_URL']},
                   'engine':{'container_id':engine_fixture.database_endpoints[0]['container_id'],'url':engine_fixture.env['ROUTE_DB_URL']}}
        assert isolation['main']['container_id']!=isolation['engine']['container_id'] and isolation['main']['url']!=isolation['engine']['url'],'Engine tests require a distinct fresh real database'
        for key in ['URL','USER','PASSWORD']:fixture.env['ROUTE_ENGINE_TEST_DB_'+key]=engine_fixture.env['ROUTE_DB_'+key]
        (base/'test-database-isolation.json').write_text(json.dumps(isolation,indent=2)+'\n')
        try:
            fixture.command(['./mvnw','-B','clean','verify'],'maven-clean-verify')
            shutil.copyfile(ROOT/'target/operator-output-proof.json',base/'operator-output-proof.json')
        finally:
            (base/'junit').mkdir(exist_ok=True)
            for folder in ['surefire-reports','failsafe-reports']:
                for p in (ROOT/'target'/folder).glob('TEST-*.xml'):shutil.copyfile(p,base/'junit'/p.name)
        isolation['main_engine_executions']=int(fixture.sql("SELECT COUNT(*) FROM executions WHERE route_id LIKE 'demo-engine-%'"))
        isolation['engine_executions']=int(engine_fixture.sql("SELECT COUNT(*) FROM executions WHERE route_id LIKE 'demo-engine-%'"))
        isolation['engine_admission_executions']=int(engine_fixture.sql("SELECT COUNT(*) FROM executions WHERE route_id LIKE 'demo-admit-%'"))
        isolation['main_admission_executions']=int(fixture.sql("SELECT COUNT(*) FROM executions WHERE route_id LIKE 'demo-admit-%'"))
        assert isolation['main_engine_executions']==0 and isolation['engine_admission_executions']==0
        assert isolation['engine_executions']>0 and isolation['main_admission_executions']>0
        fixture.command(['./mvnw','-B','dependency:tree'],'runtime-dependencies')
        case=ET.SubElement(local_xml,'testcase',name='AC010_packagedApplicationAndAC006_realDatabaseRestart',classname='PackagedProcessAcceptance')
        try:fixture.smoke()
        except Exception as e:ET.SubElement(case,'failure').text=repr(e);raise
    except Exception as e:
        problem=e
        (base/'failure.log').write_text(traceback.format_exc())
    finally:
        for name,owned in [('engine',engine_fixture),('main',fixture)]:
            try:
                owned.cleanup()
                isolation[name+'_cleanup_verified']=True
            except Exception as e:
                problem=problem or e
                isolation[name+'_cleanup_verified']=False
                (base/(name+'-cleanup-failure.log')).write_text(traceback.format_exc())
        (base/'test-database-isolation.json').write_text(json.dumps(isolation,indent=2)+'\n')
        (base/'junit').mkdir(exist_ok=True)
        ET.ElementTree(local_xml).write(base/'junit/TEST-PackagedProcessAcceptance.xml',encoding='utf-8',xml_declaration=True)
    try:
        if problem:raise problem
        summary['suites']+=validate_m1_reports(base)
        for num in range(5,11):
            rid='AC-%03d'%num
            proof=base/(rid+'.log')
            matched=[s['report'] for s in summary['suites'] if s['report'].startswith('junit/')]
            proof.write_text('Actual clean Maven build, nonempty unit/real MariaDB HTTP suites and separate packaged process/db restart completed.\nReports: '+', '.join(matched)+'\nSee raw command .log/.exit, empty-database.log, process-restart-proof.json.\n')
            summary['checks'].append({'id':rid,'status':'PASS','evidence':proof.name})
    except Exception as e:
        (base/'failure.log').write_text(traceback.format_exc())
        for num in range(5,11):summary['checks'].append({'id':'AC-%03d'%num,'status':'FAIL','evidence':'failure.log'})
    fixed.atomic_json(base/'summary.json',summary)
    try:fixed.validate_gate(summary,base,fixed.load_json(ROOT/'ai-kit/requirements.json'),'M1',os.environ['ROUTE_SOURCE_FINGERPRINT'])
    except Exception as e:print('M1 FAILED:',e);return 1
    print('M1 cumulative executable checks passed; fresh review pending');return 0
if __name__=='__main__':sys.exit(main())
