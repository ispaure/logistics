"""Stage selected public sources and verify genuine mobile runtime evidence."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

APP_MODULES = ('__init__.py', '__main__.py', 'documents.py', 'access.py', 'pickers.py', 'app.py', 'smoke.py',
               'preferences.py', 'preview.py', 'library.py', 'reading.py', 'library_ui.py',
               'chat.py', 'chat_transport.py', 'chat_ui.py', 'chat_fixture.py')
DOCUMENT_MODULES = (
    'features/__init__.py', 'features/books/__init__.py', 'features/books/epub.py',
    'features/books/metadata.py', 'features/comics/__init__.py',
    'features/comics/archive_io.py', 'features/comics/comicinfo.py',
    'features/comics/library.py', 'features/comics/pages.py',
    'services/__init__.py', 'services/zip_passwords.py',
    'features/lm/__init__.py', 'features/lm/domain.py', 'features/lm/screenshots.py',
)


def stage(repo, destination, *, testbed=False, allow_dirty=False):
    repo, destination = Path(repo).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError('Stage into a new directory; existing payloads are preserved.')
    paths = ['Python/logisticsmobile', 'Mobile', 'Python/tests/test_mobile_documents.py', 'Python/tests/test_mobile_hub.py',
             'Python/tests/test_mobile_readers.py',
             'Python/tests/test_mobile_chat.py',
             'Python/tests/portable_documents.py', 'Python/tests/books_fixture.py']
    paths.extend('Python/' + name for name in DOCUMENT_MODULES)
    dirty = bool(subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain', '--', *paths]))
    if dirty and not allow_dirty:
        raise ValueError('Commit mobile sources before creating a release/testbed payload.')
    destination.mkdir(parents=True)
    shared = repo / 'Python/commonUtils'
    spec = importlib.util.spec_from_file_location('shared_mobile_tools', shared / 'tools/mobile_ci.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.stage(shared, destination)
    def copy(original, relative):
        if original.is_symlink() or any(parent.is_symlink() for parent in original.parents if parent != repo):
            raise ValueError('Refusing linked mobile source: ' + str(relative))
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
    for name in APP_MODULES:
        copy(repo / 'Python/logisticsmobile' / name, Path('logisticsmobile') / name)
    copy(repo / 'LICENSE.md', Path('logisticsmobile/LICENSE.md'))
    copy(shared / 'LICENSE.md', Path('commonUtils/LICENSE.md'))
    for name in DOCUMENT_MODULES:
        copy(repo / 'Python' / name, Path(name))
    if testbed:
        for name in ('portable_documents.py', 'books_fixture.py', 'test_mobile_documents.py', 'test_mobile_hub.py',
                     'test_mobile_readers.py', 'test_mobile_chat.py'):
            copy(repo / 'Python/tests' / name, Path(name))
    manifest = json.loads((destination / 'source.json').read_text())
    manifest.update(logistics_commit=subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip(),
                    dirty=dirty, features=['text', 'markdown', 'epub', 'comics', 'lm'])
    for path in (destination / 'source.json', destination / 'logisticsmobile/source.json'):
        path.write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def verify(log, target, output):
    from importlib.util import spec_from_file_location, module_from_spec
    source = Path(__file__).resolve().parents[1] / 'Python/logisticsmobile/smoke.py'
    spec = spec_from_file_location('logistics_smoke_contract', source)
    contract = module_from_spec(spec)
    spec.loader.exec_module(contract)
    reports = [json.loads(line[len(contract.PREFIX):]) for line in Path(log).read_text(errors='replace').splitlines()
               if line.startswith(contract.PREFIX)]
    if len(reports) != 1:
        raise ValueError('Expected one complete mobile result.')
    report = reports[0]
    environment = {'android': 'android-emulator', 'ios': 'ios-simulator'}[target]
    manifest = report.get('source')
    if (report.get('schema') != 1 or report.get('suite') != 'logistics-mobile-documents'
            or report.get('target') != target or report.get('sys_platform') != target
            or report.get('environment') != environment or report.get('success') is not True
            or any(report.get(name) != 0 for name in ('failures', 'errors', 'skipped'))
            or report.get('tests_run') != len(contract.EXPECTED_TESTS)
            or report.get('expected_tests') != list(contract.EXPECTED_TESTS)
            or not isinstance(manifest, dict) or manifest.get('dirty') is not False
            or any(not isinstance(manifest.get(key), str) or len(manifest[key]) != 40
                   or any(c not in '0123456789abcdef' for c in manifest[key])
                   for key in ('logistics_commit', 'commonUtils_commit'))):
        raise ValueError('Missing, failed, skipped, dirty or wrong-runtime mobile evidence.')
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('stage')
    prepare.add_argument('destination', type=Path)
    prepare.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    prepare.add_argument('--testbed', action='store_true')
    prepare.add_argument('--allow-dirty', action='store_true', help='Local development only; rejected as mobile evidence')
    check = commands.add_parser('verify')
    check.add_argument('log', type=Path)
    check.add_argument('--target', choices=('android', 'ios'), required=True)
    check.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'stage':
        print(json.dumps(stage(args.repo, args.destination, testbed=args.testbed, allow_dirty=args.allow_dirty)))
    else:
        verify(args.log, args.target, args.output)


if __name__ == '__main__':
    main()
