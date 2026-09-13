import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import quote
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAMES = {
    'api-usage-console': 'API Usage Console',
    'codex-window-keeper': 'Codex Window Keeper',
}


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def api(endpoint, method='GET', body=None, allow_missing=False):
    args = ['gh', 'api', '--method', method, endpoint]
    if body is not None:
        args += ['--input', '-']
    result = subprocess.run(args, input=json.dumps(body) if body is not None else None,
                            capture_output=True, text=True)
    if result.returncode:
        if allow_missing and '(HTTP 404)' in result.stderr:
            return None
        raise RuntimeError(f'GitHub request failed: {method} {endpoint}')
    return json.loads(result.stdout) if result.stdout else None


def digest(data):
    return hashlib.sha256(data).hexdigest()


def version_tuple(version):
    if not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', version):
        raise ValueError('Expected a stable X.Y.Z version')
    return tuple(map(int, version.split('.')))


def archive_bytes(files):
    import io
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, files[name])
    return out.getvalue()


def extract(plugin, version, arch, temp):
    image = f'ghcr.io/siriusrry/{plugin}:{version}'
    run('docker', 'pull', '--platform', f'linux/{arch}', image)
    identity = json.loads(run('docker', 'image', 'inspect', image))[0]
    labels = identity['Config']['Labels']
    if identity['Os'] != 'linux' or identity['Architecture'] != arch or labels['org.opencontainers.image.version'] != version:
        raise ValueError('Image identity mismatch')
    container = run('docker', 'create', '--platform', f'linux/{arch}', identity['Id'])
    directory = temp / arch
    directory.mkdir()
    paths = {
        plugin + '.so': '/release/' + plugin + '.so',
        'metadata.json': '/release/metadata.json',
        'LICENSE': '/licenses/LICENSE',
        'THIRD_PARTY_NOTICES': '/licenses/THIRD_PARTY_NOTICES',
    }
    try:
        for name, source in paths.items():
            run('docker', 'cp', f'{container}:{source}', str(directory / name))
    finally:
        run('docker', 'rm', container)
    metadata = json.loads((directory / 'metadata.json').read_text())
    library = (directory / (plugin + '.so')).read_bytes()
    expected = dict(plugin_id=plugin, version=version, filename=plugin+'.so', os='linux', architecture=arch)
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError('Plugin metadata mismatch')
    if digest(library) != metadata['sha256']:
        raise ValueError('Plugin checksum mismatch')
    machine = 62 if arch == 'amd64' else 183
    if library[:6] != b'\x7fELF\x02\x01' or int.from_bytes(library[18:20], 'little') != machine:
        raise ValueError('Plugin architecture mismatch')
    files = {name: (directory / name).read_bytes() for name in paths if name != 'metadata.json'}
    if not all(files.values()):
        raise ValueError('Empty artifact or license')
    return archive_bytes(files), metadata['sha256']


def merge_registry(registry, entry):
    if registry.get('schema_version') != 2:
        raise ValueError('Unexpected registry schema')
    plugins = registry['plugins']
    existing = next((p for p in plugins if p['id'] == entry['id']), None)
    if existing:
        old_version, new_version = version_tuple(existing['version']), version_tuple(entry['version'])
        if new_version < old_version:
            raise ValueError('Refusing to downgrade registry')
        if new_version == old_version:
            if existing['install'] != entry['install']:
                raise ValueError('Version artifacts are immutable')
            return registry
        entry['versions'] = [
            {'version': existing['version'], 'install': existing['install']},
            *existing.get('versions', []),
        ]
        plugins.remove(existing)
    plugins.append(entry)
    plugins.sort(key=lambda p: p['id'])
    return registry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plugin', choices=NAMES, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--repo', default='Siriusrry/cpa-assets')
    args = parser.parse_args()
    version_tuple(args.version)
    if args.repo != 'Siriusrry/cpa-assets':
        raise ValueError('Unexpected target repository')
    if run('git', 'branch', '--show-current') != 'plugins':
        raise ValueError('Publication requires the plugins branch')
    if run('git', 'status', '--porcelain'):
        raise ValueError('Publication requires a clean checkout')
    base = f'repos/{args.repo}'
    latest_id = api(base + '/releases/latest')['id']
    registry = json.loads((ROOT / 'registry.json').read_text())
    existing = next((p for p in registry['plugins'] if p['id'] == args.plugin), None)
    if existing and version_tuple(args.version) < version_tuple(existing['version']):
        raise ValueError('Refusing to downgrade registry')
    tag = f'{args.plugin}/v{args.version}'
    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        archives = {}
        hashes = {}
        for arch in ('amd64', 'arm64'):
            name = f'{args.plugin}_{args.version}_linux_{arch}.zip'
            archives[name], hashes[arch] = extract(args.plugin, args.version, arch, temp)
        target = run('git', 'rev-parse', 'HEAD')
        release = api(base + '/releases/tags/' + quote(tag, safe=''), allow_missing=True)
        if release is None:
            release = api(base + '/releases', 'POST', {
                'tag_name': tag, 'target_commitish': target, 'name': tag,
                'body': '', 'draft': True, 'prerelease': False, 'make_latest': 'false',
            })
        if release['tag_name'] != tag or release.get('body') or release['prerelease']:
            raise ValueError('Unexpected release identity')
        allowed = set(archives)
        if any(a['name'] not in allowed for a in release['assets']):
            raise ValueError('Unexpected release asset')
        assets = {a['name']: a for a in release['assets']}
        for name, data in archives.items():
            expected = digest(data)
            if name in assets:
                remote = subprocess.check_output(['gh','api',f"{base}/releases/assets/{assets[name]['id']}",'-H','Accept: application/octet-stream'])
                if digest(remote) != expected:
                    raise ValueError('Published archive is immutable')
            elif release['draft']:
                path = temp / name
                path.write_bytes(data)
                run('gh','release','upload',tag,str(path),'--repo',args.repo)
            else:
                raise ValueError('Published release is incomplete')
        release = api(f"{base}/releases/{release['id']}")
        artifacts = []
        for arch in ('amd64','arm64'):
            name = f'{args.plugin}_{args.version}_linux_{arch}.zip'
            asset = next(a for a in release['assets'] if a['name'] == name)
            remote = subprocess.check_output(['gh','api',f"{base}/releases/assets/{asset['id']}",'-H','Accept: application/octet-stream'])
            if remote != archives[name]:
                raise ValueError('Release upload verification failed')
            artifacts.append({'goos':'linux','goarch':arch,'url':asset['browser_download_url'],
                              'sha256':digest(remote),'size':len(remote)})
        if release['draft']:
            release = api(f"{base}/releases/{release['id']}", 'PATCH', {'draft':False,'make_latest':'false','body':''})
        else:
            release = api(f"{base}/releases/{release['id']}")
        # Draft assets use temporary untagged URLs; resolve published URLs last.
        published_assets = {a['name']: a for a in release['assets']}
        for artifact in artifacts:
            name = f'{args.plugin}_{args.version}_linux_{artifact["goarch"]}.zip'
            artifact['url'] = published_assets[name]['browser_download_url']
        if api(base + '/releases/latest')['id'] != latest_id:
            raise ValueError('Frontend latest release changed')
        entry = {'id':args.plugin,'name':NAMES[args.plugin],'description':NAMES[args.plugin],
                 'author':'Siriusrry','version':args.version,
                 'install':{'type':'direct','artifacts':artifacts}}
        result = merge_registry(registry, entry)
        (ROOT / 'registry.json').write_text(json.dumps(result,indent=2)+'\n')
        if run('git','status','--porcelain'):
            run('git','add','--','registry.json')
            run('git','-c','user.name=Siriusrry','-c','user.email=Siriusrry@users.noreply.github.com',
                'commit','-m',f'chore: {args.plugin} {args.version}')
            run('git','push','origin','HEAD:plugins')
        if api(base + '/releases/latest')['id'] != latest_id:
            raise ValueError('Frontend latest release changed')
        print(json.dumps({'plugin':args.plugin,'version':args.version,'artifact_sha256':hashes,
                          'frontend_latest_unchanged':True}))


if __name__ == '__main__':
    main()
