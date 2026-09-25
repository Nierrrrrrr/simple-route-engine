#!/usr/bin/env python3
"""Real isolated tooling, network, Docker and kind readiness checks."""
import datetime, hashlib, json, os, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

def validate_doctor(data):
    required={'git','bash','python','java','maven-wrapper','kind','kubectl','docker','network','workspace','cluster-ready'}
    assert set(data['checks']) == required, 'Missing doctor checks'
    for name, check in data['checks'].items():
        assert check['exit'] == 0 and check['output'].strip(), 'Failed tool requirement: '+name
    assert '21.0.12.1' in data['checks']['java']['output'], 'Wrong Java version'
    assert 'Apache Maven 3.9.11' in data['checks']['maven-wrapper']['output'], 'Wrong Maven version'
    assert 'v0.33.0' in data['checks']['kind']['output'], 'Wrong kind version'
    assert 'v1.36.4' in data['checks']['kubectl']['output'], 'Wrong kubectl version'
    assert 'condition met' in data['checks']['cluster-ready']['output'], 'Cluster not ready'
    assert data['docker_host']=='unix:///var/run/docker.sock', 'Unapproved Docker endpoint'
    assert data['production_authorized'] is False

def main():
    base=pathlib.Path(sys.argv[1]).resolve()
    if not base.is_relative_to(ROOT/'.evidence'):
        raise SystemExit('Evidence must be below repository .evidence')
    base.mkdir(parents=True,exist_ok=True)
    data={'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':{},
          'docker_host':os.environ['DOCKER_HOST'],'kubeconfig':os.environ['KUBECONFIG'],
          'run_id':os.environ['ROUTE_RUN_ID'],'production_authorized':False}
    if not pathlib.Path(data['kubeconfig']).is_relative_to(ROOT/'.evidence/desktop'/data['run_id']):
        raise SystemExit('Refusing non-run kubeconfig')
    def run(name,args,timeout=120,mandatory=True):
        print('RUN',name,args,flush=True)
        try:
            result=subprocess.run(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
            code,output=result.returncode,result.stdout
        except (OSError,subprocess.TimeoutExpired) as exc:
            code,output=124,str(exc)
        (base/(name+'.log')).write_text('$ '+' '.join(args)+'\n'+output+'\nexit='+str(code)+'\n')
        if mandatory:
            data['checks'][name]={'exit':code,'output':output,'log':name+'.log'}
        if code and mandatory:
            raise RuntimeError(name+' failed, exit '+str(code))
        return code,output
    try:
        probe=base/'workspace-probe.txt'; probe.write_text('workspace-write-read-ok\n')
        data['checks']['workspace']={'exit':0,'output':probe.read_text(),'log':probe.name}
        run('git',['git','--version']);run('bash',['bash','--version']);run('python',['python3','--version'])
        run('java',['java','-version']);run('maven-wrapper',['bash','./mvnw','--version'])
        run('kind',['kind','version']);run('kubectl',['kubectl','version','--client=true','-o','json'])
        run('docker',['docker','info','--format','{{.ServerVersion}} {{.OSType}}'])
        assert 'linux' in data['checks']['docker']['output'], 'Docker must run Linux containers'
        run('network',['curl','--fail','--silent','--show-error','--head','https://repo.maven.apache.org/maven2/org/springframework/boot/spring-boot-dependencies/3.5.16/spring-boot-dependencies-3.5.16.pom'])
        cluster=os.environ['ROUTE_CLUSTER']; node=cluster+'-control-plane'
        code,out=run('cluster-owner',['docker','inspect','--format','{{ index .Config.Labels "io.x-k8s.kind.cluster" }}',node],mandatory=False)
        if code:
            versions=json.loads((ROOT/'config/versions.json').read_text())
            code,out=run('cluster-create',['kind','create','cluster','--name',cluster,'--image',versions['kindNodeImage'],'--kubeconfig',data['kubeconfig'],'--wait','180s'],timeout=600,mandatory=False)
            if code: raise RuntimeError('kind cluster create failed: '+str(code))
        elif out.strip()!=cluster:
            raise RuntimeError('Cluster node ownership mismatch')
        else:
            code,out=run('cluster-kubeconfig',['kind','export','kubeconfig','--name',cluster,'--kubeconfig',data['kubeconfig']],mandatory=False)
            if code: raise RuntimeError('Cannot export test kubeconfig')
        run('cluster-ready',['kubectl','--kubeconfig',data['kubeconfig'],'--context','kind-'+cluster,'wait','--for=condition=Ready','node/'+node,'--timeout=180s'],timeout=200)
        validate_doctor(data)
        data['status']='PASS'
    except Exception as exc:
        data['status']='FAIL';data['error']=str(exc)
        print('DOCTOR FAILED',str(exc),flush=True)
    (base/'doctor.json').write_text(json.dumps(data,indent=2)+'\n')
    return 0 if data['status']=='PASS' else 1

if __name__=='__main__':
    sys.exit(main())
