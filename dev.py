"""Run Logistics developer checks. Start with: python dev.py --help."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def environment_python(mobile=False):
    environment = ROOT / ('Mobile/.venv' if mobile else '.venv')
    return environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    setup_parser = commands.add_parser('setup', help='Install a declared desktop or mobile host environment')
    setup_parser.add_argument('suite', choices=('desktop', 'mobile'))
    setup_parser.add_argument('--dry-run', action='store_true')
    commands.add_parser('owners', help='List source owners and their developer guides')
    owned_tests = commands.add_parser('test-owner', help='Run the test groups declared for a source owner')
    owned_tests.add_argument('owner')
    owned_tests.add_argument('--dry-run', action='store_true')
    commands.add_parser('architecture', help='Check reviewed import boundaries without loading features')
    commands.add_parser('doctor', help='Inspect contributor environments without changing them')
    tests = commands.add_parser('test', help='Run desktop or mobile host tests in isolated processes')
    tests.add_argument('suite', choices=('desktop', 'mobile'))
    tests.add_argument('pattern', nargs='?', default='test*.py',
                       help='Test filename or quoted glob (default: all test files)')
    lint = commands.add_parser('lint', help='Run the CI correctness lint scope')
    for command in (tests, lint):
        command.add_argument('--python', type=Path, help='Use a specific environment Python executable')
        command.add_argument('--dry-run', action='store_true', help='Show the command without running it')
    args = parser.parse_args(argv)
    if args.command in ('owners', 'test-owner'):
        from Scripts.ownership import owners, test_owner
        if args.command == 'owners':
            for name, entry in sorted(owners(ROOT).items()):
                print(f"{name}: {entry['guide']}")
            return 0
        return test_owner(ROOT, args.owner, sys.executable, dry_run=args.dry_run)
    if args.command == 'architecture':
        from Scripts.architecture import check
        return check(ROOT)
    if args.command == 'setup':
        from Scripts.development import setup
        return setup(ROOT, args.suite, environment_python, dry_run=args.dry_run)
    if args.command == 'doctor':
        from Scripts.development import doctor
        return doctor(ROOT, environment_python)
    mobile = args.command == 'test' and args.suite == 'mobile'
    interpreter = args.python.expanduser().resolve() if args.python else environment_python(mobile)
    environment = os.environ.copy()
    # Include the repository for tests importing Mobile tooling. Do not inherit
    # unrelated PYTHONPATH entries that can shadow this checkout's packages.
    environment['PYTHONPATH'] = os.pathsep.join((str(ROOT / 'Python'), str(ROOT)))
    environment['QT_QPA_PLATFORM'] = 'offscreen'
    if args.command == 'test':
        if not args.pattern.endswith('.py') or any(c in args.pattern for c in '/\\'):
            parser.error('Use a test filename or quoted filename glob, not a path.')
        suite = ROOT / ('Mobile/tests' if mobile else 'Python/tests')
        if not any(path.is_file() for path in suite.rglob(args.pattern)):
            parser.error(f'No test files match {args.pattern!r} in {suite.relative_to(ROOT)}.')
        if mobile:
            environment['TOGA_BACKEND'] = 'toga_dummy'
        command = [str(interpreter), str(ROOT / 'Python/tests/run_regressions.py'),
                   str(suite), '--pattern', args.pattern, '--isolate-modules']
    else:
        command = [str(interpreter), '-m', 'ruff', 'check', '--config',
                   'Python/pyproject.toml', 'dev.py', 'Python', 'Mobile', 'Scripts', '.github/scripts']
    print(f'Working directory: {ROOT}', flush=True)
    for name in ('PYTHONPATH', 'QT_QPA_PLATFORM', 'TOGA_BACKEND'):
        if name in environment:
            print(f'{name}={environment[name]}', flush=True)
    print(subprocess.list2cmdline(command) if os.name == 'nt' else shlex.join(command), flush=True)
    if args.dry_run:
        return 0
    if not interpreter.is_file():
        parser.error(f'Environment Python is missing: {interpreter}. '
                     'See docs/development/testing.md for setup, or pass --python PATH.')
    if not (ROOT / 'Python/commonUtils/__init__.py').is_file():
        parser.error('commonUtils is missing. Run git submodule update --init --recursive '
                     'in a fresh checkout; preserve any existing submodule edits first.')
    try:
        return subprocess.run(command, cwd=ROOT, env=environment).returncode
    except OSError as error:
        parser.error(f'Could not start the check: {error}')


if __name__ == '__main__':
    sys.exit(main())
