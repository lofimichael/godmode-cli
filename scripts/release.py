#!/usr/bin/env python3
"""Plan, verify, and publish a commit-bound Godmode CLI release."""

import argparse
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import urlsplit


MAIN = 'refs/heads/main'
TAG = re.compile(r'v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)')
SHA = re.compile(r'[0-9a-f]{40}')
TARGETS = (
    'aarch64-apple-darwin',
    'x86_64-apple-darwin',
    'aarch64-unknown-linux-musl',
    'x86_64-unknown-linux-musl',
)


class ReleaseError(Exception):
    pass


def version_key(version):
    if len(version) > 40 or not TAG.fullmatch(version):
        raise ReleaseError('Expected a canonical vX.Y.Z release version.')
    return tuple(map(int, version[1:].split('.')))


def checked_sha(value):
    if not SHA.fullmatch(value) or value == '0' * 40:
        raise ReleaseError('Expected a full lowercase commit SHA.')
    return value


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def version_at(sha):
    version = 'v' + git('show', f'{sha}:VERSION')
    version_key(version)
    return version


def sha_at_tag(tag):
    version_key(tag)
    return checked_sha(git('rev-parse', '--verify', f'refs/tags/{tag}^{{commit}}'))


def validate_changelog(changelog, version):
    """Check the section consumed by the website release importer."""
    if len(changelog.encode()) > 512 * 1024:
        raise ReleaseError('docs/CHANGELOG.md exceeds its release archive size limit.')
    changelog = changelog.replace('\r\n', '\n')
    headings = list(re.finditer(r'^##[ \t]+(.+?)[ \t]*$', changelog, re.MULTILINE))
    matches = [index for index, heading in enumerate(headings) if heading[1] == version]
    if len(matches) != 1:
        raise ReleaseError(f'docs/CHANGELOG.md needs one ## {version} section.')
    index = matches[0]
    end = headings[index + 1].start() if index + 1 < len(headings) else len(changelog)
    body = changelog[headings[index].end():end].strip()
    if len(body) > 32768 or any(ord(character) < 32 and character not in '\n\t' for character in body):
        raise ReleaseError(f'CLI release notes for {version} contain unsupported text.')
    lines = body.splitlines()
    if not lines or not any(re.match(r'^[-*] +\S', line) for line in lines[1:]):
        raise ReleaseError(f'CLI release notes for {version} need a date and a change bullet.')
    try:
        if re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', lines[0]):
            date.fromisoformat(lines[0])
        else:
            datetime.strptime(lines[0], '%B %d, %Y')
    except ValueError as error:
        raise ReleaseError(f'CLI release notes for {version} need a valid date.') from error
    for link in re.findall(r'\[[^\]\n]+\]\(([^)\s]+)\)', body):
        if re.fullmatch(r'#[a-z0-9-]+', link):
            continue
        if link.startswith('/') and not link.startswith('//') and '\\' not in link:
            continue
        parsed = urlsplit(link)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None or '\\' in link:
            raise ReleaseError('Use HTTPS links, site-relative paths or section anchors in CLI release notes.')


def plan(event_name, ref, head, event, github):
    if git('rev-parse', 'HEAD') != checked_sha(head):
        raise ReleaseError('Planner checkout does not match the workflow commit.')
    if event_name == 'push':
        if ref != MAIN or event.get('ref') != MAIN or event.get('after') != head:
            raise ReleaseError('Push input must identify the exact main commit.')
        if event.get('forced'):
            raise ReleaseError('Forced main pushes require an explicit release dispatch.')
        before = checked_sha(event.get('before', ''))
        subprocess.run(['git', 'merge-base', '--is-ancestor', before, head], check=True)
        old, version = version_at(before), version_at(head)
        if old == version:
            print(f'VERSION remains {version}.')
            return {'mode': 'skip'}
        if version_key(old) >= version_key(version):
            raise ReleaseError(f'VERSION must increase from {old} to {version}.')
        sha, dry_run = head, False
    elif event_name == 'workflow_dispatch':
        inputs = event.get('inputs', {})
        tag = inputs.get('tag', '')
        sha = inputs.get('commit', '')
        dry = inputs.get('dry_run', 'true')
        if dry not in ('true', 'false', True, False):
            raise ReleaseError('dry_run must be true or false.')
        dry_run = dry in ('true', True)
        if tag and sha:
            raise ReleaseError('Select a tag or a commit.')
        if not dry_run and not (tag or sha):
            raise ReleaseError('Publishing requires an explicit existing tag or full commit SHA.')
        sha = sha_at_tag(tag) if tag else checked_sha(sha or head)
        version = version_at(sha)
        if tag and tag != version:
            raise ReleaseError(f'{tag} disagrees with the selected commit VERSION {version}.')
    else:
        raise ReleaseError('Unknown release event.')

    mode = 'dry-run' if dry_run else 'build'
    if not dry_run:
        if ref != MAIN:
            raise ReleaseError('Publishing must run from main.')
        github.require_main_commit(sha)
        tags, release = current_state(github, version, sha)
        if release and not release['draft']:
            return {'mode': 'reuse', 'version': version, 'source_sha': sha}
        require_newest(tags, version)
    validate_changelog(git('show', f'{sha}:docs/CHANGELOG.md'), version)
    return {'mode': mode, 'version': version, 'source_sha': sha}


def artifacts(version):
    return {target: f'godmode-{version}-{target}.tar.gz' for target in (*TARGETS, 'source')}


def digest_stream(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(chunk)
    return digest.hexdigest()


def digest_file(path):
    with path.open('rb') as stream:
        return digest_stream(stream)


def archive_member(archive, name):
    matches = [member for member in archive.getmembers() if member.name == name]
    if len(matches) != 1 or not matches[0].isfile():
        raise ReleaseError(f'Expected one regular {name} file in {archive.name}.')
    return archive.extractfile(matches[0])


def archive_text(archive, name, limit=65536):
    with archive_member(archive, name) as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ReleaseError(f'{name} exceeds its size limit in {archive.name}.')
    return value


def verify_bundle(directory, version, sha, *, require_notes=True):
    version_key(version)
    checked_sha(sha)
    archives = artifacts(version)
    names = {'install.sh', *archives.values()}
    entries = {path.name: path for path in directory.iterdir()}
    if set(entries) != names | {'SHA256SUMS'} or any(
            not path.is_file() or path.is_symlink() or not path.stat().st_size
            for path in entries.values()):
        raise ReleaseError('Expected exactly the four native archives, source, installer, and checksums.')
    hashes = {name: digest_file(path) for name, path in entries.items()}
    lines = entries['SHA256SUMS'].read_text().splitlines()
    if len(lines) != len(names) or set(lines) != {f'{hashes[name]}  {name}' for name in names}:
        raise ReleaseError('SHA256SUMS disagrees with the asset names or bytes.')

    with tarfile.open(entries[archives['source']], 'r:gz') as source:
        build_json = archive_text(source, 'BUILD.json')
        recorded_version = archive_text(source, 'VERSION').decode().strip()
        if require_notes:
            changelog = archive_text(source, 'docs/CHANGELOG.md', limit=512 * 1024).decode()
            validate_changelog(changelog, version)
    build = json.loads(build_json)
    if not isinstance(build, dict) or not isinstance(build.get('binaries'), dict):
        raise ReleaseError('Expected a build manifest with native binary digests.')
    binaries = build['binaries']
    if (recorded_version != version[1:] or build.get('version') != recorded_version
            or build.get('commit') != sha or build.get('source_archive') != archives['source']
            or build.get('CGO_ENABLED') != '0' or set(binaries) != set(TARGETS)):
        raise ReleaseError('Source archive metadata does not identify the expected build.')
    for target, name in archives.items():
        with tarfile.open(entries[name], 'r:gz') as archive:
            if (archive_text(archive, 'BUILD.json') != build_json
                    or hashlib.sha256(archive_text(archive, 'install.sh')).hexdigest() != hashes['install.sh']):
                raise ReleaseError(f'Build metadata or installer differs in {name}.')
            if target in TARGETS:
                with archive_member(archive, 'godmode') as binary:
                    if digest_stream(binary) != binaries[target]:
                        raise ReleaseError(f'Native binary digest differs in {name}.')
    return hashes


class GitHub:
    def __init__(self, repo):
        if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo, re.ASCII):
            raise ReleaseError('Expected a GitHub owner/repository.')
        self.repo = repo

    def api(self, path, *, method=None, data=None, paginate=False):
        args = ['gh', 'api', f'repos/{self.repo}/{path}']
        if method:
            args.extend(['--method', method])
        if data is not None:
            args.extend(['--input', '-'])
        if paginate:
            args.extend(['--paginate', '--slurp'])
        result = subprocess.run(args, input=json.dumps(data) if data is not None else None,
                                stdout=subprocess.PIPE, text=True, check=True)
        return json.loads(result.stdout) if result.stdout else None

    def require_main_commit(self, sha):
        checked_sha(sha)
        if self.api(f'compare/{sha}...main')['status'] not in ('ahead', 'identical'):
            raise ReleaseError('Candidate commit is no longer reachable from main.')

    def tags(self):
        result = {}
        for row in self.api('git/matching-refs/tags/v'):
            tag = row['ref'].removeprefix('refs/tags/')
            if len(tag) <= 40 and TAG.fullmatch(tag):
                result[tag] = row['object']
        return result

    def tag_commit(self, git_object):
        for _ in range(10):
            sha = checked_sha(git_object['sha'])
            if git_object['type'] == 'commit':
                return sha
            if git_object['type'] != 'tag':
                break
            git_object = self.api(f'git/tags/{sha}')['object']
        raise ReleaseError('Release tag must resolve to a commit.')

    def release(self, version):
        rows = [row for page in self.api('releases?per_page=100', paginate=True)
                for row in page if row['tag_name'] == version]
        if len(rows) > 1 or (rows and rows[0]['prerelease']):
            raise ReleaseError(f'Expected at most one stable release for {version}.')
        return rows[0] if rows else None

    def create_tag(self, version, sha):
        self.api('git/refs', method='POST', data={'ref': f'refs/tags/{version}', 'sha': sha})

    def create_draft(self, version):
        # The tag already exists. Keep the API target at the default branch for metadata updates.
        self.api('releases', method='POST', data={
            'tag_name': version, 'name': f'Godmode {version}', 'draft': True,
            'generate_release_notes': True,
        })

    def delete_starter(self, asset_id):
        self.api(f'releases/assets/{asset_id}', method='DELETE')

    def upload(self, version, paths):
        subprocess.run(['gh', 'release', 'upload', version, '--repo', self.repo,
                        *(str(path) for path in paths)], check=True)

    def download(self, asset, path):
        with path.open('wb') as stream:
            subprocess.run(['gh', 'api', f'repos/{self.repo}/releases/assets/{asset["id"]}',
                            '--header', 'Accept: application/octet-stream'],
                           stdout=stream, check=True)

    def publish(self, release_id):
        self.api(f'releases/{release_id}', method='PATCH', data={'draft': False, 'make_latest': 'true'})


def current_state(github, version, sha):
    tags = github.tags()
    release = github.release(version)
    if version in tags:
        if github.tag_commit(tags[version]) != sha:
            raise ReleaseError(f'{version} already points to a different commit.')
    elif release:
        raise ReleaseError(f'{version} release exists without its required Git tag.')
    return tags, release


def require_newest(tags, version):
    newer = max(tags, key=version_key, default=version)
    if version_key(newer) > version_key(version):
        raise ReleaseError(f'{newer} is newer than {version}. Publishing would move the latest version backward.')


def release_assets(release, names):
    rows = release['assets']
    assets = {entry['name']: entry for entry in rows}
    if len(rows) != len(assets) or not set(assets) <= names:
        raise ReleaseError('Release contains unexpected or duplicate assets.')
    return assets


def check_uploaded(github, asset, path, digest):
    if asset['state'] != 'uploaded' or asset['size'] != path.stat().st_size:
        raise ReleaseError(f'Existing asset {path.name} has an unexpected state or size.')
    remote_digest = asset.get('digest')
    if not remote_digest:
        with tempfile.TemporaryDirectory() as directory:
            downloaded = Path(directory) / path.name
            github.download(asset, downloaded)
            remote_digest = 'sha256:' + digest_file(downloaded)
    if remote_digest != 'sha256:' + digest:
        raise ReleaseError(f'Existing asset {path.name} differs from the tested bytes.')


def verify_uploaded_bundle(github, release, directory, hashes):
    assets = release_assets(release, hashes.keys())
    if assets.keys() != hashes.keys():
        raise ReleaseError('The remote release asset set is incomplete.')
    for name, asset in assets.items():
        check_uploaded(github, asset, directory / name, hashes[name])


def verify_published(github, release, version, sha):
    names = {'install.sh', 'SHA256SUMS', *artifacts(version).values()}
    assets = release_assets(release, names)
    if set(assets) != names or any(asset['state'] != 'uploaded' for asset in assets.values()):
        raise ReleaseError('Published release assets are incomplete.')
    with tempfile.TemporaryDirectory() as directory:
        for name, asset in assets.items():
            github.download(asset, Path(directory) / name)
        verify_bundle(Path(directory), version, sha, require_notes=False)


def publish(github, version, sha, directory):
    version_key(version)
    checked_sha(sha)
    github.require_main_commit(sha)
    tags, release = current_state(github, version, sha)
    if release and not release['draft']:
        if directory is None:
            verify_published(github, release, version, sha)
        else:
            verify_uploaded_bundle(github, release, directory, verify_bundle(directory, version, sha))
        return
    require_newest(tags, version)
    if directory is None:
        raise ReleaseError('Release is unpublished and no tested artifacts are available.')
    hashes = verify_bundle(directory, version, sha)
    if version not in tags:
        github.create_tag(version, sha)
        tags, release = current_state(github, version, sha)
        if version not in tags:
            raise ReleaseError('The remote did not confirm the new Git tag.')
    if not release:
        github.create_draft(version)
        _, release = current_state(github, version, sha)
    if not release or not release['draft']:
        raise ReleaseError('The remote did not confirm the expected draft release.')

    assets = release_assets(release, hashes.keys())
    missing = []
    starters = []
    for name, digest in sorted(hashes.items()):
        path = directory / name
        asset = assets.get(name)
        if not asset:
            missing.append(path)
        elif asset['state'] == 'starter' and asset['size'] == 0:
            # GitHub leaves an empty starter asset after some failed uploads.
            starters.append(asset['id'])
            missing.append(path)
        else:
            check_uploaded(github, asset, path, digest)
    for asset_id in starters:
        github.delete_starter(asset_id)
    if missing:
        github.upload(version, missing)
    tags, draft = current_state(github, version, sha)
    require_newest(tags, version)
    if not draft or not draft['draft'] or draft['id'] != release['id']:
        raise ReleaseError('The draft changed before it could be published.')
    verify_uploaded_bundle(github, draft, directory, hashes)
    github.require_main_commit(sha)
    github.publish(draft['id'])
    _, published = current_state(github, version, sha)
    if not published or published['draft'] or published['id'] != draft['id']:
        raise ReleaseError('The remote did not confirm the published release.')
    verify_uploaded_bundle(github, published, directory, hashes)


def write_outputs(**values):
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        for key, value in values.items():
            print(f'{key}={value}', file=output)
    print('Release selection:', json.dumps(values, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest='action', required=True)
    subcommands.add_parser('plan')
    for action in ('verify', 'publish'):
        subparser = subcommands.add_parser(action)
        subparser.add_argument('--version', required=True)
        subparser.add_argument('--source-sha', required=True)
        subparser.add_argument('--directory', type=Path, required=action == 'verify')
    args = parser.parse_args()
    if args.action == 'verify':
        verify_bundle(args.directory, args.version, args.source_sha)
    elif args.action == 'plan':
        event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
        write_outputs(**plan(os.environ['GITHUB_EVENT_NAME'], os.environ['GITHUB_REF'],
                             os.environ['GITHUB_SHA'], event, GitHub(os.environ['GITHUB_REPOSITORY'])))
    else:
        if os.environ['GITHUB_REF'] != MAIN:
            raise ReleaseError('Publishing must run from main.')
        publish(GitHub(os.environ['GITHUB_REPOSITORY']), args.version, args.source_sha, args.directory)
        write_outputs(version=args.version, source_sha=args.source_sha)


if __name__ == '__main__':
    try:
        main()
    except (ReleaseError, subprocess.CalledProcessError, OSError, KeyError, ValueError, tarfile.TarError) as error:
        sys.exit(f'release: {error}')
