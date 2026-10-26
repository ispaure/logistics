"""Inspect Logistics imports without importing features, toolkits or external links."""
import ast
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
INFRASTRUCTURE = {'application', 'feature_runtime', 'contributions', 'preferences', 'settings', 'discovery'}


def references(path, source_root):
    """Include relative imports and literal module[:attribute] references."""
    relative = path.relative_to(source_root).with_suffix('')
    package = '.'.join(relative.parts[:-1])
    tree = ast.parse(path.read_text(encoding='utf-8'))
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            if node.level:
                module = importlib.util.resolve_name('.' * node.level + module, package)
            result.add(module)
            result.update(module + '.' + alias.name for alias in node.names if alias.name != '*')
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            module, separator, attribute = node.value.partition(':')
            if separator and not re.fullmatch(r'[A-Za-z_]\w*(\.[A-Za-z_]\w*)*', attribute):
                continue
            application = re.fullmatch(r'(features|desktop|mobile|commonUtils|services)(\.[A-Za-z_]\w*)+', module)
            toolkit = re.fullmatch(r'(PySide6|toga)(\.[A-Za-z_]\w*)*', module)
            if application or toolkit:
                result.add(module)
    return result


def feature_edges(root):
    host, feature = set(), set()
    feature_root = root / 'Python/features'
    for owner in sorted(feature_root.iterdir()):
        if not owner.is_dir() or owner.is_symlink() or owner.name.startswith('_') or owner.name == 'emulation':
            continue
        for path in owner.rglob('*.py'):
            if '__pycache__' in path.parts or path.is_symlink():
                continue
            source = path.relative_to(root).as_posix()
            for module in references(path, root / 'Python'):
                parts = module.split('.')
                if parts[0] in {'desktop', 'mobile'}:
                    # Preserve module-level approval when an imported symbol is added.
                    host.add((source, '.'.join(parts[:2])))
                if parts[0] == 'features' and len(parts) > 1 and parts[1] != owner.name and parts[1] not in INFRASTRUCTURE:
                    feature.add((owner.name, parts[1]))
    return host, feature


def portable_sources(root, policy):
    """Resolve reviewed modules/packages deterministically; never follow source links."""
    source_root = root / 'Python'
    found = {}
    def linked(path):
        current = source_root
        for part in path.relative_to(source_root).parts:
            current = current / part
            if current.is_symlink():
                return True
        return False
    for key, package in [('portable_modules', False), ('portable_packages', True)]:
        for name in policy.get(key, []):
            if not re.fullmatch(r'[A-Za-z_]\w*(\.[A-Za-z_]\w*)*', name):
                raise ValueError(f'Invalid portable module: {name!r}')
            relative = Path(*name.split('.'))
            target = source_root / relative if package else (source_root / relative).with_suffix('.py')
            if linked(target):
                raise ValueError(f'Portable source cannot traverse links: {name}')
            if not target.exists() or (package and not target.is_dir()) or (not package and not target.is_file()):
                raise ValueError(f'Portable source does not exist: {name}')
            paths = sorted(target.rglob('*.py')) if package else [target]
            for path in paths:
                if '__pycache__' in path.parts:
                    continue
                if linked(path):
                    raise ValueError(f'Portable source cannot traverse links: {path.relative_to(source_root)}')
                parts = path.relative_to(source_root).with_suffix('').parts
                module = '.'.join(parts[:-1] if parts[-1] == '__init__' else parts)
                found[module] = path
    return dict(sorted(found.items()))


def presentation_dependency(module):
    return (module.split('.')[0] in {'PySide6', 'toga', 'desktop', 'mobile'}
            or module == 'commonUtils.ui' or module.startswith('commonUtils.ui.'))


def check(root=ROOT):
    policy = json.loads((root / 'Scripts/architecture.json').read_text())
    host, feature = feature_edges(root)
    errors = []
    for label, actual, allowed in [('feature-to-host', host, policy['host_adapters']),
                                    ('cross-feature', feature, policy['feature_dependencies'])]:
        for edge in sorted(actual - {tuple(edge) for edge in allowed}):
            errors.append(f'Unapproved {label} dependency: {edge[0]} -> {edge[1]}')
    try:
        portable = portable_sources(root, policy)
    except ValueError as error:
        portable = {}
        errors.append(str(error))
    for name, path in portable.items():
        for module in sorted(references(path, root / 'Python')):
            if presentation_dependency(module):
                errors.append(f'Portable module {name} imports presentation: {module}')
    if __package__:
        from .document_architecture import document_errors
    else:
        from document_architecture import document_errors
    try:
        storage_errors, documents = document_errors(root, policy, portable_sources, references)
        errors.extend(storage_errors)
    except (ValueError, SyntaxError) as error:
        documents = 0
        errors.append(f'Document storage scope: {error}')
    for error in errors:
        print(error)
    print(f'Architecture: {len(host)} host adapters, {len(feature)} feature edges, {len(portable)} portable modules, {documents} document modules; {len(errors)} violations.')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(check())
