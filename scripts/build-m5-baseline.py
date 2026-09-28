#!/usr/bin/env python3
"""Rebuild only the archived accepted historical source; never current engine source."""
import hashlib,json,os,pathlib,subprocess,tarfile,sys
from gate_common import ROOT,fixed,evidence_path

def build(base):
 base=evidence_path(ROOT,base);base.mkdir(parents=True,exist_ok=False);work=base/'source';work.mkdir()
 spec=json.loads((ROOT/'config/upgrade/m5-fixture.json').read_text());archive=ROOT/'config/upgrade/m5-source.tar.gz'
 assert hashlib.sha256(archive.read_bytes()).hexdigest()==spec['historicalArchiveSha256']
 with tarfile.open(archive) as bundle:bundle.extractall(work,filter='data')
 source=fixed.source_fingerprint(work);assert source==spec['sourceFingerprint'],(source,spec['sourceFingerprint'])
 os.chmod(work/'mvnw',0o755);args=['./mvnw','-B','-Dmaven.test.skip=true','package']
 (base/'command.json').write_text(json.dumps(args))
 with (base/'build.log').open('w') as out:r=subprocess.run(args,cwd=work,env=dict(os.environ),stdout=out,stderr=subprocess.STDOUT)
 (base/'build.exit').write_text(str(r.returncode));assert r.returncode==0
 assert fixed.source_fingerprint(work)==source
 jar=work/'target/route-engine-0.1.0.jar';actual=hashlib.sha256(jar.read_bytes()).hexdigest()
 provenance={'mode':'PINNED_HISTORICAL_SOURCE_REBUILD','sourceFingerprint':source,'sourceCommit':spec['historicalSourceCommit'],'archiveSha256':spec['historicalArchiveSha256'],'jarSha256':actual,'jarBytes':jar.stat().st_size,'acceptedJarSha256':spec['jarSha256'],'claimsExactAcceptedJar':False,'jarPath':str(jar)}
 (base/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');return jar,provenance
if __name__=='__main__':build(pathlib.Path(sys.argv[1]).resolve())
