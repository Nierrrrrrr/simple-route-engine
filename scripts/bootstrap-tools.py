#!/usr/bin/env python3
"""Install checksum-pinned Linux x86_64 tools only below this checkout's .tools."""
import hashlib, json, os, pathlib, platform, shutil, tarfile, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
if platform.system() != 'Linux' or platform.machine() != 'x86_64':
    raise SystemExit('Only Linux x86_64 / this checkout in WSL2 is supported')
TOOLS = ROOT / '.tools'
TOOLS.mkdir(exist_ok=True)
(TOOLS / 'bin').mkdir(exist_ok=True)
for name, spec in json.loads((ROOT / 'config/tool-downloads.json').read_text()).items():
    archive = TOOLS / (name + '-' + spec['version'] + ('.tar.gz' if spec['archive'] else '.download'))
    if not archive.exists():
        print('DOWNLOAD', name, spec['url'], flush=True)
        with urllib.request.urlopen(spec['url'], timeout=120) as source, archive.with_suffix('.part').open('wb') as dest:
            shutil.copyfileobj(source, dest)
        archive.with_suffix('.part').replace(archive)
    digest = hashlib.new(spec['algorithm'], archive.read_bytes()).hexdigest()
    if digest != spec['digest']:
        raise SystemExit('Checksum mismatch: ' + str(archive))
    if spec['archive']:
        with tarfile.open(archive) as tar:
            tar.extractall(TOOLS, filter='data')
        target = TOOLS / spec['directory']
        link = TOOLS / name
        if link.exists() and not link.is_symlink():
            raise SystemExit('Refusing to replace non-symlink: ' + str(link))
        if not link.is_symlink():
            link.symlink_to(target.name)
    else:
        dest = TOOLS / 'bin' / name
        shutil.copyfile(archive, dest)
        dest.chmod(0o755)
    print('VERIFIED', name, spec['version'], spec['algorithm'], digest, flush=True)
