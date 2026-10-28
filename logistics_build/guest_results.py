"""Project-owned guest evidence collection and conditional cleanup outcomes."""
import json
import hashlib
from pathlib import Path
import subprocess
import time

from build_manager.profiles import save_json


class GuestResultLifecycle:
    def __init__(self, result, directory, backend, workspace_key):
        self.result, self.directory = result, Path(directory)
        if result.get('backend', backend) != backend:
            raise ValueError('Guest result backend differs from its lifecycle owner.')
        result['backend'] = backend
        self.backend, self.workspace_key = backend, workspace_key
        self.started = time.monotonic()
        self.collected = False
        # Persist ownership before any transfer/worker can outlive this wrapper.
        # An interrupted running record is recovery evidence, never a test pass.
        save_json(self.directory / 'result.json', self.result)

    def collect(self, collect, evidence, cleanup):
        """Collect before cleanup; preserve remote evidence if transfer fails.

        Collection success and evidence validity are distinct: an invalid report
        is retained locally for diagnosis, allowing the owned remote copy to be
        removed just as before. Transport admission/retry stays with each backend.
        """
        try:
            collect()
            self.collected = True
            evidence = Path(evidence)
            if evidence.is_file():
                report = json.loads(evidence.read_text())
                if report['source'] != self.result['source'] or report['backend'] != self.backend:
                    raise ValueError('Retrieved guest report belongs to different source/backend.')
                self.result['phases'] = report['phases']
                self.result['guest_result'] = str(evidence)
                if self.result['status'] == 'passed' and report['status'] != 'passed':
                    raise ValueError('Guest exit status disagrees with its required test result.')
            elif self.result['status'] == 'passed':
                raise ValueError('A passing guest process did not produce its required result.')
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
            self.result.update(status='failed', retrieval_error=str(error))
        if self.collected:
            try:
                cleanup()
                self.result[self.workspace_key + '_removed'] = True
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                self.result.update(status='failed', cleanup_error=str(error))
        else:
            self.result[self.workspace_key + '_preserved_for_recovery'] = True

    def finish(self):
        self.result['seconds'] = time.monotonic() - self.started
        save_json(self.directory / 'result.json', self.result)
        print(json.dumps(self.result), flush=True)



def waiting_progress(backend, stage):
    """Describe a headless wait without claiming observed guest test progress."""
    def present(event):
        state = 'reconciling worker receipt' if event['state'] == 'reconciling' else 'waiting for worker result'
        print(f"{backend} · {stage} · {state} · {event['seconds']:.0f}s (headless)", flush=True)
    return present


def verified_manager_completion(directory, source, backend, manager_commit, source_plan_identity=''):
    """Verify a completed manager-only guest run without rewriting its wrapper.

    Legacy Linux wrappers omitted their backend field. The independently bound
    guest plan/result supplies that identity; both original records remain intact.
    This receipt certifies only those manager contracts, never an application gate.
    """
    from pathlib import PurePosixPath, PureWindowsPath
    from build_manager.history import load_run
    from build_manager.workflows import verify_artifacts
    from commonUtils.runtime.streams import file_sha256
    directory = Path(directory)
    result_path = directory/'result.json'
    if directory.is_symlink() or result_path.is_symlink():
        raise ValueError('Guest completion records cannot be linked.')
    result = json.loads(result_path.read_text())
    if (result.get('schema') != 1 or result.get('status') != 'passed' or result.get('source') != source
            or result.get('backend', backend) != backend or not any(result.get(key) is True
                for key in ('guest_workspace_removed', 'test_workspace_removed'))):
        raise ValueError('Guest completion source, outcome or cleanup is not verified.')
    guest_path = Path(result.get('guest_result', ''))
    if not guest_path.is_relative_to(directory/'guest') or any(
            p.is_symlink() for p in (guest_path, *guest_path.parents) if p == directory or directory in p.parents):
        raise ValueError('Guest report must remain inside its collected attempt.')
    plan, report = load_run(guest_path)
    if (plan.source != source or plan.backend != backend or report.get('source') != source
            or report.get('backend') != backend or report['status'] != 'passed' or plan.effect != 'test'):
        raise ValueError('Collected manager test identity or outcome differs.')
    engine = report.get('engine', {})
    for name, commit in (('manager', manager_commit), ('commonUtils', source.get('commonUtils_commit'))):
        identity = engine.get(name, {})
        if (not isinstance(commit, str) or len(commit) != 40 or identity.get('commit') != commit
                or identity.get('dirty') is not False
                or identity.get('fingerprint') != hashlib.sha256(commit.encode()).hexdigest()):
            raise ValueError('Manager test checkout identity changed or is incomplete.')
    rows = {row['id']:row for row in report['phases']}
    if any(phase.required and rows.get(phase.id, {}).get('status') != 'passed' for phase in plan.phases):
        raise ValueError('Required manager test steps are missing or unsuccessful.')
    focused = next((p for p in plan.phases if p.id == 'focused'), None)
    path_type = PureWindowsPath if 'Windows' in backend else PurePosixPath
    manager_name = 'manager-' + result['operation'] if 'Windows' in backend else 'manager'
    expected_tests = path_type(result['workspace'])/manager_name/'Python'/'tests'
    if (focused is None or focused.argv[1:5] != ('-m','unittest','discover','-s')
            or len(focused.argv) != 9 or path_type(focused.argv[5]) != expected_tests
            or focused.argv[6:] != ('-p', 'test*.py', '-v')
            or any(p.effect not in {'inherit','test'} for p in plan.phases)):
        raise ValueError('Receipt requires the complete declared manager contract suite.')
    plan_path = guest_path.parent/'plan.json'
    if plan_path.is_symlink():
        raise ValueError('Collected manager plan cannot be linked.')
    files = [result_path, guest_path, plan_path]
    for phase in plan.phases:
        row = rows.get(phase.id)
        if row is None:
            continue
        verify_artifacts(row)
        if row.get('log') != phase.id+'.log':
            raise ValueError('Completed manager test log is missing.')
        log = guest_path.parent/row['log']
        if log.is_symlink():
            raise ValueError('Completed manager test log cannot be linked.')
        files.append(log)
    receipt = dict(schema=1, scope='complete retained manager contracts only', backend=backend,
                   source_plan_identity=source_plan_identity,
                   status='verified-passed', source_sha256=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest(),
                   manager=engine['manager'], commonUtils=engine['commonUtils'], guest_plan_identity=plan.identity,
                   legacy_backend_inferred='backend' not in result, cleanup_verified=True,
                   evidence={str(path):file_sha256(path) for path in files},
                   original_records_unchanged=True, fresh_execution=False)
    receipt['identity'] = hashlib.sha256(json.dumps(receipt,sort_keys=True).encode()).hexdigest()
    return receipt


def retained_guest_source(plan, backend, directory):
    """Use the captured backend input, not later plan display annotations."""
    module = 'logistics_build.windows_backend' if 'Windows' in backend else 'logistics_build.vm_backend'
    candidates = [phase.argv for phase in plan.phases
                  if module in phase.argv and '--source-identity' in phase.argv and '--results' in phase.argv]
    if len(candidates) != 1:
        raise ValueError('Source plan must declare exactly one selected guest capture.')
    command = candidates[0]
    source = json.loads(command[command.index('--source-identity')+1])
    original = Path(command[command.index('--results')+1])
    directory = Path(directory)
    if (directory.parent != original/'attempts' or len(directory.name) != 32
            or any(c not in '0123456789abcdef' for c in directory.name)):
        raise ValueError('Completed guest attempt is outside the reviewed source plan.')
    if (source.get('dirty') is not False or any(source.get(key) != plan.source.get(key)
            for key in ('logistics_commit','commonUtils_commit','fingerprint','dirty'))):
        raise ValueError('Captured guest source differs from its reviewed plan.')
    return source


if __name__ == '__main__':
    import argparse
    from build_manager.models import Plan
    parser=argparse.ArgumentParser(description='Verify retained complete manager guest tests without replay.')
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--source-plan',type=Path,required=True)
    parser.add_argument('--backend',required=True)
    parser.add_argument('--manager-commit',required=True)
    parser.add_argument('--expect-identity')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    source_plan=Plan.load(args.source_plan)
    source=retained_guest_source(source_plan,args.backend,args.directory)
    receipt=verified_manager_completion(args.directory,source,args.backend,args.manager_commit,source_plan.identity)
    if args.expect_identity is not None and receipt['identity'] != args.expect_identity:
        raise ValueError('Retained manager evidence changed; inspect its current identity before continuation.')
    if args.output:
        save_json(args.output,receipt)
    print(json.dumps(dict(status=receipt['status'],identity=receipt['identity'],scope=receipt['scope'],
                          fresh_execution=False,original_records_unchanged=True)))
