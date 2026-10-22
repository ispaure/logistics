"""Separate generated deployment files from canonical sources and credentials."""
import os
from pathlib import Path
import shutil

WORKSPACE_ENV = 'LOGISTICS_DEPLOY_WORKSPACE'


def output_root(source_root):
    value = os.environ.get(WORKSPACE_ENV)
    return Path(value).resolve() if value else Path(source_root)


def prepare_workspace(source_root):
    source_root = Path(source_root)
    workspace = output_root(source_root)
    workspace.mkdir(parents=True, exist_ok=True)
    if workspace != source_root:
        shutil.copyfile(source_root / 'pyproject.toml', workspace / 'pyproject.toml')
        # Briefcase resolves test_sources even for a normal application project.
        # Keep this local input independent of any concurrently refreshed project.
        shutil.copytree(source_root / 'native_tests', workspace / 'native_tests',
                        dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
    (workspace / 'build').mkdir(exist_ok=True)
    return workspace
