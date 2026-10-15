"""Discover logical mobile folders without creating crypt storage or copying files."""
from features.rclone.mobile.storage_location import collection_path
from pathlib import Path
from features.rclone.mobile.mirror_jobs import copy_target
from services.folder_policy import read_exclusions, visible_name, folder_parts


def exclusions():
    root = Path(__file__).resolve().parents[1]
    source = root / 'configFile.ini'
    if not source.is_file():
        source = root / 'services/configFile.ini'
    return read_exclusions(source)


def visible_remotes(names):
    rules = exclusions()
    return sorted((name for name in names if visible_name(name, rules, remote=True)), key=str.casefold)


def hub_entries(root, jobs, remotes=(), crypt_locations=()):
    root, rules = Path(root), exclusions()
    entries = {}
    def add(name, source, reference):
        if visible_name(name, rules, remote=source == 'Remote'):
            entries.setdefault(name, []).append((source, reference))
    try:
        local = collection_path(root)
    except (OSError, ValueError):
        for remote in visible_remotes(remotes):
            add(remote, 'Remote', ('remote', remote))
        return [(name, folder_parts(name), entries[name]) for name in sorted(entries, key=str.casefold)]
    mapped = set()
    for job in jobs.values():
        target = copy_target(root, job)
        if target.is_dir() and not target.is_symlink():
            add(job['remote'], 'LocalCrypt' if job['crypt'] else 'Local', ('job', job['id']))
            if not job['crypt']:
                mapped.add(job['target'])
    represented = {job['remote'] for job in jobs.values() if job['crypt']}
    for label, remote in crypt_locations:
        if remote not in represented:
            add(remote, 'LocalCrypt', ('crypt', label))
    local = collection_path(root)
    if local.is_dir() and not local.is_symlink():
        for path in local.iterdir():
            if path.is_dir() and not path.is_symlink() and path.name not in mapped:
                add(path.name, 'Local', ('local', path.name))
    for remote in visible_remotes(remotes):
        add(remote, 'Remote', ('remote', remote))
    return [(name, folder_parts(name), entries[name]) for name in sorted(entries, key=str.casefold)]


def folder_tree(choices):
    """Build every dash-separated level, preserving selectable folder identities."""
    tree = {}
    for name in choices:
        parts = tuple(part for part in name.replace('/', '-').split('-') if part) or (name,)
        branch = tree
        for part in parts:
            node = branch.setdefault(part, dict(children={}, names=[]))
            branch = node['children']
        node['names'].append(name)
    return tree


def credential_choices(choices, remotes):
    """Keep all available copies of a folder owned by this credential."""
    return {name: entry for name, entry in choices.items()
            if entry.get('remote') in remotes or any(copy.get('remote') in remotes
                                                    for copy in entry.get('copies', ()))}
