"""Stage selected public sources and verify genuine mobile runtime evidence."""
import argparse
import importlib.util
import json
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess

APP_MODULES = ('__init__.py', '__main__.py', 'documents.py', 'access.py', 'pickers.py', 'app.py', 'smoke.py', 'navigation.py', 'native_navigation.py', 'routing.py', 'workspace.py', 'editors.py', 'adaptive_workspace.py', 'action_menu.py', 'reader_sessions.py', 'private_sessions.py', 'native_memory.py', 'window_owners.py', 'window_scenes.py',
               'preferences.py', 'locations.py', 'locations_ui.py', 'preview.py', 'library.py', 'reading.py', 'library_ui.py', 'reader_chrome.py', 'comic_canvas.py',
               'chat.py', 'chat_transport.py', 'chat_ui.py', 'chat_fixture.py', 'cloud.py', 'resource_imports.py', 'folder_download.py', 'pull_jobs.py', 'pull_jobs_ui.py', 'cloud_ui.py', 'native_loop.py', 'credential_vault.py', 'localcrypt.py', 'localcrypt_ui.py', 'file_resources.py', 'files_ui.py', 'crypt_stream.py', 'browser_preview.py', 'comic_source.py')
DOCUMENT_MODULES = (
    'features/__init__.py', 'features/books/__init__.py', 'features/books/epub.py',
    'features/books/metadata.py', 'features/comics/__init__.py',
    'features/comics/archive_io.py', 'features/comics/comicinfo.py',
    'features/comics/library.py', 'features/comics/pages.py',
    'services/__init__.py', 'services/zip_passwords.py', 'services/document_metadata.py',
    'features/lm/__init__.py', 'features/lm/domain.py', 'features/lm/screenshots.py',
)


SHARED_REQUIRED_MODULES = ('runtime/resource_provider.py', 'runtime/local_files.py', 'runtime/resource_mutations.py', 'persistence/publication.py', 'filesystem/local_access.py', 'runtime/resource_selection.py', 'runtime/browsing.py', 'runtime/range_reader.py', 'runtime/archive_source.py', 'runtime/resource_search.py', 'ui/native_browser/__init__.py')

def stage(repo, destination, *, testbed=False, allow_dirty=False):
    repo, destination = Path(repo).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError('Stage into a new directory; existing payloads are preserved.')
    paths = ['Python/logisticsmobile', 'Mobile', 'Python/tests/test_mobile_documents.py', 'Python/tests/test_mobile_hub.py',
             'Python/tests/test_mobile_readers.py', 'Python/tests/test_mobile_localcrypt.py',
             'Python/tests/test_mobile_chat.py', 'Python/tests/test_mobile_cloud.py', 'Python/tests/test_mobile_vault.py',
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
    module.stage(shared, destination, allow_dirty=allow_dirty)
    def copy(original, relative):
        if original.is_symlink() or any(parent.is_symlink() for parent in original.parents if parent != repo):
            raise ValueError('Refusing linked mobile source: ' + str(relative))
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
    # Explicit portable dependency: local development may include this new API
    # before it is committed, without admitting arbitrary untracked shared files.
    new_shared = False
    for name in SHARED_REQUIRED_MODULES:
        relative = Path('commonUtils') / name
        if not (destination / relative).exists():
            if not allow_dirty:
                raise ValueError('Commit required shared resource APIs before release staging.')
            copy(shared / name, relative)
            new_shared = True
    for name in APP_MODULES:
        copy(repo / 'Python/logisticsmobile' / name, Path('logisticsmobile') / name)
    copy(repo / 'LICENSE.md', Path('logisticsmobile/LICENSE.md'))
    copy(shared / 'LICENSE.md', Path('commonUtils/LICENSE.md'))
    for name in DOCUMENT_MODULES:
        copy(repo / 'Python' / name, Path(name))
    if testbed:
        for name in ('portable_documents.py', 'books_fixture.py', 'test_mobile_documents.py', 'test_mobile_hub.py',
                     'test_mobile_readers.py', 'test_mobile_chat.py', 'test_mobile_cloud.py', 'test_mobile_vault.py', 'test_mobile_localcrypt.py'):
            copy(repo / 'Python/tests' / name, Path(name))
    manifest = json.loads((destination / 'source.json').read_text())
    manifest['commonUtils_dirty'] = manifest.get('commonUtils_dirty', False) or new_shared
    manifest.update(logistics_commit=subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip(),
                    dirty=dirty or manifest.get('commonUtils_dirty', False), features=['text', 'markdown', 'epub', 'comics', 'lm', 'rclone'])
    # Identify the exact local source snapshot independently of commit IDs.
    digest = sha256()
    roots = ((destination, ''), (repo / 'Mobile/rclone_bridge', 'bridge/'),
             (repo / 'Mobile/native_tests', 'native-tests/'),
             (repo / 'Mobile/native_navigation', 'native-navigation/'))
    for root, prefix in roots:
        for path in sorted(root.rglob('*')):
            if path.is_file() and path.suffix in {'.py', '.go', '.java', '.json', '.mod', '.sum'} and path.name != 'source.json':
                digest.update((prefix + path.relative_to(root).as_posix()).encode() + b'\0')
                digest.update(path.read_bytes())
    manifest['source_sha256'] = digest.hexdigest()
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
