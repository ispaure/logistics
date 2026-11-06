"""Portable Workspaces visibility and naming rules, shared by both hosts."""
from commonUtils.configuration.layered import effective_settings


def _folder_settings(path):
    return effective_settings(path, case_sensitive=False, normalize_after_parse=False)


def _configured_values(parser, key):
    return [value.strip() for value in parser.get('Folders', key, fallback='').split(',') if value.strip()]


def configured_values(path, key):
    return _configured_values(_folder_settings(path), key)


def read_exclusions(path):
    settings = _folder_settings(path)
    return (frozenset(value.casefold() for value in _configured_values(settings, 'excluded_remote_names')),
            tuple(value.casefold() for value in _configured_values(settings, 'excluded_folder_name_suffixes')))


def visible_name(name, exclusions, *, remote=False):
    names, suffixes = exclusions
    return bool(name) and not (remote and name.casefold() in names) and not (
        suffixes and name.casefold().endswith(suffixes))


def folder_parts(name):
    return tuple(name.split('-'))
