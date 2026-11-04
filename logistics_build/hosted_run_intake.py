"""Adopt one verified automatic push run; never create or redispatch a remote run."""
from datetime import datetime, timedelta, timezone
import hashlib
import re
import subprocess
from urllib.parse import quote

from logistics_build.hosted_requirements import PUSH_DEFAULTS, REQUIRED, complete_family_jobs

MAX_AGE = timedelta(hours=24)
ACTIVE = {'queued', 'in_progress', 'waiting', 'requested', 'pending', 'completed'}


def contract(root, expected):
    """Only ordinary inputs covered by an exact reviewed push workflow may adopt."""
    policy = PUSH_DEFAULTS.get(expected['workflow'])
    if policy is None or expected['platform'] not in policy['targets'] or expected['inputs'] != {'target': expected['platform']}:
        return None
    ref = expected['ref']
    branch = ref.removeprefix('refs/heads/')
    if ref.startswith('refs/tags/') or not re.fullmatch(r'[A-Za-z0-9_.][A-Za-z0-9_./-]{0,199}', branch):
        return None
    # The reviewed automatic mobile contracts run only on alpha; desktop also main.
    if branch not in ({'alpha', 'main'} if policy['family'] == 'validate' else {'alpha'}):
        return None
    try:
        blob = subprocess.run(['git', '-C', str(root), 'show', expected['expected_commit'] + ':' + REQUIRED[policy['family']][0]],
                              capture_output=True, check=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    if hashlib.sha256(blob).hexdigest() != policy['sha256']:
        raise ValueError('Automatic push defaults changed. Review their contract or explicitly disable reuse for fresh validation.')
    return dict(family=policy['family'], branch=branch, workflow_path=REQUIRED[policy['family']][0],
                workflow_sha256=policy['sha256'], required_jobs=sorted(REQUIRED[policy['family']][1]))


def identity(run, expected, policy, workflow_id):
    """Immutable automatic-run facts; bool IDs and fork results are not identities."""
    run_id, attempt = run.get('id'), run.get('run_attempt')
    created = run.get('created_at')
    if (type(run_id) is not int or run_id <= 0 or type(attempt) is not int or attempt <= 0
            or run.get('workflow_id') != workflow_id or type(run.get('workflow_id')) is not int
            or run.get('head_sha') != expected['expected_commit'] or run.get('head_branch') != policy['branch']
            or run.get('event') != 'push' or run.get('path') != policy['workflow_path']
            or run.get('repository', {}).get('full_name') != expected['repository']
            or run.get('head_repository', {}).get('full_name') != expected['repository']
            or run.get('html_url') != f'https://github.com/{expected["repository"]}/actions/runs/{run_id}'
            or not isinstance(created, str)):
        raise ValueError('Automatic hosted run identity differs from the reviewed source/defaults.')
    stamp = datetime.fromisoformat(created.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Automatic hosted run creation time has no timezone.')
    return dict(run_id=run_id, run_attempt=attempt, created_at=created, html_url=run['html_url'],
        event='push', workflow_id=workflow_id, workflow_path=policy['workflow_path'],
        head_sha=run['head_sha'], head_branch=run['head_branch'], repository=expected['repository'],
        head_repository=run['head_repository']['full_name'])


def intake(client, root, expected, *, now=None):
    declared = PUSH_DEFAULTS.get(expected['workflow'])
    if declared and (expected['platform'] not in declared['targets'] or expected['inputs'] != {'target': expected['platform']}):
        raise ValueError('Hosted inputs differ from reviewed push defaults. Explicitly disable reuse for fresh validation.')
    policy = contract(root, expected)
    if policy is None:
        return None
    now = now or datetime.now(timezone.utc)
    workflow = client.request('GET', client.base + '/actions/workflows/' + quote(expected['workflow'], safe=''))
    if type(workflow.get('id')) is not int or workflow['id'] <= 0 or workflow.get('path') != policy['workflow_path']:
        raise ValueError('Automatic workflow metadata does not match the reviewed contract.')
    response = client.request('GET', client.base + '/actions/workflows/' + str(workflow['id']) + '/runs?event=push&branch='
        + quote(policy['branch'], safe='') + '&head_sha=' + expected['expected_commit'] + '&per_page=100')
    if not isinstance(response.get('workflow_runs'), list) or response.get('total_count', 0) > 100:
        raise ValueError('Automatic hosted-run inventory is incomplete; inspect it or explicitly disable reuse.')
    candidates = []
    for run in response['workflow_runs']:
        try:
            proof = identity(run, expected, policy, workflow['id'])
            stamp = datetime.fromisoformat(proof['created_at'].replace('Z', '+00:00'))
            if not timedelta(0) <= now - stamp <= MAX_AGE or run.get('status') not in ACTIVE:
                continue
        except (ValueError, KeyError, TypeError):
            continue
        candidates.append(proof)
    if len(candidates) > 1:
        raise ValueError('Multiple matching automatic runs exist. Inspect their identities or explicitly disable reuse for a fresh dispatch.')
    if not candidates:
        return None
    return dict(schema=2, provider='github', origin='existing-run', status='queued',
                automatic=candidates[0], policy=policy, run_id=candidates[0]['run_id'], **expected)


def verify_receipt(receipt, root, expected):
    policy = contract(root, expected)
    if (policy is None or receipt.get('schema') != 2 or receipt.get('provider') != 'github'
            or receipt.get('origin') != 'existing-run' or receipt.get('status') != 'queued'
            or any(receipt.get(key) != value for key, value in expected.items())
            or receipt.get('policy') != policy or not isinstance(receipt.get('automatic'), dict)
            or receipt.get('run_id') != receipt['automatic'].get('run_id')
            or not isinstance(receipt.get('operation_id'), str) or not receipt['operation_id']):
        raise ValueError('Automatic hosted intake differs from the reviewed operation.')
    captured = receipt['automatic']
    synthetic = dict(id=captured.get('run_id'), run_attempt=captured.get('run_attempt'),
        created_at=captured.get('created_at'), html_url=captured.get('html_url'), event=captured.get('event'),
        workflow_id=captured.get('workflow_id'), path=captured.get('workflow_path'), head_sha=captured.get('head_sha'),
        head_branch=captured.get('head_branch'), repository={'full_name': captured.get('repository')},
        head_repository={'full_name': captured.get('head_repository')})
    if (type(captured.get('workflow_id')) is not int or captured['workflow_id'] <= 0
            or identity(synthetic, expected, policy, captured['workflow_id']) != captured):
        raise ValueError('Automatic hosted intake has invalid immutable run facts.')
    return policy


def observe(client, receipt, root, expected, cancelled, *, progress=None):
    """Reuse the SDK wait/transport while verifying identity on every observation."""
    from build_manager.github import GitHub
    policy = verify_receipt(receipt, root, expected)
    captured = receipt['automatic']
    run_id = captured['run_id']
    path = client.base + f'/actions/runs/{run_id}'

    def checked(row):
        if identity(row, expected, policy, captured['workflow_id']) != captured:
            raise ValueError('Automatic hosted run attempt or immutable identity changed.')
        return row

    class BoundRun(GitHub):
        def __init__(self):
            self.base = client.base

        def request(self, method, requested, body=None):
            if method != 'GET':
                raise RuntimeError('Automatic hosted observation stopped locally; the shared run remains unchanged. Inspect its saved run ID/attempt.')
            result = client.request(method, requested, body)
            return checked(result) if method == 'GET' and requested == path else result

    remote = BoundRun().wait(run_id, expected['expected_commit'], timeout=13800,
                             cancelled=cancelled, progress=progress)
    if remote.get('status') != 'completed' or remote.get('conclusion') != 'success':
        raise RuntimeError('Adopted hosted validation did not pass.')
    response = client.request('GET', path + f'/attempts/{captured["run_attempt"]}/jobs?per_page=100')
    if not isinstance(response.get('jobs'), list) or response.get('total_count', 0) > 100:
        raise ValueError('Automatic hosted full-family job evidence is incomplete.')
    proof = complete_family_jobs(response['jobs'], policy['family'])
    # A rerun may begin while the terminal job evidence is being inspected.
    final = checked(client.request('GET', path))
    if final.get('status') != 'completed' or final.get('conclusion') != 'success':
        raise ValueError('Automatic hosted evidence changed while full-family jobs were verified.')
    return dict(status='passed', origin='existing-run', run_id=run_id, run_attempt=captured['run_attempt'], **proof)
