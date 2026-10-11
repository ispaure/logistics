"""Bounded IDE queries. No Qt widgets or project code execution."""
from pathlib import Path
import os
from threading import Lock

# Jedi's caches are process-global; different projects must serialize requests.
_analysis_lock = Lock()


def analyze(project, path, code, line, column, kind='definition'):
    try:
        import jedi
    except ImportError as error:
        raise RuntimeError('Python intelligence is unavailable. Synchronize the application dependencies; text editing remains available.') from error
    if len(code) > 1024 * 1024:
        raise ValueError('Analysis is limited to 1 MiB of text.')
    with _analysis_lock:
        context = jedi.Project(str(project.root), added_sys_path=project.sources(),
                               environment_path=project.python_interpreter, load_unsafe_extensions=False)
        script = jedi.Script(code=code, path=str(path), project=context)
        if kind == 'symbols':
            names = script.get_names(all_scopes=True, definitions=True, references=False)
        elif kind == 'completion':
            return [(name.name, name.complete) for name in script.complete(line, column)][:100]
        elif kind == 'help':
            return '\n\n'.join(name.docstring() for name in script.infer(line, column))[:12000]
        else:
            names = script.goto(line, column, follow_imports=True, follow_builtin_imports=False)
            if not names:
                names = script.infer(line, column)
        return [(str(name.module_path), name.line or 1, name.column or 0, name.name)
                for name in names if name.module_path][:200]


def project_files(project, query='', *, cancelled=lambda: False, limit=500):
    results = []
    visited = 0
    for root, directories, files in os.walk(project.root, followlinks=False):
        if cancelled():
            break
        relative = Path(root).relative_to(project.root)
        directories[:] = [name for name in directories if name not in project.excluded_paths
                          and (relative / name).as_posix() not in project.excluded_paths
                          and not (Path(root) / name).is_symlink()]
        for name in files:
            visited += 1
            path = relative / name
            if name not in project.excluded_paths and path.as_posix() not in project.excluded_paths and query.casefold() in str(path).casefold():
                results.append(str(path))
                if len(results) >= limit:
                    return results
            if visited >= 100000 or cancelled():
                return results
    return results


def search_project(project, query, *, cancelled=lambda: False):
    from commonUtils.persistence.text import read_text_file
    if not query:
        return []
    results = []
    for relative in project_files(project, cancelled=cancelled, limit=10000):
        if cancelled():
            break
        path = project.root / relative
        try:
            if path.stat().st_size > 1024 * 1024:
                continue
            text = read_text_file(path).text
        except (OSError, ValueError):
            continue
        for line, content in enumerate(text.splitlines(), 1):
            if query.casefold() in content.casefold():
                results.append((str(path), line, content.strip()[:180]))
                if len(results) >= 500:
                    return results
    return results
