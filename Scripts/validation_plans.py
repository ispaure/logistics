"""Logistics-owned suite inventory and ordered commands, shared by CI and local UI."""
import ast
from pathlib import Path


def desktop_checks(system, results):
    """The existing platform gate, with no platform's required checks omitted."""
    checks = []
    if system == 'Windows':
        checks.append(('windows-native-ui', ['Python/tests/native_ui_smoke.py'], 60))
    checks.extend([
        ('commonutils', ['Python/tests/run_regressions.py', 'Python/commonUtils/tests', '--isolate-modules'], 600),
        ('logistics', ['Python/tests/run_regressions.py', 'Python/tests', '--isolate-modules'], 900),
        ('compression-parity', ['Python/tests/compare_comic_zip_versions.py', '--output-dir', str(Path(results) / 'parity')], 600),
    ])
    return checks


SUITES = {
    'shared-host': dict(owner='Python/commonUtils/tests', platforms=['macos', 'ubuntu', 'fedora', 'windows'],
                        entry='dev.py test shared', kind='contracts', required=True,
                        environments=['Qt/portable', 'native Toga contracts where selected']),
    'static': dict(owner='Scripts', platforms=['macos', 'ubuntu', 'fedora', 'windows'],
                   entry='dev.py lint', kind='contracts', required=True),
    'desktop': dict(owner='Python/tests', platforms=['macos', 'ubuntu', 'fedora', 'windows'],
                    entry='Python/tests/run_platform_checks.py', kind='platform', required=True),
    'mobile-host': dict(owner='mobile_build/tests', platforms=['macos', 'ubuntu', 'windows'],
                        entry='dev.py test mobile', kind='contracts', required=True),
    'release-tooling': dict(owner='.github/scripts', platforms=['macos', 'ubuntu', 'windows'],
                           entry='python -m unittest discover -s .github/scripts', kind='packaging', required=True),
    'native-ios': dict(owner='mobile_build/native_tests', platforms=['ios'],
                       entry='mobile_build/validation/ui_tools.py', kind='native', required=True,
                       devices=['iphone', 'duo', 'ipad'], build_once=True,
                       hosted_order='parallel after shared build', local_order='sequential'),
    'native-android': dict(owner='mobile_build/native_tests', platforms=['android'],
                           entry='mobile_build/validation/ui_tools.py', kind='native', required=True),
    'runtime': dict(owner='Python/mobile/smoke.py', platforms=['ios', 'android'],
                    entry='.github/workflows/mobile-runtime.yml', kind='runtime-testbed', required=True),
    'bridge': dict(owner='mobile_build/rclone_bridge', platforms=['macos', 'ubuntu', 'fedora', 'windows'],
                   entry='go test ./...', kind='integration', required=False),
    'investigations': dict(owner='mobile_build/validation', platforms=['ios', 'android'],
                           entry='explicit individual probe', kind='optional-probe', required=False),
}


def inventory(root):
    root = Path(root)
    suites = []
    for name, contract in SUITES.items():
        owner = root / contract['owner']
        files = sorted(str(p.relative_to(root)).replace('\\', '/')
                       for p in owner.rglob('test*.py')) if owner.is_dir() else []
        row = dict(name=name, **contract, test_files=files, file_count=len(files))
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
        suites.append(row)
    return dict(schema=1, suites=suites,
                release_dependencies=['static', 'desktop', 'native-ios', 'native-android', 'runtime',
                                      'release-tooling', 'package', 'publish'],
                failure_policy='Failed, cancelled or required skipped gates block publication.',
                reuse_policy='Source, recursive dependency pin, toolchain and suite identity must match; reuse is labelled, never fresh validation.')
