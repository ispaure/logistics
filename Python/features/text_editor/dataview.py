"""Notes Library's bounded, provider-backed JSON/custom-view compatibility subset.

This is an independent implementation, not an Obsidian plugin host. Authored
JavaScript runs in a disposable browser worker; this module owns its read API.
"""
import json
import posixpath
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from markdown_it import MarkdownIt
from commonUtils.formats.markdown import split_frontmatter
from commonUtils.runtime.operations import check_cancelled
from services.documents.storage import DocumentResource
from .notes import operation

MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 8 * 1024 * 1024
MAX_REQUESTS = 128
MAX_OUTPUT = 1024 * 1024


def source_lines(text):
    """CommonMark counts CR/LF lines, not Unicode separators inside text."""
    lines = re.findall(r'[^\r\n]*(?:\r\n|\r|\n|$)', text)
    return lines[:-1] if lines and not lines[-1] else lines


@dataclass
class ViewPlan:
    source: str
    spans: list
    scripts: list

    def render(self, results=None):
        lines = source_lines(self.source)
        for index in reversed(range(len(self.spans))):
            start, end = self.spans[index]
            value = results[index] if results is not None else 'Loading data view…'
            lines[start:end] = ['\n' + value + '\n\n']
        return ''.join(lines)


def view_plan(text):
    """Only complete, top-level dataviewjs fences execute; examples stay literal."""
    spans, scripts = [], []
    parts = split_frontmatter(text)
    offset = len(source_lines(parts.prefix))
    lines = source_lines(text)
    for token in MarkdownIt('commonmark').parse(parts.body):
        if token.type != 'fence' or token.level or token.info.strip().lower() != 'dataviewjs':
            continue
        start, end = token.map
        start, end = start + offset, end + offset
        # CommonMark also emits a fence token for an unclosed code block.
        closing = lines[end - 1].strip() if end > start + 1 else ''
        if len(closing) < len(token.markup) or closing.strip(token.markup[0]):
            continue
        spans.append((start, end))
        scripts.append(token.content)
    if len(scripts) > 64 or sum(len(code.encode('utf-8')) for code in scripts) > MAX_OUTPUT:
        raise ValueError('Data views exceed the 64-block / 1 MiB script limit.')
    return ViewPlan(text, spans, scripts)


class ViewFiles:
    """One render's read lease; no recursive discovery or persistent cleartext cache."""
    def __init__(self, library, note):
        self.library, self.note = library, library.contained(note)
        self.requests = self.total = 0

    def resolve(self, path, origin=None, *, view=False):
        if not isinstance(path, str) or not path or len(path) > 4096:
            raise ValueError('Data view paths must be nonempty library paths.')
        parsed = urlsplit(path)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or '\\' in path or '\x00' in path:
            raise ValueError('Data views require paths inside this Notes Library.')
        if path.startswith('/'):
            path = path.lstrip('/')
        elif not view and (origin is not None or path.startswith(('./', '../'))):
            base = self.note
            if origin is not None:
                base = self.resolve(origin, view=True)
            relative = PurePosixPath(base).relative_to(self.library.root or '.').as_posix()
            path = posixpath.join(posixpath.dirname(relative), path)
        # Check hidden components before normalizing, too.
        if any(part.startswith('.') and part not in ('.', '..') for part in path.split('/')):
            raise ValueError('Hidden configuration is not available to data views.')
        path = posixpath.normpath(path)
        if path == '..' or path.startswith('../'):
            raise ValueError('Data view path is outside this Notes Library.')
        return self.library.contained(posixpath.join(self.library.root, path))

    def read(self, path, cancelled):
        check_cancelled(cancelled)
        with operation(self.library.provider, cancelled):
            try:
                info = self.library.entry(path)
            except FileNotFoundError:
                return None
            if info['directory']:
                return None
            if not 0 <= info['size'] <= MAX_FILE:
                raise ValueError('Data view file exceeds the 2 MiB limit.')
            remaining = MAX_TOTAL - self.total
            if info['size'] > remaining:
                raise ValueError('Data view reads exceed the 8 MiB limit.')
            with DocumentResource(self.library.provider, path, max_bytes=min(MAX_FILE, remaining), independent=False) as resource:
                data = resource.read(cancelled=cancelled)
        self.total += len(data)
        if self.total > MAX_TOTAL:
            raise ValueError('Data view reads exceed the 8 MiB limit.')
        return data.decode('utf-8-sig')

    def matching_case(self, path, cancelled):
        """Match explicit path components only; never scan descendants."""
        folder, visited = self.library.root, 0
        parts = PurePosixPath(path).relative_to(folder or '.').parts
        with operation(self.library.provider, cancelled):
            for index, name in enumerate(parts):
                check_cancelled(cancelled)
                try:
                    rows = self.library.provider.list(folder, cancelled=cancelled)
                except (FileNotFoundError, NotADirectoryError, ValueError):
                    return None
                visited += len(rows)
                if visited > 10000:
                    raise ValueError('Custom view path lookup exceeds 10,000 entries. Use the exact filename case.')
                matches = [row for row in rows if row['name'] == name]
                if not matches:
                    matches = [row for row in rows if row['name'].casefold() == name.casefold()]
                if len(matches) > 1:
                    raise ValueError('Several files match this custom view path. Use the exact filename case.')
                if not matches or (index < len(parts) - 1 and not matches[0]['directory']):
                    return None
                folder = self.library.contained(matches[0]['path'])
        return folder

    def request(self, message, *, cancelled=lambda: False):
        """Return a JSON reply; cancellation must propagate to the owning host."""
        check_cancelled(cancelled)
        identity = message.get('id')
        try:
            self.requests += 1
            if self.requests > MAX_REQUESTS:
                raise ValueError('Data views exceed the 128-request limit.')
            kind = message.get('kind')
            path = self.resolve(message.get('path'), message.get('origin'), view=kind == 'view')
            if kind == 'load':
                candidates = [path]
                if not PurePosixPath(path).suffix:
                    candidates.append(path + '.json')
                if message.get('origin') is None and not message['path'].startswith(('/', './', '../')):
                    relative = self.resolve('./' + message['path'])
                    if relative != path:
                        candidates.append(relative)
                        if not PurePosixPath(relative).suffix:
                            candidates.append(relative + '.json')
                value = None
                for candidate in candidates:
                    value = self.read(candidate, cancelled)
                    if value is not None:
                        break
            elif kind == 'view':
                candidates = [path] if path.endswith('.js') else [path + '.js', posixpath.join(path, 'view.js')]
                value = None
                for candidate in candidates:
                    code = self.read(candidate, cancelled)
                    if code is not None:
                        value = dict(code=code)
                        break
                if value is None:
                    for candidate in candidates:
                        matched = self.matching_case(candidate, cancelled)
                        code = self.read(matched, cancelled) if matched is not None else None
                        if code is not None:
                            value = dict(code=code)
                            break
                if value is None:
                    tried = [PurePosixPath(candidate).relative_to(self.library.root or '.').as_posix()
                             for candidate in candidates]
                    raise ValueError('Custom view not found. Looked inside this Notes Library for: ' + ' or '.join(tried))
            else:
                raise ValueError('Unsupported data view file operation.')
            return dict(id=identity, value=value)
        except (OSError, ValueError, UnicodeError) as error:
            return dict(id=identity, error=str(error)[:500])


def javascript(value):
    return json.dumps(value, ensure_ascii=True).replace('<', '\\u003c')


def runtime_script(plan):
    from .dataview_script import SCRIPT
    return SCRIPT.replace('DATAVIEW_SCRIPTS', javascript(plan.scripts))


def completed_results(state, count):
    results = state.get('results')
    if not isinstance(results, list) or len(results) != count or not all(isinstance(row, str) for row in results):
        raise ValueError('Invalid data view results.')
    if sum(len(row.encode('utf-8')) for row in results) > MAX_OUTPUT:
        raise ValueError('Data view output exceeds 1 MiB.')
    return results
