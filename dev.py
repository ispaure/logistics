"""Run Logistics developer checks. Start with: python dev.py --help."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent


def environment_python(mobile=False):
    environment = ROOT / ('mobile_build/.venv' if mobile else '.venv')
    return environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    setup_parser = commands.add_parser('setup', help='Install a declared desktop or mobile host environment')
    setup_parser.add_argument('suite', choices=('desktop', 'mobile'))
    setup_parser.add_argument('--dry-run', action='store_true')
    commands.add_parser('compatibility', help='List compatibility imports, canonical owners and current consumers')
    commands.add_parser('hygiene', help='Inspect indexed paths and recognizable private-key/token patterns')
    commands.add_parser('owners', help='List source owners and their developer guides')
    commands.add_parser('test-map', help='Print the project-owned suite inventory as JSON')
    structure = commands.add_parser('test-structure', help='Validate every test classification before execution')
    structure.add_argument('--inventory', action='store_true')
    owned_tests = commands.add_parser('test-owner', help='Run the test groups declared for a source owner')
    owned_tests.add_argument('owner')
    owned_tests.add_argument('--dry-run', action='store_true')
    owned_tests.add_argument('--profile', choices=('smoke', 'daily', 'full'), default='full')
    owned_tests.add_argument('--mode', choices=('fast', 'diagnostic'), default='diagnostic')
    owned_tests.add_argument('--fail-fast', action='store_true')
    commands.add_parser('toolchain', help='Check dependency pin consistency across host and app manifests')
    commands.add_parser('architecture', help='Check reviewed import boundaries without loading features')
    commands.add_parser('doctor', help='Inspect contributor environments without changing them')
    tests = commands.add_parser('test', help='Run desktop, mobile or shared host tests in isolated processes')
    tests.add_argument('suite', choices=('desktop', 'mobile', 'shared', 'bridge'))
    tests.add_argument('pattern', nargs='?', default='test*.py',
                       help='Test filename or quoted glob (default: all test files)')
    tests.add_argument('--native-python', type=Path,
                       help='Override the shared matrix Toga interpreter; --python overrides its Qt interpreter')
    tests.add_argument('--profile', choices=('smoke', 'daily', 'full'), default='full')
    tests.add_argument('--mode', choices=('fast', 'diagnostic'), default='diagnostic')
    tests.add_argument('--fail-fast', action='store_true')
    tests.add_argument('--inventory', action='store_true')
    tests.add_argument('--timings', type=Path)
    lint = commands.add_parser('lint', help='Run the CI correctness lint scope')
    for command in (tests, lint):
        command.add_argument('--python', type=Path, help='Use a specific environment Python executable')
        command.add_argument('--dry-run', action='store_true', help='Show the command without running it')
    args = parser.parse_args(argv)
    if args.command == 'test-structure':
        from logistics_build.test_structure import main as structure_main
        return structure_main(['--inventory'] if args.inventory else ['--check'])
    if args.command == 'test-map':
        import json
        from logistics_build.validation_plans import inventory
        print(json.dumps(inventory(ROOT), indent=2))
        return 0
    if args.command == 'hygiene':
        from Scripts.hygiene import check
        return check(ROOT)
    if args.command == 'compatibility':
        from Scripts.compatibility import inventory
        for name, canonical, consumers in inventory(ROOT):
            print(f'{name} -> {", ".join(canonical)} ({len(consumers)} production consumers)')
        return 0
    if args.command in ('owners', 'test-owner'):
        from Scripts.ownership import owners, test_owner
        if args.command == 'owners':
            for name, entry in sorted(owners(ROOT).items()):
                print(f"{name}: {entry['guide']}")
            return 0
        return test_owner(ROOT, args.owner, sys.executable, dry_run=args.dry_run,
                          profile=args.profile, mode=args.mode, fail_fast=args.fail_fast)
    if args.command == 'toolchain':
        from Scripts.toolchain import check
        return check(ROOT)
    if args.command == 'architecture':
        from Scripts.architecture import check
        return check(ROOT)
    if args.command == 'setup':
        from Scripts.development import setup
        return setup(ROOT, args.suite, environment_python, dry_run=args.dry_run)
    if args.command == 'doctor':
        from Scripts.development import doctor
        return doctor(ROOT, environment_python)
    from Scripts.development import run_checks, shared_test_groups
    if args.command == 'test':
        from logistics_build.test_structure import inventory
        try:
            structure_rows = inventory(ROOT)
        except (ValueError, OSError, SyntaxError) as error:
            parser.error(str(error))
        if args.suite == 'bridge':
            if args.pattern != 'test*.py' or args.native_python or args.timings:
                parser.error('Bridge selection uses execution profiles, not Python filename/interpreter options.')
            if args.inventory:
                import json
                print(json.dumps([r for r in structure_rows if r['owner'] == 'bridge'], indent=2))
                return 0
            from logistics_build.test_structure import run_bridge
            if args.dry_run:
                print('Validated bridge profile: ' + args.profile)
                return 0
            try:
                return run_bridge(structure_rows, args.profile, args.mode, args.fail_fast)
            except OSError as error:
                parser.error('Bridge prerequisite unavailable: ' + str(error))
        if args.native_python and args.suite != 'shared':
            parser.error('--native-python is only available for the shared suite.')
        if not args.pattern.endswith('.py') or any(c in args.pattern for c in '/\\'):
            parser.error('Use a test filename or quoted filename glob, not a path.')
        if args.suite == 'shared':
            groups = shared_test_groups(ROOT, args.pattern)
        else:
            mobile = args.suite == 'mobile'
            suite = ROOT / ('mobile_build/tests' if mobile else 'Python/tests')
            groups = [(args.suite, mobile, suite, args.pattern, [])]
        suite = groups[0][2]
        if not any(path.is_file() for path in suite.rglob(args.pattern)):
            parser.error(f'No test files match {args.pattern!r} in {suite.relative_to(ROOT)}.')
    else:
        groups = [('lint', False, None, None, [])]
    checks = []
    for label, mobile, suite, pattern, extra in groups:
        override = args.native_python if args.command == 'test' and args.suite == 'shared' and mobile else args.python
        # Resolving the interpreter symlink escapes a virtual environment.
        interpreter = Path(os.path.abspath(override.expanduser())) if override else environment_python(mobile)
        environment = os.environ.copy()
        # Unrelated PYTHONPATH entries can shadow this checkout's packages.
        environment['PYTHONPATH'] = os.pathsep.join((str(ROOT / 'Python'), str(ROOT)))
        environment['QT_QPA_PLATFORM'] = 'offscreen'
        if mobile:
            environment['TOGA_BACKEND'] = 'toga_dummy'
        elif args.command == 'test' and args.suite == 'shared':
            environment.pop('TOGA_BACKEND', None)
        if args.command == 'test':
            command = [str(interpreter), str(ROOT / 'Python/tests/run_regressions.py'),
                       str(suite), '--pattern', pattern, '--isolate-modules', *extra,
                       '--profile', args.profile, '--mode', args.mode]
            if args.fail_fast:
                command.append('--fail-fast')
            if args.inventory:
                command.append('--inventory')
            if args.timings:
                command.extend(['--timings', str(args.timings)])
        else:
            command = [str(interpreter), '-m', 'ruff', 'check', '--config',
                       'Python/pyproject.toml', 'dev.py', 'Python', 'mobile_build', 'Scripts', 'logistics_build', '.github/scripts']
        checks.append((label, interpreter, command, environment))
    try:
        return run_checks(ROOT, checks, dry_run=args.dry_run,
                          stop_on_failure=args.command == 'test' and (args.fail_fast or args.mode == 'fast'))
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    sys.exit(main())
