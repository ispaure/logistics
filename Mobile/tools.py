"""Stage selected public sources and verify genuine mobile runtime evidence."""
import argparse
import ast
import importlib.util
import json
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess

APP_MODULES = ('ios_reader_chrome.py', 'ios_storage.py', 'keyboard.py', 'fold_layout.py', 'storage_ui.py', 'settings_ui.py', 'documentation_ui.py', 'saved_files_ui.py', 'screen_privacy.py', 'palette.py', 'workspace_navigation.py', 'document_choices.py', 'comic_layout_check.py', 'appearance.py', 'provider_ui.py', '__init__.py', '__main__.py', 'documents.py', 'pickers.py', 'app.py', 'smoke.py', 'navigation.py', 'workspace.py', 'recent_documents.py', 'adaptive_workspace.py', 'action_menu.py', 'reader_sessions.py', 'private_sessions.py', 'window_owners.py', 'window_scenes.py',
               'hub_ui.py', 'control_icons.py', 'hub_icons.py', 'browser_ui.py', 'folder_hub.py', 'local_sources.py', 'folder_hub_ui.py', 'preferences.py', 'locations.py', 'locations_ui.py', 'preview.py', 'library_edits.py', 'library.py', 'library_ui.py', 'reader_ui.py', 'reader_host.py', 'reader_controls.py', 'reader_chrome.py',
               'chat_fixture.py', 'resource_imports.py', 'files_ui.py', 'editor_picker.py', 'host_services.py', 'feature_hosts.py', 'folder_controller.py', 'hub_controller.py', 'locations_controller.py', 'storage_controller.py', 'browser_preview.py', 'comic_source.py')
DOCUMENT_MODULES = (
    'features/books/mutations.py', 'features/comics/mutations.py',
    'features/rclone/localcrypt/__init__.py', 'features/rclone/localcrypt/mobile/__init__.py', 'features/rclone/transfers/__init__.py', 'features/rclone/transfers/mobile/__init__.py',
    'features/text_editor/__init__.py', 'features/text_editor/mobile/__init__.py', 'features/text_editor/mobile/ui.py', 'features/text_editor/resources.py', 'features/text_editor/names.py', 'services/mobile_presentation.py',
    'features/lm/mobile/controller.py', 'features/rclone/mobile/controller.py', 'features/rclone/transfers/mobile/controller.py', 'services/workflow_host.py',
    'services/document_readers.py', 'services/archive_access.py', 'services/document_limits.py', 'features/rclone/mobile/host.py',
    'features/lm/mobile/storage.py', 'features/lm/mobile/transport.py', 'features/lm/mobile/ui.py', 'features/lm/mobile/presentation.py', 'features/lm/mobile/__init__.py',
    'features/rclone/mobile/storage_location.py',
    'features/rclone/mobile/session_privacy.py',
    'features/rclone/mobile/cloud_ui.py', 'features/rclone/transfers/mobile/ui.py', 'features/rclone/transfers/mobile/review_ui.py', 'features/rclone/localcrypt/mobile/ui.py', 'features/rclone/mobile/messages.py',
    'features/rclone/mobile/__init__.py', 'features/rclone/mobile/cloud.py', 'features/rclone/mobile/remote_readers.py', 'features/rclone/mobile/credential_vault.py', 'features/rclone/mobile/credential_packages.py', 'features/rclone/localcrypt/mobile/archive_source.py', 'features/rclone/mobile/previews.py', 'features/rclone/transfers/mobile/jobs.py', 'features/rclone/localcrypt/mobile/copies.py', 'features/rclone/localcrypt/mobile/resources.py',
    'features/rclone/__init__.py', 'features/rclone/transfers/transfer_options.py', 'features/rclone/transfers/review.py', 'features/rclone/remote_policy.py', 'features/rclone/transfers/local_policy.py', 'features/rclone/transfers/scope.py',
    'features/__init__.py', 'features/books/__init__.py', 'features/books/epub.py',
    'features/books/locations.py', 'features/books/themes.py', 'features/books/metadata.py', 'features/books/xhtml.py', 'features/comics/__init__.py',
    'features/books/mobile/appearance.py', 'features/books/mobile/typography.py', 'features/books/mobile/speech.py', 'features/books/mobile/speech_native.py', 'features/books/mobile/android/io/github/ispaure/logistics/books/BookSpeechListener.java', 'features/books/mobile/speech_view.py',
    'features/books/mobile/provider_reader.py', 'features/books/mobile/private_view.py', 'features/books/mobile/metadata.py', 'features/books/mobile/text_reader.py', 'features/books/mobile/navigation.py', 'features/books/mobile/__init__.py', 'features/books/mobile/content.py', 'features/books/mobile/presentation.py',
    'features/comics/catalog_values.py', 'features/comics/mobile/collection.py', 'features/comics/mobile/private_batch.py', 'features/comics/mobile/index.py', 'features/comics/edit_state.py', 'features/comics/mobile/metadata.py', 'features/comics/reading.py', 'features/comics/mobile/navigation.py', 'features/comics/mobile/pages.py', 'features/comics/mobile/__init__.py', 'features/comics/mobile/validation.py', 'features/comics/mobile/composite.py', 'features/comics/mobile/presentation.py',
    'features/comics/archive_io.py', 'features/comics/comicinfo.py',
    'features/comics/library.py', 'features/comics/pages.py', 'features/comics/library_config.py',
    'configFile.ini', 'services/build_version.py', 'services/identifiers.py', 'services/folder_policy.py', 'services/__init__.py', 'services/zip_passwords.py', 'services/document_metadata.py',
    'features/lm/__init__.py', 'features/lm/domain.py', 'features/lm/streaming.py', 'features/lm/screenshots.py',
)


SHARED_REQUIRED_MODULES = ('formats/markdown_wiki.py', 'ui/native/markdown.py', 'ui/native/adaptive.py', 'ui/native/markdown_preview.py', 'runtime/resource_provider.py', 'runtime/local_files.py', 'runtime/resource_mutations.py', 'persistence/publication.py', 'filesystem/local_access.py', 'runtime/resource_selection.py', 'runtime/browsing.py', 'runtime/range_reader.py', 'runtime/archive_source.py', 'runtime/resource_search.py', 'ui/native_browser/__init__.py', 'ui/native/__init__.py', 'ui/native/image_canvas.py')

SHARED_REQUIRED_MODULES += ('ui/native/navigation_state.py', 'ui/native/navigation.py',
                            'ui/native/routes.py', 'ui/native/chrome.py',
                            'ui/native/android/io/github/ispaure/commonutils/ImageCanvasView.java',
                            'ui/native/android/io/github/ispaure/commonutils/NavigationBack.java')

SHARED_REQUIRED_MODULES += ('runtime/document_access.py', 'runtime/protected_keys.py',
                            'filesystem/snapshots.py', 'archives/rebuilding.py',
                            'ui/native/event_loop.py', 'ui/native/memory.py',
                            'ui/native/documents.py', 'ui/native/menus.py',
                            'ui/native/presentation.py', 'ui/native/editor_search.py')
SHARED_REQUIRED_MODULES += ('formats/code_syntax.py', 'formats/code_spans.py', 'formats/code_blade.py',
                            'ui/native/code_input.py',
                            'ui/native/android/io/github/ispaure/commonutils/CodeEditorSupport.java')


def validate_app_modules(root, modules=APP_MODULES, feature_modules=None):
    """Validate host and rclone-adapter imports against the isolated payload."""
    root = Path(root)
    feature_modules = tuple(name for name in DOCUMENT_MODULES if name.startswith('features/rclone/')) if feature_modules is None else feature_modules
    included = {'logisticsmobile/' + name for name in modules} | set(DOCUMENT_MODULES)
    included -= {name for name in DOCUMENT_MODULES if name.startswith('features/rclone/')}
    included.update(feature_modules)
    sources = [('logisticsmobile/' + name, root / name) for name in modules]
    sources += [(name, root.parent / name) for name in feature_modules if name.startswith('features/rclone/') and '/mobile/' in name]
    for relative, path in sources:
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=relative)
        package = relative.rsplit('/', 1)[0].replace('/', '.')
        for node in ast.walk(tree):
            dependencies = []
            if isinstance(node, ast.ImportFrom):
                module = importlib.util.resolve_name('.' * node.level + (node.module or ''), package) if node.level else node.module or ''
                dependencies = [module] if node.module else [module + '.' + alias.name for alias in node.names]
            elif isinstance(node, ast.Import):
                dependencies = [alias.name for alias in node.names]
            for dependency in dependencies:
                if not dependency.startswith(('logisticsmobile.', 'features.rclone.')):
                    continue
                target = dependency.replace('.', '/')
                if target + '.py' not in included and target + '/__init__.py' not in included:
                    raise ValueError(f'{path.name} imports unstaged {dependency}; '
                                     'add its module to the mobile payload before building.')


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
    validate_app_modules(repo / 'Python/logisticsmobile')
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
    # Preserve repository-relative documentation links inside the app package.
    doc_roots = [repo / 'docs', repo / 'Python/ui_new/bulk_rename/docs']
    doc_roots += [owner / 'docs' for owner in (repo / 'Python/features').iterdir()
                  if owner.is_dir() and not owner.is_symlink() and (owner / 'docs').is_dir()]
    for doc_root in doc_roots:
        for page in sorted(doc_root.rglob('*.md')):
            copy(page, Path('logisticsmobile/help') / page.relative_to(repo))
    copy(repo / 'README.md', Path('logisticsmobile/help/README.md'))
    copy(repo / 'LICENSE.md', Path('logisticsmobile/LICENSE.md'))
    copy(shared / 'LICENSE.md', Path('commonUtils/LICENSE.md'))
    for name in DOCUMENT_MODULES:
        copy(repo / 'Python' / name, Path(name))
    # Briefcase copies package sources, not payload-root configuration files.
    copy(repo / 'Python/configFile.ini', Path('services/configFile.ini'))
    if testbed:
        for name in ('portable_documents.py', 'books_fixture.py', 'test_mobile_documents.py', 'test_mobile_hub.py',
                     'test_mobile_readers.py', 'test_mobile_chat.py', 'test_mobile_cloud.py', 'test_mobile_vault.py', 'test_mobile_localcrypt.py'):
            copy(repo / 'Python/tests' / name, Path(name))
    manifest = json.loads((destination / 'source.json').read_text())
    manifest['commonUtils_dirty'] = manifest.get('commonUtils_dirty', False) or new_shared
    manifest.update(logistics_commit=subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip(),
                    dirty=dirty or manifest.get('commonUtils_dirty', False), features=['text', 'markdown', 'epub', 'comics', 'lm', 'rclone'])
    manifest['logistics_committed_at'] = subprocess.check_output(
        ['git', '-C', str(repo), 'show', '-s', '--format=%cI', 'HEAD'], text=True).strip()
    # Identify the exact local source snapshot independently of commit IDs.
    digest = sha256()
    roots = ((destination, ''), (repo / 'Mobile/rclone_bridge', 'bridge/'),
             (repo / 'Mobile/native_tests', 'native-tests/'),
             (repo / 'Mobile/native_navigation', 'native-navigation/'))
    for root, prefix in roots:
        for path in sorted(root.rglob('*')):
            if path.is_file() and path.suffix in {'.py', '.go', '.java', '.json', '.ini', '.mod', '.sum'} and path.name != 'source.json':
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
