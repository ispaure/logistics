"""Portable Workspaces visibility and naming rules, shared by both hosts."""
from configparser import ConfigParser
from pathlib import Path


def configured_values(path, key):
    parser = ConfigParser(interpolation=None)
    with Path(path).open(encoding='utf-8-sig') as stream:
        parser.read_file(stream)
    return [value.strip() for value in parser.get('Folders', key, fallback='').split(',') if value.strip()]


def read_exclusions(path):
    return (frozenset(value.casefold() for value in configured_values(path, 'excluded_remote_names')),
            tuple(value.casefold() for value in configured_values(path, 'excluded_folder_name_suffixes')))


def visible_name(name, exclusions, *, remote=False):
    names, suffixes = exclusions
    return bool(name) and not (remote and name.casefold() in names) and not (
        suffixes and name.casefold().endswith(suffixes))


def folder_parts(name):
    return tuple(name.split('-'))
