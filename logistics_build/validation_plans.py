"""Logistics-owned suite inventory and ordered commands, shared by CI and local UI."""
import ast
import json
from pathlib import Path


def desktop_checks(system, results, root=None):
    """The existing platform gate, with no platform's required checks omitted."""
    checks = [('test-structure', ['-m', 'logistics_build.test_structure', '--check'], 120)]
    if system == 'Windows':
        checks.append(('windows-native-ui', ['Python/tests/native_ui_smoke.py'], 60))
    from build_manager.test_manifest import discover
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    rows = discover(root, 'desktop')
    checks.extend((row['id'] + '.smoke', ['Python/tests/run_regressions.py', row['directory'],
                   '--isolate-modules', *row['smoke_args']], row['timeout']) for row in rows if row.get('smoke_args'))
    checks.extend((row['id'], ['Python/tests/run_regressions.py', row['directory'], '--isolate-modules'],
                   row['timeout'])
                  for row in rows)
    checks.extend([
        ('compression-parity', ['Python/tests/compare_comic_zip_versions.py', '--output-dir', str(Path(results) / 'parity')], 600),
    ])
    if system == 'Windows':
        # The measured full Windows Logistics inventory needs about 1900s.
        # Keep smoke gates and all other platforms on their declared budgets.
        minimums = {'logistics': 2100}
        checks = [(name, argv, max(timeout, minimums.get(name, 0)))
                  for name, argv, timeout in checks]
    return checks


SUITES = {
    'shared-host': dict(owner='Python/commonUtils/tests', platforms=['macos', 'fedora', 'windows'],
                        entry='dev.py test shared', kind='contracts', required=True,
                        environments=['Qt/portable', 'native Toga contracts where selected'],
                        source_owner='commonutils', source_kind='host-tests'),
    'static': dict(owner='Scripts', platforms=['macos', 'fedora', 'windows'],
                   entry='dev.py lint', kind='contracts', required=True,
                   environments=['Host Python with Ruff'], source_kind='static-analysis'),
    'desktop': dict(owner='Python/tests', platforms=['macos', 'fedora', 'windows'],
                    entry='Python/tests/run_platform_checks.py', kind='platform', required=True,
                    environments=['Desktop Python with Qt'],
                    source_owner='logistics', source_kind='host-tests'),
    'mobile-host': dict(owner='mobile_build/tests', platforms=['macos', 'fedora', 'windows'],
                        entry='dev.py test mobile', kind='contracts', required=True,
                        environments=['Mobile host Python with toga_dummy'],
                        source_owner='mobile-host', source_kind='host-tests'),
    'release-tooling': dict(owner='.github/scripts', platforms=['macos', 'fedora', 'windows'],
                           entry='python -m unittest discover -s .github/scripts', kind='packaging', required=True,
                           environments=['Host Python'],
                           source_owner='release-tooling', source_kind='host-tests'),
    'manager': dict(owner='external build-deployment-manager', platforms=['macos', 'fedora', 'windows'],
                    entry='python -m build_manager.contracts', kind='contracts', required=False,
                    environments=['External manager SDK'], source_kind='external'),
    'native-ios': dict(owner='mobile_build/native_tests', platforms=['ios'],
                       entry='mobile_build/validation/ui_tools.py', kind='native', required=True,
                       devices=['iphone', 'duo', 'ipad'], build_once=True,
                       hosted_order='parallel after shared build', local_order='sequential',
                       environments=['Packaged iOS app'], source_owner='native',
                       source_kind='shared-native-cases-and-support'),
    'native-android': dict(owner='mobile_build/native_tests', platforms=['android'],
                           entry='mobile_build/validation/ui_tools.py', kind='native', required=True,
                           environments=['Packaged Android app'], source_owner='native',
                           source_kind='shared-native-cases-and-support'),
    'runtime': dict(owner='Python/mobile/smoke.py', platforms=['ios', 'android'],
                    entry='.github/workflows/mobile-runtime.yml', kind='runtime-testbed', required=True,
                    environments=['iOS and Android CPython testbeds'],
                    source_owner='runtime', source_kind='runtime-test-module'),
    'bridge': dict(owner='mobile_build/rclone_bridge', platforms=['macos', 'fedora', 'windows'],
                   entry='go test ./...', kind='integration', required=False,
                   environments=['Host Go toolchain'], source_owner='bridge', source_kind='go-tests'),
    'investigations': dict(owner='mobile_build/validation', platforms=['ios', 'android'],
                           entry='explicit individual probe', kind='optional-probe', required=False,
                           environments=['Probe-specific'], source_kind='individual-probes'),
}


def inventory(root):
    root = Path(root)
    declared_roots = {row['owner']: row for row in json.loads(
        (root / 'test-structure.json').read_text(encoding='utf-8'))['roots']}
    sources = {}
    suites = []
    for name, contract in SUITES.items():
        owner = root / contract['owner']
        files = sorted(str(p.relative_to(root)).replace('\\', '/')
                       for p in owner.rglob('test*.py')) if owner.is_dir() else []
        row = dict(name=name, **contract, test_files=files, file_count=len(files))
        source_owner = contract.get('source_owner')
        if source_owner is not None:
            if source_owner not in sources:
                declaration = declared_roots[source_owner]
                directory = root / declaration['directory']
                sources[source_owner] = sorted({
                    path.relative_to(root).as_posix()
                    for pattern in declaration['patterns']
                    for path in directory.rglob(pattern) if path.is_file()
                })
            source_files = sources[source_owner]
            row.update(source_files=source_files, source_count=len(source_files))
            if contract['source_kind'] == 'host-tests':
                row['standalone_files'] = sorted(set(source_files).difference(files))
        declaration = (('mobile_build/native_tests/tests/logisticsmobile/__init__.py', 'CASES')
                       if name.startswith('native-') else
                       ('Python/mobile/smoke.py', 'EXPECTED_TESTS') if name == 'runtime' else None)
        if declaration:
            path, variable = declaration
            for node in ast.parse((root / path).read_text()).body:
                if (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                        and node.targets[0].id == variable):
                    row['case_ids'] = list(ast.literal_eval(node.value))
                    row['case_owner'] = path
                    row['case_count'] = len(row['case_ids'])
        suites.append(row)
    return dict(schema=1, suites=suites,
                inventory_fields={
                    'file_count': 'Legacy count of test*.py paths under the suite owner.',
                    'source_count': 'Files matching the declared test-structure root and patterns. '
                                    'Omitted for unenumerated layers. Native platforms share a source root.',
                    'standalone_files': 'Declared host drivers outside test*.py discovery.',
                    'case_count': 'Runnable cases from an explicit registry, when available.',
                },
                release_dependencies=['static', 'desktop', 'native-ios', 'native-android', 'runtime',
                                      'release-tooling', 'package', 'publish'],
                failure_policy='Failed, cancelled or required skipped gates block publication.',
                reuse_policy='Source, recursive dependency pin, toolchain and suite identity must match; reuse is labelled, never fresh validation.')
