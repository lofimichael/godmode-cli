#!/usr/bin/env python3
"""Fetch a published CLI release and open its reviewed website promotion PR."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

CLI_REPO = 'lofimichael/godmode-cli'
SITE_REPO = 'lofimichael/godmode-build'
TAG = re.compile(r'v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)')
SHA = re.compile(r'[a-f0-9]{40}')
TARGETS = (
    'aarch64-apple-darwin',
    'x86_64-apple-darwin',
    'aarch64-unknown-linux-musl',
    'x86_64-unknown-linux-musl',
    'source',
)
GIT_AUTH = ('-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential')


class PromotionError(Exception):
    pass


def command(*args):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE, text=True).stdout


def validate(version, source_sha):
    if (len(version) > 40 or not TAG.fullmatch(version) or not SHA.fullmatch(source_sha)
            or source_sha == '0' * 40):
        raise PromotionError('Expected a canonical vX.Y.Z and full lowercase source commit.')


def artifact_names(version):
    return {'install.sh', 'SHA256SUMS', *(f'godmode-{version}-{target}.tar.gz' for target in TARGETS)}


def download(version, source_sha, directory):
    validate(version, source_sha)
    if command('git', 'rev-parse', f'refs/tags/{version}^{{commit}}').strip() != source_sha:
        raise PromotionError('The Git tag does not point to the expected source commit.')
    command('git', 'merge-base', '--is-ancestor', source_sha, 'HEAD')
    release = json.loads(command('gh', 'release', 'view', version, '--repo', CLI_REPO,
                                 '--json', 'isDraft,isPrerelease,tagName,assets'))
    expected = artifact_names(version)
    names = [entry['name'] for entry in release['assets']]
    if (release['isDraft'] or release['isPrerelease'] or release['tagName'] != version
            or len(names) != len(expected) or set(names) != expected):
        raise PromotionError('The stable release does not contain the exact expected asset set.')
    # A fresh directory makes partial or extra downloads visible to the importer.
    directory.mkdir()
    command('gh', 'release', 'download', version, '--repo', CLI_REPO, '--dir', str(directory))
    entries = list(directory.iterdir())
    if ({entry.name for entry in entries} != expected
            or any(entry.is_symlink() or not entry.is_file() or not entry.stat().st_size for entry in entries)):
        raise PromotionError('The downloaded asset set is incomplete.')


def remote_ref(git, ref):
    lines = git(*GIT_AUTH, 'ls-remote', '--refs', 'origin', ref).splitlines()
    if not lines:
        return None
    if len(lines) != 1:
        raise PromotionError('The remote did not return a single exact ref.')
    sha, sep, returned = lines[0].partition('\t')
    if sep != '\t' or not SHA.fullmatch(sha) or returned != ref:
        raise PromotionError('The remote ref response was invalid.')
    return sha


def release_prs(branch):
    rows = json.loads(command('gh', 'pr', 'list', '--repo', SITE_REPO, '--base', 'main',
                              '--head', branch, '--state', 'all', '--limit', '50',
                              '--json', 'state,url,headRefName,headRefOid,isCrossRepository'))
    return [row for row in rows if not row['isCrossRepository'] and row['headRefName'] == branch]


def promote(version, source_sha, site, directory):
    validate(version, source_sha)
    branch = 'automation/cli-' + version
    branch_ref = 'refs/heads/' + branch

    def git(*args):
        return command('git', '-C', str(site), *args)

    # The website workflow must see a trusted default-branch checkout and a clean tree.
    if git('remote', 'get-url', 'origin').strip() not in (
            f'https://github.com/{SITE_REPO}', f'https://github.com/{SITE_REPO}.git'):
        raise PromotionError('The checkout does not target the website repository.')
    head = git('rev-parse', 'HEAD').strip()
    if git('status', '--porcelain') or remote_ref(git, 'refs/heads/main') != head:
        raise PromotionError('Start from a clean checkout of the current website main.')

    subprocess.run([sys.executable, 'scripts/prepare-cli-release.py', str(directory.resolve()),
                    '--version', version, '--source-sha', source_sha], cwd=site, check=True)
    if not git('status', '--porcelain'):
        print(f'{version} is already present in website main.')
        return

    git('add', '--all')
    tree = git('write-tree').strip()
    if remote_ref(git, 'refs/heads/main') != head:
        raise PromotionError('Website main moved during preparation. Retry the same version and commit.')

    rows = release_prs(branch)
    open_rows = [row for row in rows if row['state'] == 'OPEN']
    branch_sha = remote_ref(git, branch_ref)
    if len(open_rows) > 1:
        raise PromotionError('Multiple open distribution PRs use the same release branch.')
    if rows and not open_rows:
        raise PromotionError('A prior distribution PR is closed. Inspect its decision before retrying.')
    if branch_sha:
        git(*GIT_AUTH, 'fetch', '--no-tags', '--depth=1', 'origin', branch_ref)
        if git('rev-parse', 'FETCH_HEAD').strip() != branch_sha:
            raise PromotionError('The distribution branch moved. Retry after inspecting it.')
        if open_rows:
            # Preserve release-note edits while confirming the reviewed artifacts have not changed.
            if open_rows[0]['headRefOid'] != branch_sha:
                raise PromotionError('The open PR does not match the fetched distribution branch.')
            for asset in (f'public/releases/{version}', 'public/releases/latest.json', 'public/install.sh',
                          'content/docs/providers.json'):
                if git('rev-parse', f'{tree}:{asset}') != git('rev-parse', f'{branch_sha}:{asset}'):
                    raise PromotionError(f'The existing distribution PR differs at {asset}.')
            manifest = json.loads(git('show', f'{branch_sha}:content/docs/manifest.json'))
            if manifest.get('version') != version or manifest.get('cliCommit') != source_sha:
                raise PromotionError('The existing distribution PR points to a different CLI source.')
            print(open_rows[0]['url'])
            return
        if git('rev-parse', f'{branch_sha}^{{tree}}').strip() != tree:
            raise PromotionError('The existing distribution branch differs. Review it before opening a PR.')
    elif open_rows:
        raise PromotionError('The existing open PR has no matching remote branch.')
    else:
        git('-c', 'user.name=Godmode Release', '-c', 'user.email=godmode-release@users.noreply.github.com',
            'commit', '-m', f'Distribute Godmode {version}', '-m', f'CLI source: {source_sha}')
        # An empty lease expectation permits creation only. Retries never replace a remote branch.
        git(*GIT_AUTH, 'push', f'--force-with-lease={branch_ref}:', 'origin', f'HEAD:{branch_ref}')

    body = (f'Promotes the verified Godmode CLI {version} archives and versioned docs.\n\n'
            f'CLI source commit: `{source_sha}`\n\n'
            f'[Release assets](https://github.com/{CLI_REPO}/releases/tag/{version})\n\n'
            'Review the website changes and merge after its checks pass. The website deployment '
            'updates the customer installer channel.')
    print(command('gh', 'pr', 'create', '--repo', SITE_REPO, '--base', 'main',
                  '--head', branch, '--title', f'Distribute Godmode {version}', '--body', body).strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('download', 'promote'))
    parser.add_argument('--version', required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--directory', required=True, type=Path)
    parser.add_argument('--site', type=Path)
    args = parser.parse_args()
    try:
        if args.action == 'download':
            download(args.version, args.source_sha, args.directory)
        elif args.site is None:
            parser.error('--site is required for promote')
        else:
            promote(args.version, args.source_sha, args.site.resolve(), args.directory)
    except (PromotionError, subprocess.CalledProcessError, OSError, ValueError) as error:
        print(f'godmode distribution: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
