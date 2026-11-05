"""Reuse recent completed GitHub checks for the exact source and workflow contract."""
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.request import Request, build_opener, HTTPRedirectHandler

# The evidence job does not check out submodules or install project dependencies.
# Load the shared stdlib policy without executing logistics_build.__init__.
import importlib.util


def source_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[2] / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_policy = source_module('logistics_hosted_requirements', 'logistics_build/hosted_requirements.py')
REQUIRED, complete_family_jobs = _policy.REQUIRED, _policy.complete_family_jobs



def select(request, repository, commit, *, now=None, max_age=timedelta(hours=24), reuse_allowed=True):
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Evidence must identify an exact source commit.')
    if not reuse_allowed:
        return {}
    now = now or datetime.now(timezone.utc)
    result = {}
    runs = request('/actions/runs?head_sha=' + commit + '&status=success&per_page=100')['workflow_runs']
    for family, (workflow, required) in REQUIRED.items():
        for run in runs:
            if (run.get('head_sha') != commit or run.get('path') != workflow
                    or run.get('status') != 'completed' or run.get('conclusion') != 'success'
                    or run.get('event') not in {'push', 'workflow_dispatch'}
                    or run.get('head_repository', {}).get('full_name') != repository):
                continue
            jobs = request('/actions/runs/' + str(run['id']) + '/jobs?filter=latest&per_page=100')['jobs']
            try:
                proof = complete_family_jobs(jobs, family, now=now, max_age=max_age)
            except (ValueError, KeyError, TypeError):
                continue
            result[family] = dict(run_id=run['id'], url=run['html_url'], workflow=workflow,
                                  commit=commit, **proof)
            break
    return result


def hosted_validation_mode(root, commit, ref, event):
    """Only a source-bound, owned annotated push tag may opt out of validation."""
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Validation policy requires an exact source commit.')
    if not ref.startswith('refs/tags/'):
        return 'on'
    if not re.fullmatch(r'refs/tags/v[A-Za-z0-9_.-]{1,199}', ref):
        raise ValueError('Invalid release tag for hosted validation policy.')
    def git(*args):
        result = subprocess.run(['git', *args], cwd=root, capture_output=True, check=True, timeout=15)
        if len(result.stdout) > 65536:
            raise ValueError('Release tag policy exceeds its bound.')
        return result.stdout
    if (git('rev-parse', 'HEAD').decode().strip() != commit
            or git('rev-parse', ref + '^{commit}').decode().strip() != commit):
        raise ValueError('Release tag policy does not match the captured source.')
    kind = git('cat-file', '-t', ref).strip()
    if kind == b'commit':
        return 'on'
    if kind != b'tag':
        raise ValueError('Unsupported release tag policy object.')
    header, _, body = git('cat-file', '-p', ref).partition(b'\n\n')
    fields = dict(line.split(b' ', 1) for line in header.splitlines())
    if (fields.get(b'object') != commit.encode() or fields.get(b'type') != b'commit'
            or fields.get(b'tag') != ref.removeprefix('refs/tags/').encode()):
        raise ValueError('Annotated release policy must directly identify this tag and source.')
    lines = body.decode('utf-8').splitlines()
    policies = [line.strip() for line in lines if line.lower().startswith('build-manager-hosted-validation')]
    if len(policies) > 1 or policies and not re.fullmatch(r'Build-Manager-Hosted-Validation: (?:on|off)', policies[0]):
        raise ValueError('Malformed or ambiguous hosted validation mode in release tag.')
    mode = policies[0].rsplit(' ', 1)[1] if policies else 'on'
    if mode == 'off':
        owners = [line for line in lines if line.startswith('Build-Manager-Publication:')]
        if len(owners) != 1 or not re.fullmatch(r'Build-Manager-Publication: [0-9a-f]{32}', owners[0]):
            raise ValueError('Hosted validation opt-out requires an owned publication tag.')
        # A manual workflow cannot turn a validation run into a no-test release.
        if event != 'push':
            return 'on'
    return mode


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main():
    repository, commit = os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_SHA']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Invalid repository identity.')
    mode = hosted_validation_mode(Path.cwd(), commit, os.environ.get('GITHUB_REF', ''),
                                  os.environ.get('GITHUB_EVENT_NAME', ''))
    opener = build_opener(NoRedirect())
    def request(path):
        req = Request('https://api.github.com/repos/' + repository + path,
            headers={'Accept': 'application/vnd.github+json',
                     'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'],
                     'User-Agent': 'LogisticsReleaseEvidence'})
        with opener.open(req, timeout=30) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError('Evidence response exceeds the inspection budget.')
        return json.loads(raw)
    try:
        policy = source_module('logistics_release_test_evidence', 'logistics_build/release_test_evidence.py')
        evidence = ({} if mode == 'off' else
                    select(request, repository, commit, reuse_allowed=not policy.reuse_disabled(Path.cwd())))
    except (OSError, ValueError, KeyError, TypeError):
        # An unavailable or malformed proof cannot skip tests.
        evidence = {}
    Path('release-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    Path('release-validation-policy.json').write_text(json.dumps(dict(schema=1, source=commit,
        ref=os.environ.get('GITHUB_REF', ''), hosted_validation=mode, hosted_skip=mode == 'off',
        verified_reuse_families=sorted(evidence),
        reason='Operator selected no hosted validation in the immutable owned release tag.' if mode == 'off'
               else 'Hosted validation required; only verified exact-source evidence may be reused.'), indent=2) + '\n')
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
        stream.write(f'hosted-skip={str(mode == 'off').lower()}\n')
        for family in REQUIRED:
            stream.write(f'{family}={str(family in evidence).lower()}\n')
    with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as stream:
        stream.write('## Release validation evidence\n\n')
        if mode == 'off':
            stream.write('Operator selected **no hosted validation** in the owned release tag. '
                         'No hosted matrix or release-tooling tests were run; packaging integrity remains required.\n\n')
        for family in REQUIRED:
            proof = evidence.get(family)
            stream.write(f'- {family}: ' + (f'reused [verified prior run]({proof["url"]}) for `{commit}`'
                                          if proof else 'not run: explicit operator opt-out' if mode == 'off' else 'fresh checks required') + '\n')


if __name__ == '__main__':
    main()
