"""Recoverable promotion of one Plex archive/settings generation."""
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4
from commonUtils.persistence import atomic_write_json
from commonUtils.persistence.publication import mutation_lock


def _signature(path):
    info = path.stat()
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


class PackagePublication:
    """Keep original files until every new member has been promoted.

    This is recovery for ordinary failures, not atomic visibility of a file set.
    If rollback conflicts or fails, originals and a journal remain for recovery.
    """
    def __init__(self, destination, outputs, obsolete=()):
        self.destination = Path(destination)
        self.outputs = tuple(Path(path) for path in outputs)
        self.obsolete = tuple(Path(path) for path in obsolete)
        names = [path.name for path in self.outputs]
        if 'journal.json' in names or any(path.name == 'journal.json' for path in self.obsolete):
            raise ValueError('journal.json is reserved for recovery metadata.')
        if len(names) != len(set(names)):
            raise ValueError('Package outputs must have distinct names.')
        self.recovery = self.destination / ('.logistics-plex-recovery-' + uuid4().hex)
        self.state = dict(schema=1, phase='prepared', originals=[], published={})

    def _save(self):
        atomic_write_json(self.recovery / 'journal.json', self.state)

    def _rollback(self):
        # Refuse to overwrite an unrelated edit made after our publication.
        for name, revision in self.state['published'].items():
            target = self.destination / name
            if target.exists() or target.is_symlink():
                if target.is_symlink() or _signature(target) != revision:
                    raise RuntimeError(f'Package changed during recovery: {target}')
                target.unlink()
        for name in self.state['originals']:
            backup = self.recovery / name
            if backup.is_symlink() or backup.is_junction() or (backup.exists() and not backup.is_file()):
                raise RuntimeError(f'Package recovery member is not a regular file: {backup}')
            if backup.exists():
                target = self.destination / name
                if target.exists() or target.is_symlink():
                    raise RuntimeError(f'Package recovery destination is occupied: {target}')
                os.replace(backup, target)
        shutil.rmtree(self.recovery)

    def publish(self):
        with mutation_lock:
            originals = {}
            for target in [*(self.destination / path.name for path in self.outputs), *self.obsolete]:
                if target.parent != self.destination or target.is_symlink() or target.is_junction() or (target.exists() and not target.is_file()):
                    raise ValueError(f'Package destination is not a regular file: {target}')
                if target.exists():
                    originals[target.name] = _signature(target)
            self.recovery.mkdir(mode=0o700)
            self.state['originals'] = list(originals)
            try:
                self._save()
                for name, revision in originals.items():
                    target = self.destination / name
                    if _signature(target) != revision:
                        raise RuntimeError(f'Package changed before publication: {target}')
                    os.replace(target, self.recovery / name)
                self.state['phase'] = 'publishing'
                self._save()
                for source in self.outputs:
                    target = self.destination / source.name
                    if target.exists() or target.is_symlink():
                        raise RuntimeError(f'Package destination appeared during publication: {target}')
                    # Record the staged inode before promotion, so rollback still
                    # knows ownership if a journal write fails after the rename.
                    revision = _signature(source)
                    os.replace(source, target)
                    revision[-1] = target.stat().st_ctime_ns
                    self.state['published'][source.name] = revision
                    self._save()
                self.state['phase'] = 'committed'
                self._save()
            except BaseException:
                try:
                    self._rollback()
                except Exception as recovery_error:
                    raise RuntimeError(f'Plex package rollback needs recovery at {self.recovery}: {recovery_error}') from recovery_error
                raise
            # Once committed, cleanup failure must not roll back a valid package.
            try:
                shutil.rmtree(self.recovery)
            except OSError as error:
                raise RuntimeError(f'Plex package published; recovery cleanup remains at {self.recovery}') from error

    @classmethod
    def recover(cls, directory):
        """Explicitly roll back an interrupted, uncommitted generation."""
        directory = Path(directory)
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError('Choose an ordinary Plex recovery directory.')
        journal = directory / 'journal.json'
        if journal.is_symlink() or not journal.is_file():
            raise ValueError('Recovery requires an ordinary journal file.')
        state = json.loads(journal.read_text())
        if not isinstance(state, dict):
            raise ValueError('Invalid package recovery journal.')
        if state.get('schema') != 1 or state.get('phase') not in {'prepared', 'publishing'}:
            raise ValueError('Recovery requires an uncommitted Plex publication journal.')
        originals, published = state.get('originals'), state.get('published')
        if not isinstance(originals, list) or not isinstance(published, dict):
            raise ValueError('Invalid package recovery members.')
        if any(not isinstance(revision, list) or len(revision) != 5 or
               any(type(value) is not int for value in revision) for revision in published.values()):
            raise ValueError('Invalid package recovery revision.')
        names = [*originals, *published]
        if any(not isinstance(name, str) or name in {'', '.', '..', 'journal.json'} or Path(name).name != name or '\\' in name for name in names):
            raise ValueError('Invalid package recovery member.')
        publication = cls(directory.parent, ())
        publication.recovery, publication.state = directory, state
        with mutation_lock:
            publication._rollback()
