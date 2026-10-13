"""Bounded read-only project tools. No project code is imported or executed."""
from pathlib import Path
import json
import os
from time import monotonic

MAX_FILE_BYTES = 256 * 1024


def tool(name, description, properties):
    return dict(type='function', function=dict(name=name, description=description,
        parameters=dict(type='object', properties=properties, required=list(properties), additionalProperties=False)))


TOOLS = [
    tool('list_files', 'List project-relative file paths containing query; use an empty query to browse.',
         {'query': {'type': 'string'}}),
    tool('search_files', 'Search project text for a literal, case-insensitive query. Returns paths and line numbers.',
         {'query': {'type': 'string'}}),
    tool('read_file', 'Read a project text file, using open editor text when available. Lines are 1-based; at most 200 per call.',
         {'path': {'type': 'string'}, 'start_line': {'type': 'integer', 'minimum': 1},
          'end_line': {'type': 'integer', 'minimum': 1}}),
]


class ProjectTools:
    def __init__(self, project, buffers=None):
        self.root = Path(project.root).resolve()
        if not self.root.is_dir():
            raise ValueError('The selected IDE project folder is unavailable.')
        self.name = project.name
        self.exclusions = tuple(project.excluded_paths) + ('.git',)
        self.buffers = dict(buffers or {})

    def path(self, relative):
        if not isinstance(relative, str) or not relative or len(relative) > 4096:
            raise ValueError('Use a project-relative file path.')
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Paths must stay inside the selected project.')
        current = self.root
        for index, part in enumerate(path.parts):
            current = current / part
            prefix = Path(*path.parts[:index + 1]).as_posix()
            if part in self.exclusions or prefix in self.exclusions or current.is_symlink():
                raise ValueError('Excluded paths and symbolic links are unavailable.')
        current.resolve().relative_to(self.root)
        return current

    def text(self, relative):
        path = self.path(relative)
        if relative in self.buffers:
            text = self.buffers[relative]
            if len(text.encode('utf-8')) > MAX_FILE_BYTES:
                raise ValueError('File exceeds the 256 KiB reading limit.')
            return text, 'editor snapshot'
        # O_NOFOLLOW also prevents replacing the final component with a link
        # between validation and open on platforms that support it.
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        if os.open in os.supports_dir_fd and hasattr(os, 'O_NOFOLLOW'):
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                for part in Path(relative).parts[:-1]:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                    os.close(directory)
                    directory = child
                descriptor = os.open(Path(relative).name, flags, dir_fd=directory)
            finally:
                os.close(directory)
        else:
            descriptor = os.open(path, flags)
        with os.fdopen(descriptor, 'rb') as stream:
            import stat
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError('Only regular text files can be read.')
            if os.fstat(stream.fileno()).st_size > MAX_FILE_BYTES:
                raise ValueError('File exceeds the 256 KiB reading limit.')
            content = stream.read(MAX_FILE_BYTES + 1)
        if len(content) > MAX_FILE_BYTES:
            raise ValueError('File exceeds the 256 KiB reading limit.')
        if b'\0' in content:
            raise ValueError('Binary files are unavailable.')
        return content.decode('utf-8-sig'), 'disk'

    def files(self, cancelled):
        visited = 0
        deadline = monotonic() + 5
        for directory, dirs, files in os.walk(self.root, followlinks=False):
            if cancelled() or monotonic() >= deadline:
                return
            relative = Path(directory).relative_to(self.root)
            kept = []
            for name in dirs:
                visited += 1
                if visited > 5000:
                    return
                try:
                    self.path((relative / name).as_posix())
                    kept.append(name)
                except (ValueError, OSError):
                    pass
            dirs[:] = sorted(kept)
            for name in sorted(files):
                visited += 1
                if visited > 5000 or cancelled() or monotonic() >= deadline:
                    return
                value = (relative / name).as_posix()
                try:
                    self.path(value)
                except (ValueError, OSError):
                    continue
                yield value

    def execute(self, name, arguments, cancelled=lambda: False):
        try:
            args = json.loads(arguments)
            if not isinstance(args, dict):
                raise ValueError('Tool arguments must be an object.')
            if name == 'read_file':
                if set(args) != {'path', 'start_line', 'end_line'}:
                    raise ValueError('read_file requires path, start_line and end_line.')
                start, end = args['start_line'], args['end_line']
                if type(start) is not int or type(end) is not int or not 1 <= start <= end or end - start >= 200:
                    raise ValueError('Read between 1 and 200 lines, starting at line 1 or later.')
                text, source = self.text(args['path'])
                lines = text.splitlines()
                result = dict(path=args['path'], source=source, total_lines=len(lines),
                              text='\n'.join(f'{i}: {line}' for i, line in enumerate(lines[start - 1:end], start)))
                result['truncated'] = len(result['text']) > 10000
                result['text'] = result['text'][:10000]
            elif name in ('list_files', 'search_files'):
                if set(args) != {'query'} or not isinstance(args['query'], str) or len(args['query']) > 500:
                    raise ValueError('Provide a text query of at most 500 characters.')
                query = args['query'].casefold()
                if name == 'search_files' and not query:
                    raise ValueError('Enter a nonempty search query.')
                matches, size, read_bytes = [], 0, 0
                for path in self.files(cancelled):
                    if cancelled():
                        break
                    if name == 'list_files':
                        found = [path] if query in path.casefold() else []
                    else:
                        try:
                            text, _ = self.text(path)
                        except (OSError, ValueError, UnicodeError):
                            continue
                        read_bytes += len(text.encode('utf-8'))
                        if read_bytes > 8 * 1024 * 1024:
                            break
                        found = []
                        for line, content in enumerate(text.splitlines(), 1):
                            if query in content.casefold():
                                found.append(dict(path=path, line=line, text=content[:240]))
                                if len(found) >= 50:
                                    break
                    for match in found:
                        cost = len(json.dumps(match, ensure_ascii=False))
                        if len(matches) >= 50 or size + cost > 10000:
                            break
                        matches.append(match)
                        size += cost
                    if len(matches) >= 50 or size >= 9500:
                        break
                result = dict(matches=matches, bounded=True,
                              note='Search is bounded to 5,000 entries, 50 matches and 8 MiB of text; results may be incomplete.')
            else:
                raise ValueError('Unknown tool. Only list_files, search_files and read_file are available.')
            return json.dumps(result, ensure_ascii=False)
        except (OSError, ValueError, UnicodeError, TypeError) as error:
            return json.dumps({'error': str(error)[:500]})
