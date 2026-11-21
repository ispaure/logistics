"""Immutable repository command inputs, validated again on the existing worker."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from ...runner import GitError


def frozen(value):
    if isinstance(value, (list, tuple)):
        return tuple(frozen(item) for item in value)
    if isinstance(value, dict):
        return MappingProxyType({key: frozen(item) for key, item in value.items()})
    return value


@dataclass(frozen=True)
class GitCommand:
    repository: Path
    label: str
    method: str
    arguments: tuple = ()
    options: tuple = ()
    expected_branch: str | None = None

    @classmethod
    def capture(cls, repository, label, method, args=(), kwargs=None, *, expected_branch=None):
        return cls(Path(repository), label, method, frozen(args),
                   tuple((key, frozen(value)) for key, value in (kwargs or {}).items()), expected_branch)

    def execute(self, repository):
        if Path(repository.path) != self.repository:
            raise GitError('The repository changed. Reopen the command.')
        if self.expected_branch is not None and repository.status().branch != self.expected_branch:
            raise GitError('The active branch changed. Refresh before running this command.')
        return getattr(repository, self.method)(*self.arguments, **dict(self.options))
