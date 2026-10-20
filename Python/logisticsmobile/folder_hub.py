"""Discover logical mobile folders without creating crypt storage or copying files."""
from features.rclone.mobile.storage_location import collection_path
from pathlib import Path
from dataclasses import dataclass
from features.rclone.transfers.mobile.jobs import copy_target
from services.folders.policy import read_exclusions, visible_name, folder_parts


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


def folder_storage_label(entry):
    """Describe available copies, without implying that a mapping is up to date."""
    copies = entry.get('copies') or [entry]
    sources = {copy['source'] for copy in copies}
    return ' · '.join(source for source in ('Local', 'LocalCrypt', 'Remote') if source in sources)


def credential_choices(choices, remotes):
    """Keep all available copies of a folder owned by this credential."""
    return {name: entry for name, entry in choices.items()
            if entry.get('remote') in remotes or any(copy.get('remote') in remotes
                                                    for copy in entry.get('copies', ()))}


def source_choices(choices, source, network_remotes=()):
    """Expose downloaded copies locally while retaining their remote actions."""
    network_remotes = set(network_remotes)
    def owner(entry):
        remotes = {copy.get('remote') for copy in [entry, *entry.get('copies', ())]} - {None, ''}
        if remotes & network_remotes:
            return 'Network shares'
        return 'rclone' if remotes else 'Local'
    def visible(entry):
        if source == 'Local':
            return any(copy['source'] in ('Local', 'LocalCrypt')
                       for copy in entry.get('copies') or [entry])
        return owner(entry) == source
    return {name: entry for name, entry in choices.items() if visible(entry)}


def folder_browse_copy(entry, source):
    """Choose a tab's browse target without changing the logical action entry."""
    copies = entry.get('copies') or [entry]
    if source == 'Local':
        return next((copy for copy in copies if copy['source'] in ('Local', 'LocalCrypt')), entry)
    if source == 'rclone':
        return next((copy for copy in copies if copy['source'] == 'Remote'), entry)
    return entry


@dataclass(frozen=True)
class FolderDiscoverySnapshot:
    """Detached input captured on the UI thread; no clients or widget callbacks."""
    private_root: Path
    jobs: dict
    remote_names: tuple
    retained_packages: tuple
    crypt_locations: tuple
    crypt_roots: dict


@dataclass(frozen=True)
class FolderDiscoveryResult:
    choices: dict
    crypt_locations: tuple


def discover_folder_choices(snapshot):
    """Read local directories and group known locations without mutating the snapshot."""
    jobs = snapshot.jobs
    # Retained metadata is a discovery index, never permission to browse.
    # Opening any locked remote still goes through the matching ZIP guard.
    retained = snapshot.retained_packages
    remotes = sorted(set(snapshot.remote_names) | {
        remote for package in retained for remote in package['remotes']}, key=str.casefold)
    crypt = dict(snapshot.crypt_locations)
    roots = snapshot.crypt_roots
    if roots:
        # The account identities were resolved at credential load. Recheck
        # just their local directories, including copies created since then.
        base = collection_path(snapshot.private_root, True)
        crypt = {}
        for label, (remote, identity) in roots.items():
            path = base / identity
            if path.is_dir() and not path.is_symlink() and any(path.iterdir()):
                crypt[label] = remote
    # Rendering and menu opening must never enter the native bridge. A
    # credential load updates this discovery snapshot.
    choices = {'All files': dict(source='Local', kind='local', value='', name='Browse All Files', copies=[], browser_root=True)}
    for name, parts, copies in hub_entries(snapshot.private_root, jobs, remotes, crypt.items()):
        for source, (kind, value) in copies:
            title = (name if not jobs[value]['prefix'] else jobs[value]['target']) if kind == 'job' else name
            if kind == 'remote':
                value = value, ''
            remote = jobs[value]['remote'] if kind == 'job' else name if kind in ('crypt', 'remote') else None
            copy = dict(source=source, kind=kind, value=value, name=title, remote=remote)
            group = choices.setdefault(title, dict(copy, copies=[]))
            group['copies'].append(copy)
    for group in choices.values():
        if group['copies']:
            primary = min(group['copies'], key=lambda copy: (copy['kind'] != 'job', copy['source'] == 'Remote'))
            group.update(primary)
            # Browse the mapped scope, rather than accidentally opening the
            # remote root for a pulled subfolder. Decode crypt paths on open.
            if primary['kind'] == 'job':
                job = jobs[primary['value']]
                # The mapping already identifies this online folder even
                # before credentials load. Opening it uses the usual unlock
                # guard and resolves its mapped scope after authentication.
                group['copies'] = [copy for copy in group['copies'] if copy['source'] != 'Remote']
                group['copies'].append(dict(source='Remote', kind='job-remote',
                                            value=job['id'], name=primary['name'], remote=job['remote']))
            elif primary['kind'] == 'crypt' and not any(copy['source'] == 'Remote' for copy in group['copies']):
                group['copies'].append(dict(source='Remote', kind='remote',
                                            value=(primary['remote'], ''), name=primary['name'],
                                            remote=primary['remote']))
    from .local_sources import shared_files
    shared = shared_files(snapshot.private_root)
    if shared is not None:
        # Imported folders and mapped copies stay individually accessible.
        # The shared directory is a separate browse action below the list.
        choices['All files'] = dict(source='Local', kind='shared-local', value='',
                                    name='Browse All Files', copies=[], browser_root=True)
        for row in shared.list():
            if row['directory'] and row['name'] != 'Local':
                title = row['name']
                key = title if title not in choices else title + ' (Local)'
                choices[key] = dict(source='Local', kind='shared-local', value=title, name=title, copies=[])
    return FolderDiscoveryResult(choices, tuple(crypt.items()) if roots else snapshot.crypt_locations)
