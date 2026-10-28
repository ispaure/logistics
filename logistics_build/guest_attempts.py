"""Retain immutable guest attempts while publishing the latest declared result."""
from contextlib import contextmanager
import json
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from commonUtils.runtime.streams import file_sha256

from build_manager.locking import workspace_lock
from build_manager.profiles import save_json


def _failed_setup(directory, previous):
    """Resolve only the declared direct attempt, never arbitrary report paths."""
    directory = Path(directory)
    attempt = Path(previous.get('attempt_directory', ''))
    if (previous.get('status') != 'running' or previous.get('backend') != 'Parallels Windows'
            or attempt.parent != directory / 'attempts' or len(attempt.name) != 32
            or any(c not in '0123456789abcdef' for c in attempt.name)
            or any(path.is_symlink() for path in (directory, directory/'attempts', attempt,
                                                   attempt/'prepared.json', attempt/'setup-reconciliation.json'))):
        raise ValueError('Failed setup does not identify an owned Windows attempt.')
    prepared = json.loads((attempt/'prepared.json').read_text())
    if (prepared.get('status') != 'failed' or prepared.get('tests_run') is not False
            or not isinstance(prepared.get('token'), str) or len(prepared['token']) != 32
            or any(c not in '0123456789abcdef' for c in prepared['token'])
            or not isinstance(prepared.get('vm'), str)):
        raise ValueError('Only a failed pre-test setup can be reconciled as absent.')
    return attempt, prepared


def _setup_reconciled(directory, previous):
    if previous.get('status') != 'running' or previous.get('backend') != 'Parallels Windows':
        return False
    try:
        attempt, prepared = _failed_setup(directory, previous)
        receipt = json.loads((attempt/'setup-reconciliation.json').read_text())
        return (receipt.get('schema') == 1 and receipt.get('kind') == 'failed-setup-workspace-absent'
                and receipt.get('result_sha256') == file_sha256(directory/'result.json')
                and receipt.get('prepared_sha256') == file_sha256(attempt/'prepared.json')
                and receipt.get('source') == previous.get('source')
                and receipt.get('backend') == previous.get('backend')
                and receipt.get('inspection', {}).get('vm') == prepared['vm']
                and receipt['inspection'].get('token') == prepared['token']
                and receipt['inspection'].get('exists') is False)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def reconcile_setup(directory, inspect):
    """Append an absent-workspace receipt; never change the original failure.

    The project-owned inspector must verify the selected VM's ownership before
    making the generic fixed read-only workspace query. No removal or replay is
    permitted when that exact namespace still exists.
    """
    directory = Path(directory)
    with workspace_lock(directory.parent / (directory.name + '.attempt.lock')):
        if any(path.is_symlink() for path in (directory, directory/'result.json', directory/'.attempt-owner.json')):
            raise ValueError('Guest attempt records cannot be links.')
        previous = json.loads((directory/'result.json').read_text())
        owner = json.loads((directory/'.attempt-owner.json').read_text())
        if owner != dict(schema=1, source=previous.get('source'), backend=previous.get('backend')):
            raise ValueError('Failed setup source/backend ownership changed.')
        attempt, prepared = _failed_setup(directory, previous)
        path = attempt/'setup-reconciliation.json'
        if path.exists():
            if not _setup_reconciled(directory, previous):
                raise ValueError('Existing setup reconciliation no longer matches the retained attempt.')
            return path
        proof = inspect(prepared['vm'], prepared['token'])
        if (proof.get('vm') != prepared['vm'] or proof.get('token') != prepared['token']
                or proof.get('exists') is not False):
            raise ValueError('Guest workspace still exists or inspection identity differs; no retry authorized.')
        receipt = dict(schema=1, kind='failed-setup-workspace-absent', source=previous['source'],
                       backend=previous['backend'], result_sha256=file_sha256(directory/'result.json'),
                       prepared_sha256=file_sha256(attempt/'prepared.json'), inspection=proof,
                       inspected_at=datetime.now(timezone.utc).isoformat())
        save_json(path, receipt)
        return path


@contextmanager
def result_attempt(directory, source, backend):
    directory = Path(directory)
    with workspace_lock(directory.parent / (directory.name + '.attempt.lock')):
        if directory.is_symlink():
            raise ValueError('Guest result directory cannot be a link.')
        owner = directory / '.attempt-owner.json'
        result = directory / 'result.json'
        expected = dict(schema=1, source=source, backend=backend)
        previous = None
        if directory.exists():
            if owner.is_symlink() or result.is_symlink():
                raise ValueError('Guest attempt records cannot be links.')
            if owner.exists() and json.loads(owner.read_text()) != expected:
                raise ValueError('Guest attempt source/backend changed.')
            if not result.is_file():
                raise ValueError('Existing guest workspace needs reconciliation before retry.')
            previous = json.loads(result.read_text())
            if previous.get('source') != source or previous.get('backend') != backend:
                raise ValueError('Existing guest result belongs to another source/backend.')
            cleaned = previous.get('status') in {'passed', 'failed', 'cancelled'} and any(
                previous.get(key) is True for key in ('test_workspace_removed', 'guest_workspace_removed'))
            if not cleaned and not _setup_reconciled(directory, previous):
                raise ValueError('Previous guest operation needs reconciliation before retry.')
        else:
            directory.mkdir(parents=True, exist_ok=False)
        attempts = directory / 'attempts'
        if attempts.is_symlink():
            raise ValueError('Guest attempts directory cannot be a link.')
        attempts.mkdir(exist_ok=True)
        save_json(owner, expected)
        if previous is not None:
            # Keep exact previous report bytes, including all original timings.
            (attempts / ('retained-' + uuid4().hex + '.json')).write_bytes(result.read_bytes())
        attempt = attempts / uuid4().hex
        save_json(result, dict(expected, status='running', attempt_directory=str(attempt)))
        try:
            yield attempt  # The backend creates its own fresh directory.
        finally:
            completed = attempt / 'result.json'
            if completed.is_file() and not completed.is_symlink():
                data = json.loads(completed.read_text())
                if data.get('source') != source or data.get('backend') != backend:
                    raise ValueError('Guest attempt produced mismatched evidence.')
                save_json(result, dict(data, attempt_directory=str(attempt)))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['reconcile-windows-setup'])
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--manager-checkout', type=Path, required=True)
    args = parser.parse_args()
    from logistics_build.guest_manager import verify
    from build_manager.vm import WindowsVM
    from build_manager.parallels import Parallels
    verify(args.manager_checkout, Path(__file__).resolve().parents[1])
    def inspect(vm, token):
        receipt, row = WindowsVM(args.manager_checkout).selected()
        if receipt['uuid'] != vm or row['status'] != 'running':
            raise ValueError('Reconciliation requires the exact running, receipt-owned Windows VM.')
        return dict(Parallels().inspect_windows_workspace(vm, token), vm=vm)
    with workspace_lock(args.directory.parent/'operation.lock'):
        path = reconcile_setup(args.directory, inspect)
    print(json.dumps(dict(status='reconciled-workspace-absent', receipt=str(path),
                          original_attempt_unchanged=True)))
