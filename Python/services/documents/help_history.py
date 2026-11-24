"""Identify the shipped user and developer guides in normal file history."""

from pathlib import Path


def is_documentation(source, *, private_root=None):
    if not source or source.get('type') != 'local' or not source.get('path'):
        return False
    from .progress_identity import local_document_path
    module = Path(__file__).resolve()
    try:
        path = Path(source['path']) if private_root is None else local_document_path(private_root, source['path'])
        if not path.is_absolute():
            return False
        physical = path.resolve()
        return any(physical.is_relative_to(root) for root in (
            module.parents[3] / 'docs', module.parents[2] / 'mobile' / 'help' / 'docs'))
    except (OSError, ValueError, RuntimeError):
        return False
