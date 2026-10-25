"""Name policy for mobile Save As; folder paths remain provider-owned."""
from pathlib import PurePosixPath

from commonUtils.formats.code_syntax import SOURCE_EXTENSIONS
from commonUtils.runtime.resources.paths import resource_name


def save_filename(name, source_name, *, extensions=SOURCE_EXTENSIONS):
    name = resource_name(name)
    if not name.strip() or name.endswith('.'):
        raise ValueError('Choose a nonblank name without a trailing dot.')
    suffix = PurePosixPath(name).suffix
    if not suffix:
        source_suffix = PurePosixPath(source_name).suffix
        name += source_suffix if source_suffix.lower() in extensions else '.txt'
    elif suffix.lower() not in extensions:
        if extensions == ('.rmdoc',):
            raise ValueError('Choose a notebook filename ending in .rmdoc.')
        raise ValueError('Choose a supported text, source or configuration extension.')
    return name
