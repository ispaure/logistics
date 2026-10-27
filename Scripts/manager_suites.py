"""Logistics suite routing, native evidence translation and release acceptance."""
import argparse
import ast
from dataclasses import replace
from fnmatch import fnmatchcase
import json
from pathlib import Path
import subprocess
import sys
import unittest
from uuid import uuid4

from build_manager.reporting import run_suite, write_junit


def selection(root, suite, operation, target, backend, pattern):
    if not suite:
        return
    rows = json.loads((Path(root) / 'build-project.json').read_text())['test_suites']
    if not any(row['id'] == suite and target in row['platforms'] and operation in row['operations'] for row in rows):
        raise ValueError('Unsupported Logistics test suite for this target/operation.')
    if backend == 'GitHub' or backend == 'Local Parallels VM':
        raise ValueError('Named suites currently require the owning local host; hosted/VM plans keep their complete declared gates.')
    if pattern and suite not in {'portable.contracts', 'desktop.ui'}:
        raise ValueError('Focused patterns cannot narrow native or release acceptance.')


def declared_cases(root, runtime=False):
    path = Path(root) / ('Python/mobile/smoke.py' if runtime else 'mobile_build/native_tests/tests/logisticsmobile/__init__.py')
    variable = 'EXPECTED_TESTS' if runtime else 'CASES'
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == variable for target in node.targets):
            return list(ast.literal_eval(node.value))
    raise ValueError('Missing project-owned native case inventory.')


def native_cases(data, root, target, runtime=False):
    report = data.get('report', data)
    expected = declared_cases(root, runtime)
    valid = (report.get('schema') == 1 and report.get('success') is True and report.get('target') == target
             and report.get('suite') == ('logistics-mobile-documents' if runtime else 'logistics-native-ui')
             and not report.get('error'))
    if runtime:
        valid = valid and (report.get('expected_tests') == expected and report.get('tests_run') == len(expected)
                           and all(report.get(key) == 0 for key in ('failures', 'errors', 'skipped')))
        passed = expected if valid else []
    else:
        passed = report.get('cases', [])
        valid = valid and passed == expected and report.get('expected_cases') == expected
    cases = [dict(name=name, classname=target + ('.runtime' if runtime else '.native'),
                  status='passed' if name in passed and valid else 'skipped', seconds=None,
                  message='' if name in passed and valid else 'No successful verified result for this case in this attempt.') for name in expected]
    if not valid:
        cases.append(dict(name='verified_native_inventory', classname='Logistics.acceptance', status='failed',
                          message=report.get('error') or data.get('error') or 'Native/runtime inventory is incomplete or unsuccessful.'))
    return cases


def with_reports(plan, target):
    if plan.backend == 'GitHub':
        return plan
    directory = Path(plan.workspace) / 'reports' / uuid4().hex
    phases = []
    for phase in plan.phases:
        if phase.kind != 'test':
            phases.append(phase)
            continue
        report = directory / (phase.id + '.xml')
        argv = list(phase.argv)
        if 'Python/tests/run_regressions.py' in argv:
            argv += ['--junit', str(report), '--report', str(report.with_suffix('.json'))]
        elif 'dev.py' in argv:
            pattern = argv[argv.index('desktop') + 1]
            argv = [argv[0], 'Python/tests/run_regressions.py', 'Python/tests', '--isolate-modules',
                    '--pattern', pattern, '--junit', str(report), '--report', str(report.with_suffix('.json'))]
        else:
            native = phase.id in {'android-native', 'android-runtime', 'iphone', 'duo', 'ipad', 'ios-runtime'}
            mode = ['native', '--root', phase.cwd, '--target', target, '--json', phase.artifacts[0]] if native else ['command']
            if phase.id in {'android-runtime', 'ios-runtime'}:
                mode += ['--runtime']
            argv = [argv[0], '-m', 'Scripts.manager_suites', *mode, '--junit', str(report),
                    '--name', phase.id, '--', *argv[1:]]
        inventory = phase.test_files
        if argv[1:2] == ['Python/tests/run_regressions.py']:
            test_root = Path(phase.cwd) / argv[2]
            pattern = argv[argv.index('--pattern') + 1] if '--pattern' in argv else 'test*.py'
            includes = [argv[index + 1] for index, arg in enumerate(argv) if arg == '--include-pattern']
            inventory = tuple(path.relative_to(test_root).as_posix() for path in sorted(test_root.rglob(pattern))
                              if path.is_file() and all(fnmatchcase(path.name, extra) for extra in includes))
        phases.append(replace(phase, test_files=inventory, argv=tuple(argv), artifacts=(*phase.artifacts, str(report)),
                              artifact_types=dict(phase.artifact_types, **{str(report): 'junit'})))
    return replace(plan, phases=tuple(phases))


def same_source(actual, expected):
    return all(actual.get(key) == expected.get(key) for key in ('logistics_commit', 'commonUtils_commit')) and actual.get('dirty') is False


def release_evidence(root, target, native, runtime, require_ipad=False):
    source = json.loads((Path(root) / '.manager-source.json').read_text())['source']
    if source.get('dirty'):
        raise ValueError('Release acceptance requires committed source.')
    if not native:
        raise ValueError('Required native UI evidence is missing.')
    if target == 'ios':
        kinds = [json.loads(Path(path).read_text()).get('kind') for path in native]
        expected_kinds = {'iphone', 'duo', 'ipad'} if require_ipad else {'iphone', 'duo'}
        if len(kinds) != len(set(kinds)) or set(kinds) != expected_kinds:
            raise ValueError('Required iOS device-family inventory is incomplete.')
    for path in native:
        data = json.loads(Path(path).read_text())
        report = data.get('report', data)
        if (data.get('status', 'passed') != 'passed' or not same_source(report.get('source', {}), source)
                or any(row['status'] != 'passed' for row in native_cases(data, root, target))):
            raise ValueError('Native UI source, inventory or outcome differs; skips cannot satisfy release acceptance.')
        if target == 'ios' and data.get('owned_simulator_removed') is not True:
            raise ValueError('Required owned simulator cleanup did not complete.')
    if not runtime or not Path(runtime).is_file():
        raise ValueError('Required ' + target + ' runtime evidence is missing; configure LOGISTICS_IOS_RUNTIME_EVIDENCE for iOS.')
    data = json.loads(Path(runtime).read_text())
    if (data.get('sys_platform') != target or not same_source(data.get('source', {}), source)
            or any(row['status'] != 'passed' for row in native_cases(data, root, target, True))):
        raise ValueError('Runtime source, native host, inventory or outcome differs.')
    return dict(schema=1, status='passed', source=source, target=target, native_reports=list(map(str, native)), runtime_report=str(runtime))


def with_host_gates(plan, desktop_python):
    """Tester release policy requires host contracts/UI as well as native proof."""
    from build_manager import Phase
    first = plan.phases[0]
    env = dict(first.environment, QT_QPA_PLATFORM='offscreen')
    from build_manager.test_manifest import phases as manifest_phases
    hosts = manifest_phases(first.cwd, 'mobile-host',
        {'desktop': desktop_python, 'mobile': first.argv[0]},
        ('Python/tests/run_regressions.py', '{directory}', '--isolate-modules'), environment=env)
    dependencies = tuple(phase.id for phase in hosts)
    phases = tuple(replace(phase, dependencies=dependencies) if not phase.dependencies and not phase.always else phase
                   for phase in plan.phases)
    return replace(plan, phases=(*hosts, *phases))


def acceptance_phase(plan, target):
    from build_manager import Phase
    directory = Path(plan.workspace) / 'reports' / uuid4().hex
    output, junit = directory / 'release-acceptance.json', directory / 'release-acceptance.xml'
    native = [phase.artifacts[0] for phase in plan.phases if phase.id in {'android-native', 'iphone', 'duo', 'ipad'}]
    runtime = next((phase.artifacts[0] for phase in plan.phases if phase.id in {'android-runtime', 'ios-runtime'}), '')
    import os
    if target == 'ios' and not runtime:
        runtime = os.environ.get('LOGISTICS_IOS_RUNTIME_EVIDENCE', '')
    first = plan.phases[0]
    argv = [first.argv[0], '-m', 'Scripts.manager_suites', 'acceptance', '--root', first.cwd,
            '--target', target, '--junit', str(junit), '--output', str(output)]
    for path in native:
        argv += ['--native', path]
    if runtime:
        argv += ['--runtime-report', runtime]
    if any(phase.id == 'ipad' for phase in plan.phases):
        argv += ['--require-ipad']
    retained = (str(junit), str(output), *([str(runtime)] if runtime else []))
    return Phase('release-acceptance', tuple(argv), first.cwd, dependencies=tuple(phase.id for phase in plan.phases),
                 environment=dict(first.environment), kind='acceptance', timeout=120, artifacts=retained,
                 artifact_types={str(junit): 'junit'}, effect='test')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['command', 'native', 'acceptance'])
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--target', choices=['ios', 'android'])
    parser.add_argument('--json', type=Path)
    parser.add_argument('--runtime', action='store_true')
    parser.add_argument('--junit', type=Path, required=True)
    parser.add_argument('--name', default='release.acceptance')
    parser.add_argument('--native', type=Path, action='append', default=[])
    parser.add_argument('--runtime-report', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--require-ipad', action='store_true')
    # REMAINDER after the action would swallow options. Split only the explicit
    # command delimiter; no command or shell string is inferred from report data.
    values = sys.argv[1:]
    split = values.index('--') if '--' in values else len(values)
    args = parser.parse_args(values[:split])
    command = values[split + 1:]
    args.junit.unlink(missing_ok=True)
    if args.action == 'acceptance':
        value = {}
        class Acceptance(unittest.TestCase):
            def test_required_native_and_runtime_inventory(self):
                value.update(release_evidence(args.root, args.target, args.native, args.runtime_report, args.require_ipad))
        result = run_suite(unittest.defaultTestLoader.loadTestsFromTestCase(Acceptance), args.junit, 'release.acceptance', fail_on_skip=True)
        if result['status'] == 'passed':
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(value, indent=2) + '\n')
        return int(result['status'] != 'passed')
    if not command:
        parser.error('A structured command after -- is required.')
    if args.action == 'native' and args.json:
        args.json.unlink(missing_ok=True)
    # Existing owning backends keep their process/lifecycle cleanup. The outer
    # manager owns this wrapper and its descendant group on cancellation.
    code = subprocess.run([sys.executable, *command], check=False).returncode
    if args.action == 'native':
        try:
            cases = native_cases(json.loads(args.json.read_text()), args.root, args.target, args.runtime)
        except (OSError, ValueError, KeyError, TypeError) as error:
            cases = [dict(name='verified_native_report', classname=args.name, status='error', message=str(error))]
    else:
        cases = [dict(name='command_gate', classname=args.name, status='passed' if code == 0 else 'failed',
                      message='' if code == 0 else 'Owning command exited with code ' + str(code))]
    if code and all(row['status'] == 'passed' for row in cases):
        cases.append(dict(name='command_exit', classname=args.name, status='failed', message='Owning command exited with code ' + str(code)))
    write_junit(args.junit, args.name, cases)
    return int(bool(code) or any(row['status'] != 'passed' for row in cases))


if __name__ == '__main__':
    raise SystemExit(main())
