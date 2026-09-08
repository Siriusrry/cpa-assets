"""Release automation. Only official stable snapshots and reviewed local patches execute."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=ROOT):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def gh_json(path):
    return json.loads(run('gh', 'api', path))


def config():
    return json.loads((ROOT / 'build-config.json').read_text())


def release_tag(tag):
    if not re.fullmatch(r'v\d+\.\d+\.\d+', tag):
        raise ValueError(f'Unrecognized stable upstream tag: {tag!r}')
    return f'{tag}-Siriusrry'


def fingerprint():
    digest = hashlib.sha256()
    paths = [ROOT / 'build-config.json']
    for folder in ['patches', 'scripts', '.github/workflows']:
        paths += sorted(p for p in (ROOT / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    for p in paths:
        digest.update(str(p.relative_to(ROOT)).encode() + b'\0' + p.read_bytes() + b'\0')
    return digest.hexdigest()


def select_release(release):
    if release.get('draft') or release.get('prerelease'):
        raise ValueError('Upstream release is not stable')
    if not any(a['name'] == 'management.html' for a in release.get('assets', [])):
        raise ValueError('Upstream release has no management.html')
    return release_tag(release['tag_name'])


def plan(repo):
    cfg = config()
    upstream = gh_json(f"repos/{cfg['upstream']}/releases/latest")
    tag = select_release(upstream)
    sha = gh_json(f"repos/{cfg['upstream']}/commits/{upstream['tag_name']}")['sha']
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise ValueError('Invalid upstream commit')
    plan = dict(upstream=cfg['upstream'], upstream_tag=upstream['tag_name'], upstream_sha=sha,
                upstream_release_id=upstream['id'], upstream_published_at=upstream['published_at'],
                version=tag, fingerprint=fingerprint(), pipeline_sha=run('git', 'rev-parse', 'HEAD'),
                bun=cfg['bun'], repository=repo, build=True)
    # An authenticated 404 means a first build; transport/auth failures must fail the run.
    response = subprocess.run(['gh', 'api', f'repos/{repo}/releases/tags/{tag}'], text=True, capture_output=True)
    if response.returncode == 0:
        existing = json.loads(response.stdout)
        if not existing['draft']:
            required = {'management.html', 'SHA256SUMS', 'build-info.json', 'source.tar.gz', 'LICENSE'}
            if not required.issubset({a['name'] for a in existing['assets']}):
                raise ValueError('Published release is incomplete; repair manually')
            metadata_url = next(a['url'] for a in existing['assets'] if a['name'] == 'build-info.json')
            info = json.loads(run('gh', 'api', '-H', 'Accept: application/octet-stream', metadata_url))
            if info['upstream_sha'] != plan['upstream_sha']:
                raise ValueError('A published upstream tag moved; review before rebuilding')
            plan['build'] = info['fingerprint'] != plan['fingerprint']
    elif '(HTTP 404)' not in response.stderr:
        raise RuntimeError(f'Release lookup failed: {response.stderr}')
    (ROOT / '.work').mkdir(exist_ok=True)
    (ROOT / '.work/plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as out:
            out.write(f"build={str(plan['build']).lower()}\nversion={tag}\nbun={cfg['bun']}\n")
    print(json.dumps(plan, indent=2))


def load_plan():
    return json.loads((ROOT / '.work/plan.json').read_text())


def prepare():
    plan = load_plan()
    source = ROOT / '.work/source'
    if source.exists():
        raise ValueError('Source workspace already exists; use a fresh checkout')
    source.mkdir()
    run('git', 'init', cwd=source)
    run('git', 'remote', 'add', 'origin', f"https://github.com/{plan['upstream']}.git", cwd=source)
    run('git', 'fetch', '--depth=1', 'origin', plan['upstream_sha'], cwd=source)
    run('git', 'checkout', '--detach', 'FETCH_HEAD', cwd=source)
    if run('git', 'rev-parse', 'HEAD', cwd=source) != plan['upstream_sha']:
        raise ValueError('Source identity mismatch')
    package = json.loads((source / 'package.json').read_text())
    if package.get('packageManager') != f"bun@{plan['bun']}":
        raise ValueError('Upstream Bun version changed; review build-config before publishing')
    base = config()['patch_base']
    if not re.fullmatch('[0-9a-f]{40}', base):
        raise ValueError('Invalid patch base commit')
    # Fetch the original blobs so Git can merge surrounding upstream edits.
    run('git', 'fetch', '--depth=1', 'origin', base, cwd=source)
    patches = sorted((ROOT / 'patches').glob('*.patch'))
    if not patches:
        raise ValueError('No customization patches found')
    for patch in patches:
        # Three-way merge retains compatible upstream edits; real conflicts fail.
        run('git', 'apply', '--3way', str(patch), cwd=source)
    run('git', 'diff', '--cached', '--check', cwd=source)


def package():
    plan = load_plan()
    source = ROOT / '.work/source'
    html = (source / 'dist/index.html').read_text()
    if plan['version'] not in html:
        raise ValueError('Expected Siriusrry version is missing from built HTML')
    if re.search(r'<script\b[^>]*\bsrc\s*=', html, re.I) or re.search(r'<link\b[^>]*rel=["\']stylesheet', html, re.I):
        raise ValueError('Build requires external JS or CSS')
    out = ROOT / 'out'
    out.mkdir(exist_ok=True)
    license_text = (source / 'LICENSE').read_text()
    (out / 'management.html').write_text('<!--\n' + license_text.replace('--', '—') + '\n-->\n' + html)
    (out / 'LICENSE').write_text(license_text)
    info = {**plan, 'built_at': dt.datetime.now(dt.timezone.utc).isoformat()}
    info.pop('build')
    (out / 'build-info.json').write_text(json.dumps(info, indent=2) + '\n')
    with tarfile.open(out / 'source.tar.gz', 'w:gz') as archive:
        # Public source only, no .git, caches, dependencies or compiled assets.
        files = run('git', 'ls-files', '--cached', '--others', '--exclude-standard', cwd=source).splitlines()
        for name in files:
            archive.add(source / name, arcname=f'source/{name}', recursive=False)
    names = ['management.html', 'LICENSE', 'build-info.json', 'source.tar.gz']
    (out / 'SHA256SUMS').write_text(''.join(f'{hashlib.sha256((out / name).read_bytes()).hexdigest()}  {name}\n' for name in names))
    (ROOT / '.work/release-notes.md').write_text(
        f"Based on [{plan['upstream_tag']}](https://github.com/{plan['upstream']}/releases/tag/{plan['upstream_tag']}) "
        f"(`{plan['upstream_sha']}`).\n\n"
        'Adds authentication priority after the Codex reset count, email quota-card/window labels with full filenames on hover, and a Siriusrry version suffix.\n\n'
        'Validation: the official upstream test, lint and TypeScript/build workflow; '
        'single-file HTML/version checks and release attachment round-trip verification.\n\n'
        f"Pipeline source: `{plan['pipeline_sha']}`. Build metadata and corresponding patched source attached.\n")


def publish():
    plan = load_plan()
    repo, tag = plan['repository'], plan['version']
    target = f'repos/{repo}/releases/tags/{tag}'
    response = subprocess.run(['gh', 'api', target], text=True, capture_output=True)
    previous = None
    backup = ROOT / '.work/previous-release'
    if response.returncode:
        if '(HTTP 404)' not in response.stderr:
            raise RuntimeError(response.stderr)
        run('gh', 'release', 'create', tag, '--repo', repo, '--target', plan['pipeline_sha'], '--draft',
            '--title', tag, '--notes-file', str(ROOT / '.work/release-notes.md'))
    elif not json.loads(response.stdout)['draft']:
        # Same upstream version keeps the same visible suffix. Rebuild only
        # after validation, and keep the previous attachments for rollback.
        previous = json.loads(response.stdout)
        backup.mkdir()
        run('gh', 'release', 'download', tag, '--repo', repo, '--dir', str(backup))
        previous['tag_sha'] = gh_json(f'repos/{repo}/git/ref/tags/{tag}')['object']['sha']
        (ROOT / '.work/previous-notes.md').write_text(previous.get('body') or '')
        run('gh', 'release', 'edit', tag, '--repo', repo, '--draft')
    try:
        if previous:
            run('gh', 'api', '--method', 'PATCH', f'repos/{repo}/git/refs/tags/{tag}',
                '-f', f"sha={plan['pipeline_sha']}", '-F', 'force=true')
        assets = [str(p) for p in sorted((ROOT / 'out').iterdir()) if p.is_file()]
        run('gh', 'release', 'upload', tag, *assets, '--repo', repo, '--clobber')
        verify = ROOT / '.work/downloaded'
        verify.mkdir()
        run('gh', 'release', 'download', tag, '--repo', repo, '--dir', str(verify))
        for asset in assets:
            p = Path(asset)
            if p.read_bytes() != (verify / p.name).read_bytes():
                raise ValueError(f'Release upload verification failed: {p.name}')
        run('gh', 'release', 'edit', tag, '--repo', repo, '--draft=false', '--latest',
            '--notes-file', str(ROOT / '.work/release-notes.md'))
    except Exception:
        if previous:
            run('gh', 'release', 'upload', tag, *map(str, sorted(backup.iterdir())), '--repo', repo, '--clobber')
            run('gh', 'api', '--method', 'PATCH', f'repos/{repo}/git/refs/tags/{tag}',
                '-f', f"sha={previous['tag_sha']}", '-F', 'force=true')
            run('gh', 'release', 'edit', tag, '--repo', repo, '--draft=false', '--latest',
                '--notes-file', str(ROOT / '.work/previous-notes.md'))
        raise
    print(f'https://github.com/{repo}/releases/tag/{tag}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['plan', 'prepare', 'package', 'publish'])
    parser.add_argument('--repo')
    args = parser.parse_args()
    if args.command == 'plan':
        if not args.repo: parser.error('--repo is required')
        plan(args.repo)
    else:
        globals()[args.command]()
