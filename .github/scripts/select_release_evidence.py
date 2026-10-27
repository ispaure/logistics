"""Reuse recent completed GitHub checks for the exact source and workflow contract."""
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import re
from urllib.request import Request, build_opener, HTTPRedirectHandler

REQUIRED = {
    'validate': ('.github/workflows/archive-platform-checks.yml',
                 {'static', 'macos-latest', 'windows-latest', 'Fedora 43 container'}),
    'mobile-build': ('.github/workflows/mobile-build.yml',
                     {'Build shared iOS test app', 'Build and validate Android', 'Validate iOS iphone',
                      'Validate iOS duo', 'Validate iOS ipad', 'Require every selected native check'}),
    'mobile-runtime': ('.github/workflows/mobile-runtime.yml', {'ios', 'android'}),
}


def select(request, repository, commit, *, now=None, max_age=timedelta(hours=24)):
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Evidence must identify an exact source commit.')
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
            by_name = {job['name']: job for job in jobs}
            if not required.issubset(by_name):
                continue
            selected = [by_name[name] for name in required]
            if any(job.get('status') != 'completed' or job.get('conclusion') != 'success'
                   or not job.get('completed_at') for job in selected):
                continue
            dates = [datetime.fromisoformat(job['completed_at'].replace('Z', '+00:00')) for job in selected]
            if any(date > now or now - date > max_age for date in dates):
                continue
            result[family] = dict(run_id=run['id'], url=run['html_url'], workflow=workflow,
                                  commit=commit, jobs=sorted(required), oldest_completed_at=min(dates).isoformat())
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
        evidence = select(request, repository, commit)
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
