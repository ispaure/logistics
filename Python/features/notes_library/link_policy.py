"""One link spelling, precedence and ambiguity policy for navigation/connections."""
import posixpath
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from commonUtils.formats.markdown import link_path_names
from commonUtils.runtime.operations import check_cancelled


def resolve_link(current, target, *, root, contained, exists, suffix_matches,
                 cancelled=lambda: False):
    """Resolve against live probes or a detached inventory, without choosing I/O."""
    check_cancelled(cancelled)
    link = urlsplit(target)
    if link.scheme or link.netloc or link.query or link.path.startswith(('/', '\\')) or '\\' in link.path:
        raise ValueError('Choose a note inside this Notes Library.')
    current = contained(current)
    if not link.path:
        return current, link.fragment
    for name in link_path_names(link.path):
        explicit = any(part in {'.', '..'} for part in name.split('/'))
        names = [name] if PurePosixPath(name).suffix else [name, name + '.md']
        for lookup in names:
            candidates = [contained(posixpath.normpath(posixpath.join(posixpath.dirname(current), lookup)))]
            if not explicit:
                candidates.append(contained(posixpath.normpath(posixpath.join(root, lookup))))
            for candidate in dict.fromkeys(candidates):
                check_cancelled(cancelled)
                if exists(candidate):
                    return candidate, link.fragment
        if explicit:
            continue
        matches = list(dict.fromkeys(suffix_matches(names[-1])))
        check_cancelled(cancelled)
        if len(matches) == 1:
            return contained(matches[0]), link.fragment
        if matches:
            raise ValueError('Several notes match this link. Use a path from the Notes Library root.')
    raise ValueError('Note not found in this Notes Library.')
