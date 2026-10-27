"""Logistics policy for signed local test evidence transported as Git notes.

Signing keys live in private manager configuration. Receivers trust only the
public allowlist in the selected source and derive each suite's inputs locally.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

NOTE_REF = 'refs/notes/build-manager-tests'
SIGNER = 'logistics-local'
MAX_BYTES = 4 * 1024 * 1024


def git(root, *arguments, check=True):
    result = subprocess.run(['git', '-C', str(root), *arguments], capture_output=True,
                            check=check, timeout=60)
    if len(result.stdout) > MAX_BYTES:
        raise ValueError('Local test evidence exceeds the inspection budget.')
    return result


def bindings(root, repository):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('An explicit repository identity is required.')
    def value(*args):
        return git(root, *args).stdout.decode().strip()
    source = value('rev-parse', 'HEAD')
    shared = value('rev-parse', 'HEAD:Python/commonUtils')
    manager = json.loads(value('show', 'HEAD:build-manager-dependency.json'))['revision']
    if any(not re.fullmatch(r'[0-9a-f]{40}', item) for item in (source, shared, manager)):
        raise ValueError('Source and dependencies must use exact commits.')
    return dict(contract='logistics-portable-host-v1', repository=repository,
                source=source, dependencies=dict(commonUtils=shared, manager=manager))


def signing_key(repository):
    from build_manager.registry import config_directory
    identity = hashlib.sha256(repository.encode()).hexdigest()
    return config_directory() / 'release-evidence' / identity / 'signing-key'


def enroll(root, repository):
    """Explicit one-time setup; normal release never silently enrolls a signer."""
    key = signing_key(repository)
    key.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not key.exists():
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)],
                       check=True, capture_output=True, timeout=15)
    if key.is_symlink() or not key.is_file() or os.name != 'nt' and key.stat().st_mode & 0o077:
        raise ValueError('Evidence signing key must be a private regular file.')
    public = subprocess.run(['ssh-keygen', '-y', '-f', str(key)], capture_output=True,
                            check=True, timeout=15).stdout.decode().strip()
    public = ' '.join(public.split()[:2])  # Exclude optional machine/user comments.
    if not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]+', public):
        raise ValueError('Expected the configured Ed25519 evidence signing key.')
    from build_manager.attestations import NAMESPACE
    allowlist = Path(root) / '.github/local-test-signers'
    line = SIGNER + ' namespaces="' + NAMESPACE + '" ' + public
    previous = allowlist.read_text() if allowlist.exists() else ''
    if line not in previous.splitlines():
        allowlist.parent.mkdir(parents=True, exist_ok=True)
        allowlist.write_text(previous.rstrip() + ('\n' if previous.strip() else '') + line + '\n')
    return allowlist


def with_export_request(plan):
    """Bind the exact test phase recipes into the already-reviewed release argv."""
    from dataclasses import replace
    from build_manager.profiles import save_json
    phases = [phase for phase in plan.phases if phase.reuse_key]
    releases = [phase for phase in plan.phases if phase.id.endswith('release-source-and-gates')]
    if not phases or not releases:
        return plan
    path = Path(plan.workspace) / 'evidence-export-request.json'
    save_json(path, dict(source=plan.source['logistics_commit'], phases=[asdict(phase) for phase in phases]))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return replace(plan, phases=tuple(replace(phase, argv=(*phase.argv,
        '--test-evidence-request', str(path), '--test-evidence-sha256', digest))
        if phase in releases else phase for phase in plan.phases))



def verify_from_source(root, envelope, expected, tests, *, now=None, subset=False):
    from build_manager.attestations import verify_export
    # Trust the allowlist in the exact selected commit, not a later working-file
    # replacement by a build command or an uncommitted local enrollment.
    public = git(root, 'show', 'HEAD:.github/local-test-signers').stdout
    with TemporaryDirectory(prefix='logistics-evidence-trust-') as temporary:
        allowed = Path(temporary) / 'allowed-signers'
        allowed.write_bytes(public)
        return verify_export(envelope, allowed, SIGNER, expected, tests, now=now,
                             allow_additional_tests=subset)


def prepare_export(root, repository, request, digest, *, cache=None, key=None, now=None):
    from build_manager import Phase
    from build_manager.attestations import export_receipts
    from build_manager.evidence import EvidenceCache
    if git(root, 'status', '--porcelain').stdout.strip():
        raise ValueError('Commit intended source before exporting release evidence.')
    raw = Path(request).read_bytes()
    if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Reviewed evidence request changed or is oversized.')
    recipe = json.loads(raw)
    expected = bindings(root, repository)
    if recipe['source'] != expected['source']:
        raise ValueError('Evidence request belongs to another source commit.')
    cache = cache or EvidenceCache()
    now = now or datetime.now(timezone.utc)
    local_key = cache.key()
    eligible = []
    for data in recipe['phases']:
        phase = Phase(**data)
        receipt = cache.read(phase, local_key)
        if receipt is None:
            continue
        stamp = datetime.fromisoformat(receipt['row']['finished_at'])
        if stamp.tzinfo is not None and timedelta(0) <= now - stamp <= timedelta(hours=24):
            eligible.append(phase)
    if not eligible:
        return None
    envelope = export_receipts(cache, eligible, expected, key or signing_key(repository), now=now)
    # Refuse to publish a proof whose signer is not enrolled in this source.
    verify_from_source(root, envelope, expected, {phase.id: phase.reuse_key for phase in eligible}, now=now)
    return envelope


def publish_note(root, envelope, output):
    """Publish proof without moving an existing note or tag; reruns reconcile."""
    commit = envelope['payload']['bindings']['source']
    output = Path(output)
    output.write_text(json.dumps(envelope, sort_keys=True) + '\n')
    remote = git(root, 'ls-remote', '--exit-code', 'origin', NOTE_REF, check=False)
    if remote.returncode == 0:
        git(root, 'fetch', '--no-tags', 'origin', NOTE_REF + ':' + NOTE_REF)
    elif remote.returncode != 2:
        raise RuntimeError('Could not reconcile remote evidence notes.')
    existing = git(root, 'notes', '--ref=' + NOTE_REF, 'show', commit, check=False)
    if existing.returncode == 0:
        if json.loads(existing.stdout) != envelope:
            raise ValueError('This source already has evidence; leave it unchanged and use fresh hosted checks.')
    else:
        git(root, 'notes', '--ref=' + NOTE_REF, 'add', '-F', str(output), commit)
    # A lost push response is not replayed: caller falls back to fresh tests;
    # a later release first reconciles the remote ref and exact existing note.
    git(root, 'push', 'origin', NOTE_REF)


def fetch_note(root):
    # Public repository read only. Missing/private/unavailable notes are misses.
    try:
        result = git(root, 'fetch', '--no-tags', 'origin', NOTE_REF + ':' + NOTE_REF, check=False)
        return result.returncode == 0
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def matched_proof(root, phase, *, envelope=None, repository=None, now=None):
    """Use only the actual receiver-derived phase key, never a manifest key claim."""
    if not phase.reuse_key:
        return None
    try:
        repository = repository or os.environ['GITHUB_REPOSITORY']
        expected = bindings(root, repository)
        if os.environ.get('GITHUB_SHA', expected['source']) != expected['source']:
            return None
        if envelope is None:
            envelope = json.loads(git(root, 'notes', '--ref=' + NOTE_REF,
                                      'show', expected['source']).stdout)
        suite = phase.id.rsplit('.', 1)[-1]
        matches = {item['step']: phase.reuse_key for item in envelope['payload']['tests']
                   if item['inputs'] == phase.reuse_key and item['step'].rsplit('.', 1)[-1] == suite}
        if not matches:
            return None
        verify_from_source(root, envelope, expected, matches, now=now, subset=True)
        return dict(source=expected['source'], inputs=phase.reuse_key, signer=SIGNER,
                    steps=sorted(matches), signature_sha256=hashlib.sha256(
                        envelope['signature'].encode()).hexdigest(), provenance='signed local test receipt')
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return None  # Never turn an unavailable or invalid proof into a pass.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('enroll', 'fetch'))
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--repository', default='ispaure/logistics')
    args = parser.parse_args()
    if args.command == 'enroll':
        print('Review and commit the public signer allowlist:', enroll(args.root, args.repository))
    else:
        print('Local evidence notes fetched.' if fetch_note(args.root) else
              'Local evidence unavailable; fresh hosted checks remain required.')


if __name__ == '__main__':
    main()
