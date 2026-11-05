"""Reuse recent completed GitHub checks for the exact source and workflow contract."""
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import re
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


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main():
    repository, commit = os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_SHA']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Invalid repository identity.')
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
        evidence = select(request, repository, commit, reuse_allowed=not policy.reuse_disabled(Path.cwd()))
    except (OSError, ValueError, KeyError, TypeError):
        # An unavailable or malformed proof cannot skip tests.
        evidence = {}
    Path('release-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
        for family in REQUIRED:
            stream.write(f'{family}={str(family in evidence).lower()}\n')
    with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as stream:
        stream.write('## Release validation evidence\n\n')
        for family in REQUIRED:
            proof = evidence.get(family)
            stream.write(f'- {family}: ' + (f'reused [verified prior run]({proof["url"]}) for `{commit}`'
                                          if proof else 'fresh checks required') + '\n')


if __name__ == '__main__':
    main()
