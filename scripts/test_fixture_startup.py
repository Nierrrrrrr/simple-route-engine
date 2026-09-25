#!/usr/bin/env python3
"""Fixture safety policy tests and real pinned MariaDB TLS regressions. No business DB is mocked."""
import datetime, ipaddress, json, os, pathlib, subprocess, sys, tempfile, time, traceback, unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from foundation_gate import LocalFixture, DatabaseStartupFailure,validate_initial_schema_proof
from gate_common import ROOT
from test_gate import JunitResult

EXACT='ERROR 2026 (HY000): TLS/SSL error: certificate is not yet valid'

class FixturePolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.fixture=LocalFixture(pathlib.Path(self.temp.name))
    def test_initial_schema_uses_same_deadline_and_exact_read_only_probe(self):
        f=self.fixture;f.created=True;deadline=time.monotonic()+90;state=json.dumps({'Status':'running'})
        with patch.object(f,'command_result',side_effect=[(0,state),(0,''),(1,EXACT),(0,state),(0,''),(0,'0')]) as command,patch('foundation_gate.time.sleep'):
            f.wait_db(deadline,initial_schema=True)
        queries=[c for c in command.call_args_list if c.args[1]=='initial-schema-sql']
        self.assertEqual(len(queries),2);self.assertFalse(f.initialized)
        self.assertTrue(all(c.args[0]==f.sql_args('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()') for c in queries))
        self.assertTrue(all(0<c.kwargs['timeout']<=90 for c in command.call_args_list))
    def test_initial_schema_other_errors_are_immediate(self):
        for error in ['ERROR 2026 (HY000): TLS/SSL error: certificate has expired','ERROR 1045 (28000): Access denied','ERROR 1064 (42000): invalid SQL','warning\n'+EXACT]:
            with self.subTest(error=error):
                f=self.fixture;f.created=True
                with patch.object(f,'command_result',side_effect=[(0,json.dumps({'Status':'running'})),(0,''),(1,error)]),patch.object(f,'database_diagnostics') as diagnostic,patch('foundation_gate.time.sleep') as sleep:
                    with self.assertRaisesRegex(DatabaseStartupFailure,'sql-error'):f.wait_db(time.monotonic()+90,initial_schema=True)
                sleep.assert_not_called();diagnostic.assert_called_once()
    def test_initial_schema_refuses_used_database_before_any_command(self):
        f=self.fixture;f.created=True;f.initialized=True
        with patch.object(f,'command_result') as command:
            with self.assertRaisesRegex(DatabaseStartupFailure,'fresh-unused'):f.wait_db(initial_schema=True)
        command.assert_not_called()
    def test_initial_schema_refuses_active_application_before_any_command(self):
        f=self.fixture;f.created=True;f.process=object()
        with patch.object(f,'command_result') as command:
            with self.assertRaisesRegex(DatabaseStartupFailure,'fresh-unused'):f.wait_db(initial_schema=True)
        command.assert_not_called();f.process=None
    def test_initial_schema_original_expired_deadline_never_gets_new_budget(self):
        f=self.fixture;f.created=True
        with patch.object(f,'command_result') as command,patch.object(f,'database_diagnostics') as diagnostic:
            with self.assertRaisesRegex(DatabaseStartupFailure,'deadline'):f.wait_db(time.monotonic()-1,initial_schema=True)
        command.assert_not_called();diagnostic.assert_called_once()
    def test_initial_schema_nonempty_database_rejected_without_retry(self):
        f=self.fixture;f.created=True
        with patch.object(f,'command_result',side_effect=[(0,json.dumps({'Status':'running'})),(0,''),(0,'1')]),patch.object(f,'database_diagnostics'),patch('foundation_gate.time.sleep') as sleep:
            with self.assertRaisesRegex(DatabaseStartupFailure,'unexpected-sql-result'):f.wait_db(initial_schema=True)
        sleep.assert_not_called()
    def test_initial_schema_proof_cannot_disable_tls_or_accept_expired_start(self):
        proof={'controlled_certificate_transition':True,'natural_failure_cause_claimed':False,'expired':False,'initialized':True,'same_container':True,'readiness_preceded_certificate_transition':True,'tls_verification_preserved':True,'original_deadline_seconds':90,'elapsed':40,'not_before':'fixture-date','not_after':'fixture-date'}
        validate_initial_schema_proof(proof,False)
        for changed in [dict(proof,tls_verification_preserved=False),dict(proof,initialized=False),dict(proof,elapsed=91),dict(proof,original_deadline_seconds=100)]:
            with self.assertRaises(AssertionError):validate_initial_schema_proof(changed,False)
    def test_same_sql_transport_waits_only_exact_not_yet_valid(self):
        f=self.fixture;state=json.dumps({'Status':'running'})
        with patch.object(f,'command_result',side_effect=[(0,state),(0,''),(1,EXACT),(0,state),(0,''),(0,'1')]) as command,patch('foundation_gate.time.sleep'):
            f.wait_db()
        calls=[c for c in command.call_args_list if c.args[1]=='readiness-sql']
        self.assertEqual(len(calls),2)
        self.assertTrue(all(c.args[0]==f.sql_args('SELECT 1') for c in calls))
    def error_is_immediate(self,message):
        f=self.fixture;state=json.dumps({'Status':'running'})
        with patch.object(f,'command_result',side_effect=[(0,state),(0,''),(1,message)]),patch.object(f,'database_diagnostics') as diagnostic,patch('foundation_gate.time.sleep') as sleep:
            with self.assertRaisesRegex(DatabaseStartupFailure,'sql-error'):f.wait_db()
        diagnostic.assert_called_once();sleep.assert_not_called()
    def test_expired_certificate_is_not_retried(self):self.error_is_immediate('ERROR 2026 (HY000): TLS/SSL error: certificate has expired')
    def test_authentication_error_is_not_retried(self):self.error_is_immediate('ERROR 1045 (28000): Access denied for user')
    def test_sql_error_is_not_retried(self):self.error_is_immediate('ERROR 1064 (42000): invalid SQL')
    def test_warning_plus_tls_error_is_not_silently_swallowed(self):self.error_is_immediate('config ignored\n'+EXACT)
    def test_expired_budget_saves_diagnostics_without_new_attempt(self):
        f=self.fixture
        with patch.object(f,'command_result') as command,patch.object(f,'database_diagnostics') as diagnostic:
            with self.assertRaisesRegex(DatabaseStartupFailure,'deadline'):f.wait_db(time.monotonic()-1)
        command.assert_not_called();diagnostic.assert_called_once()
    def test_initialization_has_at_most_two_attempts_and_one_deadline(self):
        f=self.fixture;deadline=time.monotonic()+90
        error=DatabaseStartupFailure('tls-not-yet-valid',{'Status':'exited'})
        def discard():f.created=False
        with patch.object(f,'command_result',return_value=(0,'')) as create,patch.object(f,'wait_db',side_effect=error) as wait,patch.object(f,'_remove_failed_initialization',side_effect=discard) as remove:
            with self.assertRaisesRegex(DatabaseStartupFailure,'tls-not-yet-valid'):f._initialize_database(['docker','run'],deadline)
        self.assertEqual(create.call_count,2);remove.assert_called_once()
        self.assertEqual([c.args for c in wait.call_args_list],[(deadline,),(deadline,)])
        self.assertFalse(f.initializing)
    def test_docker_client_timeout_tracks_owned_partial_creation_without_retry(self):
        f=self.fixture;labels={'route-engine.run-id':f.run,'route-engine.purpose':'foundation-test'}
        with patch.object(f,'command_result',side_effect=[(124,''),(0,json.dumps(labels))]) as command,patch.object(f,'database_diagnostics') as diagnostic:
            with self.assertRaisesRegex(DatabaseStartupFailure,'docker-run'):f._initialize_database(['docker','run'],time.monotonic()+90)
        self.assertTrue(f.created);self.assertEqual(command.call_count,2);diagnostic.assert_called_once()
    def test_failed_creation_does_not_claim_foreign_container_for_cleanup(self):
        f=self.fixture;labels={'route-engine.run-id':'other','route-engine.purpose':'foundation-test'}
        with patch.object(f,'command_result',side_effect=[(1,''),(0,json.dumps(labels))]),patch.object(f,'database_diagnostics') as diagnostic:
            with self.assertRaisesRegex(DatabaseStartupFailure,'docker-run'):f._initialize_database(['docker','run'],time.monotonic()+90)
        self.assertFalse(f.created);diagnostic.assert_not_called()
    def test_other_entrypoint_error_never_recreates(self):
        f=self.fixture
        with patch.object(f,'command_result',return_value=(0,'')),patch.object(f,'wait_db',side_effect=DatabaseStartupFailure('entrypoint-exited',{'Status':'exited'})),patch.object(f,'_remove_failed_initialization') as remove:
            with self.assertRaisesRegex(DatabaseStartupFailure,'entrypoint-exited'):f._initialize_database(['docker','run'],time.monotonic()+90)
        remove.assert_not_called()
    def test_used_database_never_recreates_even_for_matching_tls_error(self):
        f=self.fixture;f.initialized=True;f.initializing=True
        with patch.object(f,'command') as command:
            with self.assertRaisesRegex(AssertionError,'used database'):f._remove_failed_initialization()
            with self.assertRaisesRegex(AssertionError,'fresh'):f._initialize_database(['docker','run'],time.monotonic()+90)
        command.assert_not_called()
        with patch.object(f,'command_result',side_effect=[(0,json.dumps({'Status':'exited'})),(0,EXACT)]),patch.object(f,'database_diagnostics'),patch.object(f,'_remove_failed_initialization') as remove:
            with self.assertRaisesRegex(DatabaseStartupFailure,'tls-not-yet-valid'):f.wait_db()
        remove.assert_not_called()
    def test_removal_requires_matching_owner_and_purpose(self):
        f=self.fixture;f.initializing=True
        for labels in [{'route-engine.run-id':'other','route-engine.purpose':'foundation-test'},{'route-engine.run-id':f.run,'route-engine.purpose':'other'}]:
            with self.subTest(labels=labels),patch.object(f,'command',return_value=json.dumps(labels)) as command:
                with self.assertRaisesRegex(AssertionError,'owner and purpose'):f._remove_failed_initialization()
                self.assertEqual(command.call_count,1)
    def test_removal_rejects_bind_or_named_volume(self):
        f=self.fixture;f.initializing=True;labels={'route-engine.run-id':f.run,'route-engine.purpose':'foundation-test'}
        for mount in [{'Type':'bind','Destination':'/var/lib/mysql','Name':'a'*64},{'Type':'volume','Destination':'/var/lib/mysql','Name':'named-data'}]:
            with self.subTest(mount=mount),patch.object(f,'command',side_effect=[json.dumps(labels),json.dumps([mount])]) as command:
                with self.assertRaisesRegex(AssertionError,'anonymous'):f._remove_failed_initialization()
                self.assertEqual(command.call_count,2)
    def test_fresh_owned_anonymous_volume_removal_checks_before_mutation(self):
        f=self.fixture;f.initializing=True;f.created=True
        labels={'route-engine.run-id':f.run,'route-engine.purpose':'foundation-test'}
        mounts=[{'Type':'volume','Destination':'/var/lib/mysql','Name':'a'*64}]
        with patch.object(f,'command',side_effect=[json.dumps(labels),json.dumps(mounts),'']) as command:f._remove_failed_initialization()
        self.assertEqual([c.args[1] for c in command.call_args_list],['initialization-owner','initialization-volumes','failed-initialization-cleanup'])
        self.assertFalse(f.created)

def tls_case(base,expired=False):
    # cryptography is a test-only dependency; no production dependency or transport setting changes.
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    base.mkdir(parents=True,exist_ok=False);f=LocalFixture(base)
    try:
        f.start();now=datetime.datetime.now(datetime.timezone.utc)
        valid_at=now+datetime.timedelta(seconds=-120 if expired else 30)
        expires_at=now+datetime.timedelta(seconds=-30 if expired else 3600)
        ca_key=rsa.generate_private_key(public_exponent=65537,key_size=2048);key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        ca_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Isolated Route Engine Test CA')]);name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])
        ca=x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(days=1)).not_valid_after(now+datetime.timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True).sign(ca_key,hashes.SHA256())
        cert=x509.CertificateBuilder().subject_name(name).issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(valid_at).not_valid_after(expires_at).add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False).sign(ca_key,hashes.SHA256())
        for filename,data in [('test-ca.pem',ca.public_bytes(serialization.Encoding.PEM)),('test-server.pem',cert.public_bytes(serialization.Encoding.PEM)),('test-server.key',key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))]:
            path=f.secret_dir/filename;path.write_bytes(data);path.chmod(0o600);f.command(['docker','cp',str(path),f.name+':/var/lib/mysql/'+filename],'copy-'+filename)
        f.command(['docker','exec',f.name,'chown','mysql:mysql','/var/lib/mysql/test-ca.pem','/var/lib/mysql/test-server.pem','/var/lib/mysql/test-server.key'],'certificate-owner')
        f.command(['docker','exec',f.name,'chmod','600','/var/lib/mysql/test-ca.pem','/var/lib/mysql/test-server.pem','/var/lib/mysql/test-server.key'],'certificate-mode')
        config=f.secret_dir/'tls-test.cnf';config.write_text('[mariadbd]\nssl-ca=/var/lib/mysql/test-ca.pem\nssl-cert=/var/lib/mysql/test-server.pem\nssl-key=/var/lib/mysql/test-server.key\n[client]\nssl-ca=/var/lib/mysql/test-ca.pem\nssl-verify-server-cert=on\n')
        f.command(['docker','cp',str(config),f.name+':/etc/mysql/mariadb.conf.d/99-tls-test.cnf'],'verified-tls-config')
        f.command(['docker','exec',f.name,'chmod','644','/etc/mysql/mariadb.conf.d/99-tls-test.cnf'],'secure-config-mode')
        f.command(['docker','exec',f.name,'chown','root:root','/etc/mysql/mariadb.conf.d/99-tls-test.cnf'],'secure-config-owner')
        identity=f.command(['docker','inspect','--format','{{.Id}}',f.name],'identity-before')
        f.command(['docker','restart',f.name],'restart-with-test-certificate')
        # This observes the existing healthcheck's readiness, without mistaking it for verified SQL readiness.
        deadline=time.monotonic()+20
        while True:
            code,_=f.command_result(['docker','exec',f.name,'healthcheck.sh','--connect','--innodb_initialized'],'tls-setup-health')
            if code==0:break
            assert time.monotonic()<deadline;time.sleep(.25)
        endpoint=f.command(['docker','port',f.name,'3306/tcp'],'tls-peer-endpoint')
        args=['openssl','s_client','-starttls','mysql','-connect',endpoint,'-showcerts']
        peer=subprocess.run(args,input='',capture_output=True,text=True,timeout=10)
        (base/'tls-peer.command.json').write_text(json.dumps(args)+'\n');(base/'tls-peer.log').write_text(peer.stdout+peer.stderr);(base/'tls-peer.exit').write_text(str(peer.returncode)+'\n')
        assert peer.returncode==0
        peer_cert=x509.load_pem_x509_certificate(peer.stdout[peer.stdout.index('-----BEGIN CERTIFICATE-----'):].encode())
        assert peer_cert.fingerprint(hashes.SHA256())==cert.fingerprint(hashes.SHA256())
        (base/'tls-peer-proof.json').write_text(json.dumps({'expected_sha256':cert.fingerprint(hashes.SHA256()).hex(),'actual_sha256':peer_cert.fingerprint(hashes.SHA256()).hex(),'not_before':valid_at.isoformat(),'not_after':expires_at.isoformat(),'verification_enabled':True})+'\n')
        started=time.monotonic()
        if expired:
            try:f.wait_db();raise AssertionError('Expired certificate must fail readiness')
            except DatabaseStartupFailure as error:assert error.reason=='sql-error',error
            assert time.monotonic()-started<15,'Non-retryable certificate error was swallowed'
            logs='\n'.join(p.read_text() for p in base.glob('raw-*-readiness-sql.log'))
            assert 'TLS/SSL error: certificate has expired' in logs,logs
        else:
            assert datetime.datetime.now(datetime.timezone.utc)<valid_at,'Setup took too long to exercise future certificate'
            f.wait_db();assert f.sql('SELECT 1')=='1'
            actual=f.sql("SHOW GLOBAL STATUS LIKE 'Ssl_server_not_before'")
            assert valid_at.strftime('%b %d %H:%M:%S %Y GMT') in actual,actual
            assert 'TLS_' in f.sql("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
            logs='\n'.join(p.read_text() for p in base.glob('raw-*-readiness-sql.log'))
            assert EXACT in logs,'No actual future certificate verification failure exercised'
        assert f.command(['docker','inspect','--format','{{.Id}}',f.name],'identity-after')==identity
        (base/'result.json').write_text(json.dumps({'same_container':True,'expired':expired,'elapsed':time.monotonic()-started,'tls_verification_preserved':True})+'\n')
    except Exception:
        (base/'failure.log').write_text(traceback.format_exc());raise
    finally:
        if f.created:f.database_diagnostics()
        f.cleanup()

def install_initial_transition_certificate(f,base,expired):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    now=datetime.datetime.now(datetime.timezone.utc)
    valid_at=now+datetime.timedelta(seconds=-120 if expired else 30)
    expires_at=now+datetime.timedelta(seconds=-30 if expired else 3600)
    ca_key=rsa.generate_private_key(public_exponent=65537,key_size=2048);key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    ca_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Isolated Route Engine Test CA')]);name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])
    ca=x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(days=1)).not_valid_after(now+datetime.timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True).sign(ca_key,hashes.SHA256())
    cert=x509.CertificateBuilder().subject_name(name).issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(valid_at).not_valid_after(expires_at).add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False).sign(ca_key,hashes.SHA256())
    for filename,data in [('test-ca.pem',ca.public_bytes(serialization.Encoding.PEM)),('test-server.pem',cert.public_bytes(serialization.Encoding.PEM)),('test-server.key',key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))]:
        path=f.secret_dir/filename;path.write_bytes(data);path.chmod(0o600);f.command(['docker','cp',str(path),f.name+':/var/lib/mysql/'+filename],'copy-'+filename)
    f.command(['docker','exec',f.name,'chown','mysql:mysql','/var/lib/mysql/test-ca.pem','/var/lib/mysql/test-server.pem','/var/lib/mysql/test-server.key'],'certificate-owner')
    f.command(['docker','exec',f.name,'chmod','600','/var/lib/mysql/test-ca.pem','/var/lib/mysql/test-server.pem','/var/lib/mysql/test-server.key'],'certificate-mode')
    config=f.secret_dir/'tls-test.cnf';config.write_text('[mariadbd]\nssl-ca=/var/lib/mysql/test-ca.pem\nssl-cert=/var/lib/mysql/test-server.pem\nssl-key=/var/lib/mysql/test-server.key\n[client]\nssl-ca=/var/lib/mysql/test-ca.pem\nssl-verify-server-cert=on\n')
    f.command(['docker','cp',str(config),f.name+':/etc/mysql/mariadb.conf.d/99-tls-test.cnf'],'verified-tls-config')
    f.command(['docker','exec',f.name,'chmod','644','/etc/mysql/mariadb.conf.d/99-tls-test.cnf'],'secure-config-mode')
    f.command(['docker','exec',f.name,'chown','root:root','/etc/mysql/mariadb.conf.d/99-tls-test.cnf'],'secure-config-owner')
    identity=f.command(['docker','inspect','--format','{{.Id}}',f.name],'identity-before')
    f.command(['docker','restart',f.name],'restart-with-test-certificate')
    # This observes the existing healthcheck's readiness, without mistaking it for verified SQL readiness.
    deadline=time.monotonic()+20
    while True:
        code,_=f.command_result(['docker','exec',f.name,'healthcheck.sh','--connect','--innodb_initialized'],'tls-setup-health')
        if code==0:break
        assert time.monotonic()<deadline;time.sleep(.25)
    endpoint=f.command(['docker','port',f.name,'3306/tcp'],'tls-peer-endpoint')
    args=['openssl','s_client','-starttls','mysql','-connect',endpoint,'-showcerts']
    peer=subprocess.run(args,input='',capture_output=True,text=True,timeout=10)
    (base/'tls-peer.command.json').write_text(json.dumps(args)+'\n');(base/'tls-peer.log').write_text(peer.stdout+peer.stderr);(base/'tls-peer.exit').write_text(str(peer.returncode)+'\n')
    assert peer.returncode==0
    peer_cert=x509.load_pem_x509_certificate(peer.stdout[peer.stdout.index('-----BEGIN CERTIFICATE-----'):].encode())
    assert peer_cert.fingerprint(hashes.SHA256())==cert.fingerprint(hashes.SHA256())
    (base/'tls-peer-proof.json').write_text(json.dumps({'expected_sha256':cert.fingerprint(hashes.SHA256()).hex(),'actual_sha256':peer_cert.fingerprint(hashes.SHA256()).hex(),'not_before':valid_at.isoformat(),'not_after':expires_at.isoformat(),'verification_enabled':True})+'\n')
    return identity,valid_at,expires_at

def initial_schema_tls_case(base,expired=False):
    base.mkdir(parents=True,exist_ok=False)
    class TransitionFixture(LocalFixture):
        def record_database_endpoint(self,stage):
            super().record_database_endpoint(stage)
            if stage=='initial':
                assert not self.initialized and self.process is None
                assert self.sql('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()')=='0'
                self.transition=install_initial_transition_certificate(self,base,expired)
                self.transition_completed=time.monotonic()
    f=TransitionFixture(base);started=time.monotonic();caught=None
    try:
        try:f.start()
        except Exception as error:
            if not hasattr(f,'transition'):raise
            caught=error
        logs='\n'.join(p.read_text() for p in base.glob('raw-*-*.log'))
        if expired:
            assert caught is not None and not f.initialized,'Expired initial certificate must fail closed'
            assert 'TLS/SSL error: certificate has expired' in logs
            assert time.monotonic()-f.transition_completed<15,'Expired initial certificate was retried'
        else:
            if caught:raise AssertionError('Verified readiness must not bypass bounded verification of the first empty-schema query: '+str(caught)) from caught
            assert f.initialized and time.monotonic()-started<90
            assert EXACT in '\n'.join(p.read_text() for p in base.glob('raw-*-initial-schema-sql.log')),'Must exercise actual post-readiness initial-schema TLS not-yet-valid'
            assert f.sql('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()')=='0'
            assert 'TLS_' in f.sql("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
        identity,valid_at,expires_at=f.transition
        assert f.command(['docker','inspect','--format','{{.Id}}',f.name],'initial-transition-identity-after')==identity
        assert any(p.read_text().strip()=='1' for p in base.glob('raw-*-readiness-sql.log')),'Initial verified readiness was not observed'
        (base/'initial-schema-proof.json').write_text(json.dumps({'controlled_certificate_transition':True,'natural_failure_cause_claimed':False,'expired':expired,'same_container':True,'readiness_preceded_certificate_transition':True,'initialized':f.initialized,'tls_verification_preserved':True,'original_deadline_seconds':90,'elapsed':time.monotonic()-started,'not_before':valid_at.isoformat(),'not_after':expires_at.isoformat()})+'\n')
    except Exception:
        (base/'failure.log').write_text(traceback.format_exc());raise
    finally:
        if f.created:f.database_diagnostics()
        f.cleanup()

class RealTlsTests(unittest.TestCase):
    evidence=None
    def test_initial_schema_future_certificate_after_verified_readiness_waits_within_original_deadline(self):initial_schema_tls_case(self.evidence/"initial-future")
    def test_initial_schema_expired_certificate_after_verified_readiness_fails_closed(self):initial_schema_tls_case(self.evidence/"initial-expired",expired=True)
    def test_future_certificate_blocks_readiness_until_original_verified_sql_succeeds(self):tls_case(self.evidence/'future')
    def test_expired_certificate_fails_immediately_preserves_same_database_and_diagnostics(self):tls_case(self.evidence/'expired',expired=True)

if __name__=='__main__':
    base=pathlib.Path(sys.argv[1]);base.mkdir(parents=True,exist_ok=False);RealTlsTests.evidence=base
    import cryptography
    versions=json.loads((ROOT/'config/test-tools.json').read_text())
    assert cryptography.__version__==versions['pythonCryptography'],'Pinned test cryptography version required'
    args=['dpkg-query','-W','-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\n',*versions['packages']]
    inventory=subprocess.run(args,capture_output=True,text=True)
    (base/'test-tools.command.json').write_text(json.dumps(args)+'\n');(base/'test-tools.log').write_text(inventory.stdout+inventory.stderr);(base/'test-tools.exit').write_text(str(inventory.returncode)+'\n')
    assert inventory.returncode==0,'Existing pinned Ubuntu test packages required'
    actual={line.split('\t')[0]:line.split('\t')[1] for line in inventory.stdout.splitlines()}
    assert actual==versions['packages'],(actual,versions['packages'])
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(FixturePolicyTests),unittest.defaultTestLoader.loadTestsFromTestCase(RealTlsTests)])
    result=unittest.TextTestRunner(verbosity=2,resultclass=JunitResult).run(suite)
    xml=ET.Element('testsuite',name='FixtureStartup',tests=str(result.testsRun),failures=str(len(result.failures)),errors=str(len(result.errors)),skipped=str(len(result.skipped)))
    for _,case in result.cases:xml.append(case)
    ET.ElementTree(xml).write(base/'TEST-FixtureStartup.xml',encoding='utf-8',xml_declaration=True)
    sys.exit(0 if result.wasSuccessful() else 1)