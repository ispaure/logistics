"""Compatibility entry point for opening a desktop comic reader."""


def open_reader(comic):
    """Open through the feature's desktop presentation owner.

    Before: from features.comics.reader import open_reader
    After: from features.comics.ui.reader_opening import open_reader
    Keep calling open_reader(comic) with the same argument.
    """
    import warnings
    from .ui.reader_opening import open_reader as open_comic
    warnings.warn(
        'features.comics.reader.open_reader is deprecated; use '
        'features.comics.ui.reader_opening.open_reader with the same argument.',
        FutureWarning, stacklevel=2)
    return open_comic(comic)
