"""Verify explicit guest SDK sources; refill only recognized owned Git objects.

No checkout, reset, pull, remote fetch, environment install or profile mutation.
Arbitrary developer sources and working-tree-local overlays are never repaired.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from build_manager.dependency_sources import verify
from logistics_build.tooling_bootstrap import pin, private, linked

FETCH_BUDGET=30
GUIDANCE=('Guest manager source is not ready. Update project tooling, or clear the explicit manager checkout '
          'to use the published dependency pin. External developer checkouts must be updated by their owner.')


class ReadinessIssue(ValueError):
    """Bounded project-owned classification, never subprocess diagnostics."""


ROUTING = {'GIT_DIR','GIT_COMMON_DIR','GIT_WORK_TREE','GIT_INDEX_FILE','GIT_OBJECT_DIRECTORY',
    'GIT_ALTERNATE_OBJECT_DIRECTORIES','GIT_GRAFT_FILE','GIT_SHALLOW_FILE','GIT_NAMESPACE',
    'GIT_CEILING_DIRECTORIES','GIT_DISCOVERY_ACROSS_FILESYSTEM','GIT_EXEC_PATH','GIT_CONFIG'}


def safe_environment():
    if any(key in ROUTING or key.startswith('GIT_CONFIG_') for key in os.environ):
        raise ReadinessIssue('Git routing/configuration environment overrides must be unset before source readiness')
    return dict(os.environ,GIT_ALLOW_PROTOCOL='file',GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='Never')


def metadata_contained(checkout,boundary):
    """Gitfiles/submodules may point inside owner; external metadata cannot write."""
    def absolute(value):return Path(os.path.abspath(checkout/value if not Path(value).is_absolute() else value))
    if absolute(git(checkout,'rev-parse','--show-toplevel'))!=checkout:
        raise ReadinessIssue('Git working directory differs from owned checkout')
    metadata=[absolute(git(checkout,'rev-parse',flag)) for flag in ('--absolute-git-dir','--git-common-dir')]
    objects=absolute(git(checkout,'rev-parse','--git-path','objects'));metadata.append(objects)
    if any(not path.is_relative_to(boundary) or not unlinked(path) for path in metadata):
        raise ReadinessIssue('Git metadata or object store redirects outside the owned cache')
    alternates=objects/'info/alternates'
    if alternates.exists() and alternates.stat().st_size:
        raise ReadinessIssue('Alternate Git object stores are not eligible for automatic repair')
    for folder,directories,files in os.walk(objects,followlinks=False):
        if any(linked(Path(folder)/name) for name in (*directories,*files)):
            raise ReadinessIssue('Linked Git object-store entry is not eligible for automatic repair')


def git(folder,*args,check=True,timeout=10):
    result=subprocess.run(['git','-C',str(folder),*args],capture_output=True,text=True,timeout=timeout,env=safe_environment())
    if check and result.returncode:raise ReadinessIssue('Git source metadata could not be read')
    return result.stdout.strip() if check else result.returncode==0


def unlinked(path):
    return not any(linked(part) for part in (path,*path.parents))


def clean(checkout):
    if not unlinked(checkout) or not unlinked(checkout/'Python/commonUtils'):
        raise ReadinessIssue('Linked checkout or dependency is not eligible')
    for folder in (checkout,checkout/'Python/commonUtils'):
        if git(folder,'status','--porcelain','--untracked-files=all'):
            raise ReadinessIssue('Selected managed checkout or dependency has local changes')


def owned_target(root,checkout,declared):
    """A directory name alone never authorizes changing a Git object store."""
    cache=private(root)/'tooling';proof=checkout.with_suffix('.ownership.json')
    if checkout.parent!=cache or not re.fullmatch('[0-9a-f]{40}',checkout.name):return False
    if not unlinked(checkout) or not unlinked(proof):raise ReadinessIssue('Linked checkout or ownership proof is not eligible')
    try:identity=json.loads(proof.read_text())
    except (OSError,ValueError):return False
    expected=dict(declared,root=str(root),revision=checkout.name)
    if identity!=expected:return False
    clean(checkout)
    for folder in (checkout,checkout/'Python/commonUtils'):
        metadata_contained(folder,checkout)
    if git(checkout,'config','--get','remote.origin.url')!=declared['repository']:
        raise ReadinessIssue('Checkout repository differs from declared manager repository')
    verify(checkout,checkout.name,pinned_source=False)
    return True


def installed_source(root,declared):
    """Trust the actual imported SDK, not a GUI candidate or directory label."""
    import build_manager
    origin=Path(build_manager.__file__).absolute()
    checkout=private(root)/'tooling'/declared['revision']
    if origin!=checkout/'Python/build_manager/__init__.py' or not unlinked(origin):
        raise ReadinessIssue('Imported SDK is not this project owned declared-pin checkout')
    clean(checkout)
    for folder in (checkout,checkout/'Python/commonUtils'):
        metadata_contained(folder,checkout)
    if git(checkout,'config','--get','remote.origin.url')!=declared['repository']:
        raise ReadinessIssue('Checkout repository differs from declared manager repository')
    _,dependency=verify(checkout,declared['revision'],pinned_source=False)
    return checkout,dependency


def available(checkout,revision):
    return git(checkout,'cat-file','-e',revision+'^{commit}',check=False)


def ensure(root,snapshot,checkout,source):
    """Return before VM setup/start; only missing objects may change on repair."""
    if not checkout or source.get('run_overrides',{}).get('testing.manager_source')=='working-tree-local':
        return dict(status='not-needed')
    root=Path(root).resolve();checkout=Path(os.path.abspath(Path(checkout).expanduser()))
    try:declared=pin(snapshot)
    except ValueError:
        raise ValueError(f'Guest manager source {checkout}; declared revision unavailable: invalid dependency pin. {GUIDANCE}') from None
    revision=declared['revision']
    try:
        safe_environment()
        if not unlinked(checkout):raise ReadinessIssue('Linked checkout is not eligible')
        owned=owned_target(root,checkout,declared)
        if available(checkout,revision):
            dependency=git(checkout,'ls-tree',revision,'Python/commonUtils').split()[2]
            if available(checkout/'Python/commonUtils',dependency):
                verify(checkout,revision,pinned_source=True)
                return dict(status='verified',revision=revision,commonUtils=dependency)
        if not owned:raise ReadinessIssue('Required objects are missing and target ownership proof is absent or mismatched; no automatic changes made')
        trusted,dependency=installed_source(root,declared)
        before=(git(checkout,'rev-parse','HEAD'),git(checkout/'Python/commonUtils','rev-parse','HEAD'))
        deadline=time.monotonic()+FETCH_BUDGET
        environment=safe_environment()
        for destination,origin,required in ((checkout,trusted,revision),
                (checkout/'Python/commonUtils',trusted/'Python/commonUtils',dependency)):
            if available(destination,required):continue
            if not owned_target(root,checkout,declared):raise ReadinessIssue('Target ownership changed before local object copy')
            installed_source(root,declared)
            remaining=deadline-time.monotonic()
            if remaining<=0:raise ReadinessIssue('Local Git object copy exceeded its time budget')
            # No remote names, refspec destinations, FETCH_HEAD or recursion.
            result=subprocess.run(['git','-C',str(destination),'fetch','--no-write-fetch-head',
                '--no-tags','--no-recurse-submodules',origin.as_uri(),required],
                capture_output=True,text=True,timeout=min(15,remaining),env=environment)
            if result.returncode:raise ReadinessIssue('Local Git object copy failed; no checkout or profile change was requested')
        clean(checkout)
        after=(git(checkout,'rev-parse','HEAD'),git(checkout/'Python/commonUtils','rev-parse','HEAD'))
        if before!=after:raise ReadinessIssue('Checkout HEAD changed concurrently; review the selected source')
        verify(checkout,revision,pinned_source=True)
        receipt=dict(status='objects-restored',revision=revision,commonUtils=dependency,checkout=str(checkout),
            reason='Exact local Git objects restored; HEADs and runtime files unchanged')
        print(json.dumps(dict(operation='guest-source-readiness',**receipt)),file=sys.stderr,flush=True)
        return receipt
    except (OSError,ValueError,IndexError,subprocess.SubprocessError) as error:
        reason = str(error) if isinstance(error,ReadinessIssue) else ('Local Git operation timed out' if isinstance(error,subprocess.TimeoutExpired) else 'Pinned source verification failed')
        raise ValueError(f'Guest manager source {checkout}; declared revision {revision}: {reason}. {GUIDANCE}') from None


def before_transfer(snapshot,checkout,*,working_tree=None):
    """Recheck before scratch/archive creation; ownership still needs all proofs."""
    if working_tree:return dict(status='not-needed')
    checkout=Path(os.path.abspath(Path(checkout).expanduser()))
    proof=checkout.with_suffix('.ownership.json')
    if not unlinked(checkout) or not unlinked(proof):raise ReadinessIssue('Linked checkout or ownership proof is not eligible')
    try:
        identity=json.loads(proof.read_text())
        owner=identity.get('root') if isinstance(identity,dict) else None
    except (OSError,ValueError):owner=None
    # An untrusted/missing marker never authorizes a repair. ensure() additionally
    # requires exact target path/marker and actual installed SDK origin for owner.
    return ensure(Path(owner) if isinstance(owner,str) else snapshot,snapshot,checkout,{})
