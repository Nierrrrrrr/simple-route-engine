#!/usr/bin/env python3
"""Create a nonsecret adapter catalog and protected local shell settings."""
import hashlib
import json
import os
import pathlib
import re
import shlex

root = pathlib.Path(os.environ['PROJECT_DIR']).resolve()
home = pathlib.Path(os.environ['SOP_HOME']).resolve()
image = os.environ['RUNNER_IMAGE']
namespace = os.environ['SOP_NAMESPACE']
context = os.environ['SOP_KUBE_CONTEXT']
kubeconfig = pathlib.Path(os.environ['SOP_KUBECONFIG']).resolve()
dbhost = os.environ['SOP_DB_HOST']
dbport = os.environ.get('SOP_DB_PORT', '3306')
ca = pathlib.Path(os.environ['SOP_DB_CA']).resolve()
assert re.fullmatch(r'.+@sha256:[a-f0-9]{64}', image), 'RUNNER_IMAGE 必須包含真正的映像 digest'
assert re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}', namespace), 'namespace 格式錯誤'
assert re.fullmatch(r'[A-Za-z0-9.-]+', dbhost), '請使用憑證對應的 DNS 主機名稱'
assert dbport.isdigit() and 1 <= int(dbport) <= 65535
assert kubeconfig.is_file() and ca.is_file()
assert all(not c.isspace() and c not in '&?#' for c in str(ca)), 'CA 路徑請避免空白及 URL 保留字元'
assert context.strip()
digest = 'sha256:' + hashlib.sha256((root/'config/runner/playbooks/probe.yml').read_bytes()).hexdigest()
catalog = {
    'endpoints': {'sop.rest': {
        'baseUri': 'http://127.0.0.1:9081/operations', 'allowedHost': '127.0.0.1',
        'allowLoopbackHttp': True, 'timeoutMillis': 5000, 'maxResponseBytes': 65536,
        'query': True, 'cancel': False}},
    'resources': {'sop.probe': {
        'kind': 'ANSIBLE', 'namespace': namespace, 'image': image,
        'runId': 'ubuntu-sop', 'artifactDigest': digest, 'pvc': 'runner-artifacts',
        'playbook': 'probe', 'secretName': 'runner-probe', 'imagePullPolicy': 'IfNotPresent'}},
    'kubernetes': {'kubeconfig': str(kubeconfig), 'context': context}}
home.mkdir(parents=True, exist_ok=True)
(home/'logs').mkdir(exist_ok=True)
(home/'adapter-catalog.json').write_text(json.dumps(catalog, indent=2)+'\n')
common = {'PROJECT_DIR': str(root), 'SOP_HOME': str(home), 'API_BASE': 'http://127.0.0.1:8080',
          'SOP_NAMESPACE': namespace, 'SOP_KUBE_CONTEXT': context,
          'SOP_KUBECONFIG': str(kubeconfig), 'SOP_DB_HOST': dbhost, 'SOP_DB_PORT': dbport,
          'SOP_DB_CA': str(ca), 'RUNNER_IMAGE': image}
settings = {
    **common, 'ROUTE_DB_URL': f'jdbc:mariadb://{dbhost}:{dbport}/route_engine_sop?sslMode=verify-full&serverSslCert={ca}',
    'ROUTE_DB_USER': 're_sop_app', 'SPRING_FLYWAY_ENABLED': 'false',
    'ROUTE_BIND_ADDRESS': '127.0.0.1', 'ROUTE_PORT': '8080',
    'ROUTE_ADAPTERS_CONFIG': str(home/'adapter-catalog.json'),
    'ROUTE_LOG_FILE': str(home/'logs/route-engine.log'),
    'ROUTE_ADMIN_TOKEN_SHA256': hashlib.sha256((home/'admin-token.txt').read_text().strip().encode()).hexdigest(),
    'ROUTE_SCHEDULER_ENABLED': 'true', 'ROUTE_ENGINE_ENABLED': 'true'}
for name, values in [('session.env', common), ('app.env', settings)]:
    path = home/name
    path.write_text(''.join(f'export {k}={shlex.quote(v)}\n' for k,v in values.items()))
    path.chmod(0o600)
print('已建立 adapter-catalog.json、session.env、app.env；未保存 DB 密碼。')
