"""Stage selected public sources and verify genuine mobile runtime evidence."""
import argparse
import ast
import importlib.util
import json
from hashlib import sha256
from pathlib import Path, PurePosixPath
import shutil
import subprocess

SOURCE_OWNERS = (
    'mobile', 'services', 'features/books', 'features/pdf', 'features/comics',
    'features/notebooks', 'features/images', 'features/lm', 'features/rclone', 'features/text_editor',
)
BASE_DOCUMENT_MODULES = ('features/__init__.py', 'configFile.ini')


def load_source_modules(repo):
    """Aggregate strict, feature-owned allowlists without importing feature code."""
    inventories = {}
    for owner in SOURCE_OWNERS:
        manifest = Path(repo) / 'Python' / owner / 'mobile_sources.json'
        if manifest.is_symlink():
            raise ValueError('Refusing linked mobile source manifest: ' + owner)
        data = json.loads(manifest.read_text())
        if (not isinstance(data, dict) or set(data) != {'schema', 'modules'}
                or type(data['schema']) is not int or data['schema'] != 1
                or not isinstance(data['modules'], list)):
            raise ValueError('Invalid mobile source manifest: ' + owner)
        selected = []
        for name in data['modules']:
            if (not isinstance(name, str) or not name or '\\' in name or ':' in name
                    or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts
                    or PurePosixPath(name).as_posix() != name or PurePosixPath(name).suffix not in {'.py', '.java', '.m', '.js', '.css', '.html'}):
                raise ValueError('Invalid mobile source path in ' + owner)
            if name in selected:
                raise ValueError('Duplicate mobile source path in ' + owner)
            selected.append(name)
        inventories[owner] = tuple(selected)
    documents = list(BASE_DOCUMENT_MODULES)
    for owner in SOURCE_OWNERS:
        if owner != 'mobile':
            documents.extend(owner + '/' + name for name in inventories[owner])
    return inventories['mobile'], tuple(documents)


APP_MODULES, DOCUMENT_MODULES = load_source_modules(Path(__file__).resolve().parents[1])

# Explicit local-development supplements to the shared mobile allowlist.
# Release staging still requires every member to be committed.
SHARED_REQUIRED_MODULES = (
    # Filesystem snapshots and local objects.
    'filesystem/local_access.py',
    'filesystem/objects.py',
    'filesystem/snapshots.py',
    # Atomic publication and persistence.
    'persistence/atomic.py',
    'persistence/publication.py',
    # Portable archive operations.
    'archives/callbacks.py',
    'archives/rebuilding.py',
    # Document parsing and syntax.
    'formats/code_blade.py',
    'formats/code_spans.py',
    'formats/code_syntax.py',
    'formats/code_language.py',
    'runtime/choices.py',
    'formats/image_headers.py',
    'formats/markdown/__init__.py',
    'formats/markdown/file.py',
    'formats/markdown/editing.py',
    'formats/markdown/images.py',
    'formats/markdown/properties.py',
    'formats/markdown/wiki.py',
    # Portable resource, stream and lifecycle mechanisms.
    'runtime/browsing.py',
    'runtime/progress.py',
    'runtime/protected_keys.py',
    'runtime/resources/archives.py',
    'runtime/resources/documents.py',
    'runtime/resources/content.py',
    'runtime/resources/local.py',
    'runtime/resources/mutations.py',
    'runtime/resources/provider.py',
    'runtime/resources/range_reader.py',
    'runtime/resources/selection.py',
    'runtime/signals.py',
    'runtime/speech.py',
    'runtime/streams/progress.py',
    'runtime/streams/sse.py',
    # Portable query providers.
    'search/__init__.py',
    'search/indexed.py',
    'search/names.py',
    'search/providers.py',
    'search/text.py',
    # Shared native presentation and browser adapters.
    'ui/appearance/colors.py',
    'ui/appearance/formatting_glyphs.py',
    'ui/features/declarations.py',
    'ui/native/__init__.py',
    'ui/native/adaptive.py',
    'ui/native/android/io/github/ispaure/commonutils/CodeEditorSupport.java',
    'ui/native/android/io/github/ispaure/commonutils/DrawReady.java',
    'ui/native/android/io/github/ispaure/commonutils/FileListView.java',
    'ui/native/android/io/github/ispaure/commonutils/ImageCanvasView.java',
    'ui/native/android/io/github/ispaure/commonutils/NavigationBack.java',
    'ui/native/android/io/github/ispaure/commonutils/SpeechListener.java',
    'ui/native/appearance.py',
    'ui/native/bars.py',
    'ui/native/chrome.py',
    'ui/native/code_input.py',
    'ui/native/documents.py',
    'ui/native/draw_ready.py',
    'ui/native/editor_search.py',
    'ui/native/event_loop.py',
    'ui/native/forms.py',
    'ui/native/icons.py',
    'ui/native/image_canvas.py',
    'ui/native/keyboard.py',
    'ui/native/markdown.py',
    'formats/markdown/image_sources.py',
    'ui/native/markdown_preview.py',
    'ui/native/markdown_search.py',
    'ui/native/memory.py',
    'ui/native/menus.py',
    'ui/native/web_dropdown.py',
    'ui/native/navigation.py',
    'ui/native/navigation_state.py',
    'ui/native/password_input.py',
    'ui/native/presentation.py',
    'ui/native/private_webview.py',
    'ui/native/recycled_list.py',
    'ui/native/recycled_list_android.py',
    'ui/native/recycled_list_ios.py',
    'ui/native/routes.py',
    'ui/native/sliders.py',
    'ui/native/speech.py',
    'ui/native/text_size.py',
    'ui/native/transitions.py',
    'ui/native_browser/__init__.py',
    'ui/native_browser/lifecycle.py',
    'ui/native_browser/paginated.py',
    'ui/native_browser/presentation.py',
    'ui/native_browser/recycled.py',
)


def validate_app_modules(root, modules=APP_MODULES, feature_modules=None, *, document_modules=DOCUMENT_MODULES):
    """Check staged application/feature/service imports before a native build."""
    root = Path(root)
    included = {'mobile/' + name for name in modules} | set(document_modules)
    if feature_modules is not None:
        included = {name for name in included if not name.startswith('features/rclone/')}
        included.update(feature_modules)
    for relative in sorted(included):
        if not relative.endswith('.py'):
            continue
        path = root.parent / relative
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=relative)
        if relative.startswith('features/') and relative.endswith('/__init__.py'):
            # Desktop registration factories remain lazy in portable packages.
            tree.body = [node for node in tree.body if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        package = relative.rsplit('/', 1)[0].replace('/', '.')
        if relative.endswith('/__init__.py'):
            package = relative[:-len('/__init__.py')].replace('/', '.')
        class RuntimeImports(ast.NodeTransformer):
            def visit_If(self, node):
                if (isinstance(node.test, ast.Name) and node.test.id == 'TYPE_CHECKING'
                        or isinstance(node.test, ast.Attribute) and node.test.attr == 'TYPE_CHECKING'
                        and isinstance(node.test.value, ast.Name) and node.test.value.id == 'typing'):
                    alternative = ast.Module(body=node.orelse, type_ignores=[])
                    return self.generic_visit(alternative).body
                return self.generic_visit(node)
        tree = RuntimeImports().visit(tree)
        for node in ast.walk(tree):
            dependencies = []
            if isinstance(node, ast.ImportFrom):
                module = importlib.util.resolve_name('.' * node.level + (node.module or ''), package) if node.level else node.module or ''
                dependencies = [module] if node.module else [module + '.' + alias.name for alias in node.names]
                # "from package import module" also requires that selected child
                # when it is a source module rather than a public class/function.
                for alias in node.names:
                    child = module.replace('.', '/') + '/' + alias.name
                    if (root.parent / (child + '.py')).is_file():
                        dependencies.append(module + '.' + alias.name)
            elif isinstance(node, ast.Import):
                dependencies = [alias.name for alias in node.names]
            for dependency in dependencies:
                if not dependency.startswith(('mobile.', 'features.', 'services.')):
                    continue
                target = dependency.replace('.', '/')
                if target + '.py' not in included and target + '/__init__.py' not in included:
                    raise ValueError(f'{path.name} imports unstaged {dependency}; '
                                     'add its module to the owning mobile source manifest before building.')


def stage(repo, destination, *, testbed=False, allow_dirty=False):
    repo, destination = Path(repo).resolve(), Path(destination).resolve()
    app_modules, document_modules = load_source_modules(repo)
    if destination.exists():
        raise ValueError('Stage into a new directory; existing payloads are preserved.')
    paths = ['Python/mobile', 'mobile_build', 'Python/tests/test_mobile_documents.py', 'Python/tests/test_mobile_hub.py',
             'Python/tests/test_mobile_readers.py', 'Python/tests/test_mobile_localcrypt.py',
             'Python/tests/test_mobile_chat.py', 'Python/tests/test_mobile_cloud.py', 'Python/tests/test_mobile_vault.py',
             'Python/tests/portable_documents.py', 'Python/tests/books_fixture.py']
    paths.extend('Python/' + name for name in document_modules)
    paths.extend('Python/' + owner + '/mobile_sources.json' for owner in SOURCE_OWNERS)
    dirty = bool(subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain', '--', *paths]))
    if dirty and not allow_dirty:
        raise ValueError('Commit mobile sources before creating a release/testbed payload.')
    validate_app_modules(repo / 'Python/mobile', app_modules, document_modules=document_modules)
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
    for name in app_modules:
        copy(repo / 'Python/mobile' / name, Path('mobile') / name)
    # Briefcase derives the installed identity and main module from its app key.
    # Keep that key stable while the application source lives in Python/mobile.
    launcher = destination / 'logisticsmobile'
    launcher.mkdir()
    (launcher / '__init__.py').write_text('# Stable native application entry point.\n')
    (launcher / '__main__.py').write_text(
        'from mobile.app import main\n\nmain().main_loop()\n')
    for owner in SOURCE_OWNERS:
        copy(repo / 'Python' / owner / 'mobile_sources.json', Path(owner) / 'mobile_sources.json')
    # Preserve repository-relative documentation links inside the app package.
    for page in sorted((repo / 'docs').rglob('*.md')):
        # Old local checkouts may still keep their ignored QA archive here.
        if page.is_relative_to(repo / 'docs/development/mobile-evidence'):
            continue
        copy(page, Path('mobile/help') / page.relative_to(repo))
    copy(repo / 'README.md', Path('mobile/help/README.md'))
    copy(repo / 'LICENSE.md', Path('mobile/LICENSE.md'))
    copy(shared / 'LICENSE.md', Path('commonUtils/LICENSE.md'))
    for name in document_modules:
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
                    dirty=dirty or manifest.get('commonUtils_dirty', False), features=['text', 'markdown', 'epub', 'comics', 'lm', 'rclone', 'notebooks'])
    manifest['logistics_committed_at'] = subprocess.check_output(
        ['git', '-C', str(repo), 'show', '-s', '--format=%cI', 'HEAD'], text=True).strip()
    # Identify the exact local source snapshot independently of commit IDs.
    digest = sha256()
    roots = ((destination, ''), (repo / 'mobile_build/rclone_bridge', 'bridge/'),
             (repo / 'mobile_build/native_tests', 'native-tests/'),
             (repo / 'mobile_build/native_navigation', 'native-navigation/'))
    for root, prefix in roots:
        for path in sorted(root.rglob('*')):
            if path.is_file() and path.suffix in {'.py', '.go', '.java', '.m', '.json', '.ini', '.mod', '.sum'} and path.name != 'source.json':
                digest.update((prefix + path.relative_to(root).as_posix()).encode() + b'\0')
                digest.update(path.read_bytes())
    manifest['source_sha256'] = digest.hexdigest()
    for path in (destination / 'source.json', destination / 'mobile/source.json'):
        path.write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def verify(log, target, output, *, local_manifest=None):
    from importlib.util import spec_from_file_location, module_from_spec
    source = Path(__file__).resolve().parents[1] / 'Python/mobile/smoke.py'
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
            or not isinstance(manifest, dict) or (local_manifest is None and
                (manifest.get('dirty') is not False or report.get('local_source_sha256') is not None))
            or any(not isinstance(manifest.get(key), str) or len(manifest[key]) != 40
                   or any(c not in '0123456789abcdef' for c in manifest[key])
                   for key in ('logistics_commit', 'commonUtils_commit'))):
        raise ValueError('Missing, failed, skipped, dirty or wrong-runtime mobile evidence.')
    if local_manifest is not None:
        expected = json.loads(Path(local_manifest).read_text())
        if (manifest != expected or len(manifest.get('source_sha256', '')) != 64
                or report.get('local_source_sha256') != manifest['source_sha256']):
            raise ValueError('Local runtime evidence came from a different staged source.')
        report['verification_scope'] = 'local exact snapshot; not hosted release evidence'
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
