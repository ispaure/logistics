"""Retain immutable guest attempts while publishing the latest declared result."""
from contextlib import contextmanager
import json
from pathlib import Path
from uuid import uuid4

from build_manager.locking import workspace_lock
from build_manager.profiles import save_json


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
            if previous.get('status') not in {'passed', 'failed', 'cancelled'} or not any(
                    previous.get(key) is True for key in ('test_workspace_removed', 'guest_workspace_removed')):
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
