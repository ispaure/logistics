"""Static document-storage contracts, without importing editors or providers.

This is an architectural guard, not a Python sandbox. Resolve ordinary import
and assignment aliases; reject backend dependencies, policy inspection and raw
publication APIs. Explicit exceptions identify an operation and owning function,
never an entire editor. New descendants of a document package inherit the rules.
"""
import ast
import importlib.util
import re
from pathlib import Path


BACKENDS = ('features.rclone', 'commonUtils.runtime.resources.local',
            'commonUtils.runtime.resources.mutations', 'services.native')
BACKEND_ATTRIBUTES = {'localcrypt', 'encrypted_path', 'remote_storage', 'remote_source', 'storage_scope'}
RAW_FUNCTIONS = {
    'open', 'builtins.open', 'io.open', 'io.FileIO', 'os.open', 'os.fdopen',
    'os.write', 'os.replace', 'os.rename', 'os.remove', 'os.unlink',
    'shutil.copy', 'shutil.copy2', 'shutil.copyfile', 'shutil.move', 'shutil.rmtree',
    'sqlite3.connect',
}
RAW_METHODS = {'remove_empty', 'write_bytes', 'write_text', 'read_bytes', 'read_text', 'unlink', 'rename',
               'replace_stream', 'replace_created', 'create_file'}


def prefix(name, prefixes):
    return any(name == item or name.startswith(item + '.') for item in prefixes)


def raw_function(name):
    method = name.rsplit('.', 1)[-1]
    return name in RAW_FUNCTIONS or (prefix(name, ('commonUtils.persistence',)) and method in {
        'atomic_write_bytes', 'atomic_write_json', 'atomic_write_text',
        'write_text_file', 'read_text_file', 'save_transaction', 'promote_path', 'rename_exclusive'})


class StorageVisitor(ast.NodeVisitor):
    def __init__(self, path, source_root):
        self.path, self.source_root = path, source_root
        self.bindings = [{}]
        self.scope = []
        self.findings = set()
        self.launcher = False
        self.calls = set()

    def report(self, node, operation):
        self.findings.add(('.'.join(self.scope) or '<module>', operation, node.lineno))

    def resolve(self, node):
        if isinstance(node, ast.Name):
            return next((scope[node.id] for scope in reversed(self.bindings) if node.id in scope), node.id)
        if isinstance(node, ast.Attribute):
            return self.resolve(node.value) + '.' + node.attr
        if isinstance(node, ast.Call):
            return self.resolve(node.func) + '()'
        return '?'

    def visit_Import(self, node):
        for alias in node.names:
            self.bindings[-1][alias.asname or alias.name.split('.')[0]] = alias.name if alias.asname else alias.name.split('.')[0]
            if prefix(alias.name, BACKENDS):
                self.report(node, 'backend:' + alias.name)

    def visit_ImportFrom(self, node):
        module = node.module or ''
        if node.level:
            package = '.'.join(self.path.relative_to(self.source_root).with_suffix('').parts[:-1])
            module = importlib.util.resolve_name('.' * node.level + module, package)
        for alias in node.names:
            if alias.name == '*' and prefix(module, ('commonUtils.persistence', 'commonUtils.runtime.resources', 'os', 'pathlib', 'io')):
                self.report(node, 'opaque-storage-import:' + module)
            name = module + '.' + alias.name
            self.bindings[-1][alias.asname or alias.name] = name
            if prefix(name, BACKENDS):
                self.report(node, 'backend:' + name)

    def visit_Constant(self, node):
        if isinstance(node.value, str) and prefix(node.value.partition(':')[0], BACKENDS):
            self.report(node, 'backend:' + node.value)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load) and raw_function(self.resolve(node)):
            self.report(node, 'raw-call:' + self.resolve(node))

    def visit_Attribute(self, node):
        name = self.resolve(node)
        if raw_function(name):
            self.report(node, 'raw-call:' + name)
        if node.attr == 'replace' and self.resolve(node.value) == 'pathlib.Path()':
            self.report(node, 'raw-method:replace')
        if node.attr in RAW_METHODS - {'rename'}:
            self.report(node, 'raw-method:' + node.attr)
        if node.attr in BACKEND_ATTRIBUTES:
            self.report(node, 'backend-policy:' + node.attr)
        self.generic_visit(node)

    def visit_Assign(self, node):
        value = self.resolve(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                if target.id == 'document_editor_id':
                    self.launcher = True
                self.bindings[-1][target.id] = value
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if isinstance(node.target, ast.Name):
            if node.target.id == 'document_editor_id':
                self.launcher = True
            if node.value is not None:
                self.bindings[-1][node.target.id] = self.resolve(node.value)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        # Defaults/decorators execute in the surrounding scope.
        for value in [*node.decorator_list, *node.args.defaults, *filter(None, node.args.kw_defaults)]:
            self.visit(value)
        self.scope.append(node.name)
        args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        self.bindings.append({arg.arg: arg.arg for arg in args})
        for child in node.body:
            self.visit(child)
        self.bindings.pop()
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self.scope.append(node.name)
        self.bindings.append({})
        self.generic_visit(node)
        self.bindings.pop()
        self.scope.pop()

    def visit_Call(self, node):
        name = self.resolve(node.func)
        self.calls.add(('.'.join(self.scope) or '<module>', name))
        method = name.rsplit('.', 1)[-1]
        if name.rsplit('.', 1)[-1] == 'DocumentLauncherContribution':
            self.launcher = True
        if prefix(name, BACKENDS):
            self.report(node, 'backend:' + name)
        if name in ('getattr', 'hasattr', 'setattr') and len(node.args) > 1:
            attribute = node.args[1]
            if isinstance(attribute, ast.Constant) and attribute.value in BACKEND_ATTRIBUTES:
                self.report(node, 'backend-policy:' + attribute.value)
            elif isinstance(attribute, ast.Constant) and attribute.value in RAW_METHODS:
                self.report(node, 'raw-method:' + attribute.value)
        if name in ('zipfile.ZipFile', 'commonUtils.archives.zip_access.open_archive'):
            mode = next((kw.value for kw in node.keywords if kw.arg == 'mode'), node.args[1] if len(node.args) > 1 else None)
            memory = bool(node.args) and self.resolve(node.args[0]).startswith(('io.BytesIO()', 'io.StringIO()'))
            if mode is not None and not (isinstance(mode, ast.Constant) and mode.value == 'r') and not memory:
                self.report(node, 'archive-write:' + name)
        if name in RAW_FUNCTIONS:
            self.report(node, 'raw-call:' + name)
        elif prefix(name, ('commonUtils.persistence',)) and method in {
                'atomic_write_bytes', 'atomic_write_json', 'atomic_write_text',
                'write_text_file', 'read_text_file', 'save_transaction'}:
            self.report(node, 'raw-call:' + name)
        elif method in RAW_METHODS:
            self.report(node, 'raw-method:' + method)
        elif method == 'open':
            # Path(...) aliases identify filesystem reads. Unknown receivers can
            # be generic archive/provider streams, but write modes are reviewed.
            mode = next((kw.value for kw in node.keywords if kw.arg == 'mode'),
                        node.args[0] if node.args else None)
            explicit_mode = isinstance(mode, ast.Constant) and isinstance(mode.value, str) and bool(re.fullmatch(r'[rwaxbt+]+', mode.value))
            dynamic_mode = any(kw.arg == 'mode' and not isinstance(kw.value, ast.Constant) for kw in node.keywords)
            if name.startswith('pathlib.Path()') or explicit_mode or dynamic_mode:
                self.report(node, 'raw-method:open')
        self.generic_visit(node)


def document_errors(root, policy, sources, references):
    """Return violations and the automatically expanded module count."""
    packages = policy.get('document_packages', [])
    source_root = root / 'Python'
    paths = sources(root, {'portable_packages': packages})
    excluded = policy.get('document_external_packages', {})
    exceptions = policy.get('document_storage_exceptions', [])
    allowed = {}
    required = {}
    errors = []
    for module in excluded:
        if '._vendor' not in module or module not in paths or not prefix(module, packages):
            errors.append(f'Invalid external document codec exclusion: {module}')
    for entry in exceptions:
        key = (entry['module'], entry['scope'], entry['operation'])
        if not entry.get('reason', '').strip() or key in allowed or entry['module'] not in paths:
            errors.append(f'Invalid document storage exception: {key}')
        allowed[key] = entry.get('reason', '')
        required[key] = entry.get('via')
    used = set()
    count = 0
    for module, path in paths.items():
        if prefix(module, excluded):
            continue
        count += 1
        visitor = StorageVisitor(path, source_root)
        visitor.visit(ast.parse(path.read_text(encoding='utf-8')))
        for scope, operation, line in sorted(visitor.findings):
            key = module, scope, operation
            # Backend selection/policy is never exempted inside editors.
            via = required.get(key)
            anchored = not via or any((scope == owner or scope.startswith(owner + '.')) and call == via
                                     for owner, call in visitor.calls)
            if key in allowed and not operation.startswith(('backend', 'opaque-storage-import')) and anchored:
                used.add(key)
            else:
                errors.append(f'Document storage boundary: {path.relative_to(root)}:{line} {scope} -> {operation}')
        # Include deferred module factories using the existing reference scanner.
        for dependency in references(path, source_root):
            if prefix(dependency, BACKENDS) and not any('backend:' + dependency == op for _, op, _ in visitor.findings):
                errors.append(f'Document storage boundary: {module} -> backend:{dependency}')
    for key in sorted(set(allowed) - used):
        errors.append(f'Unused document storage exception: {key}')
    # A new launcher must explicitly join this contract or declare its separate
    # filesystem-tool ownership. It cannot silently evade package coverage.
    workflows = policy.get('document_workflow_packages', {})
    for owner in sorted((source_root / 'features').iterdir()):
        if not owner.is_dir() or owner.is_symlink() or owner.name == 'emulation':
            continue
        package = 'features.' + owner.name
        if prefix(package, packages) or prefix(package, workflows):
            continue
        for path in sorted(owner.rglob('*.py')):
            if path.is_symlink() or any(part.startswith('_') for part in path.relative_to(owner).parts[:-1]):
                continue
            visitor = StorageVisitor(path, source_root)
            visitor.visit(ast.parse(path.read_text(encoding='utf-8')))
            if visitor.launcher:
                errors.append(f'Unclassified document launcher: {path.relative_to(root)}; declare document storage ownership')
    for module, reason in {**excluded, **workflows}.items():
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f'Document storage exclusion requires a reason: {module}')
    return errors, count
