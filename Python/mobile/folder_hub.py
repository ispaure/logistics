"""Discover logical mobile folders without creating crypt storage or copying files."""
from features.rclone.mobile.storage_location import collection_path
from pathlib import Path
from dataclasses import dataclass
from features.rclone.transfers.mobile.jobs import copy_target
from services.folders.catalog import FolderCopy, project_catalog, credential_source, source_category as catalog_category
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
    scope = getattr(remotes, 'source_identity', None)
    def accepts(copy):
        source = copy.get('source_identity')
        return copy.get('remote') in remotes and (scope is None or not source or source == scope)
    result = {}
    for name, entry in choices.items():
        if not any(accepts(copy) for copy in [entry, *entry.get('copies', ())]):
            continue
        if scope is None:
            result[name] = entry
            continue
        copies = [copy for copy in entry.get('copies', ())
                  if copy['source'] != 'Remote' or accepts(copy)]
        primary = next((copy for copy in copies if accepts(copy)), entry)
        result[name] = {**entry, **primary, 'copies': copies}
    return result


def source_choices(choices, source, network_remotes=()):
    """Expose downloaded copies locally while retaining their remote actions."""
    network_remotes = set(network_remotes)
    def owner(entry):
        categories = {copy.get('catalog_category') for copy in [entry, *entry.get('copies', ())]}
        if 'Home Server' in categories:
            return 'Network shares'
        if 'Cloud' in categories:
            return 'rclone'
        remotes = {copy.get('remote') for copy in [entry, *entry.get('copies', ())]} - {None, ''}
        if remotes & network_remotes:
            return 'Network shares'
        return 'rclone' if remotes else 'Local'
    def visible(entry):
        if source == 'Local':
            return any(copy['source'] in ('Local', 'LocalCrypt')
                       for copy in [entry, *entry.get('copies', ())])
        return (owner(entry) == source and (source != 'rclone' or any(copy['source'] == 'Remote'
                for copy in [entry, *entry.get('copies', ())])))
    return {name: entry for name, entry in choices.items() if visible(entry)}


def folder_browse_copy(entry, source):
    """Choose a tab's browse target without changing the logical action entry."""
    copies = entry.get('copies') or [entry]
    if source == 'Local':
        return next((copy for copy in copies if copy['source'] in ('Local', 'LocalCrypt')), entry)
    if source == 'rclone':
        return min((copy for copy in copies if copy['source'] == 'Remote'),
                   key=lambda copy: copy.get('locked', False), default=entry)
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
    source_packages: tuple = ()


@dataclass(frozen=True)
class FolderDiscoveryResult:
    choices: dict
    crypt_locations: tuple


def _folder_copy_descriptors(snapshot, remotes, crypt):
    """Resolve detached account/copy identities before catalog grouping and display."""
    jobs, retained = snapshot.jobs, snapshot.retained_packages
    packages = [*retained, *snapshot.source_packages]
    accounts, by_identity = {}, {}
    loaded_sources = {credential_source(item['package_name']) for item in snapshot.source_packages
                      if item.get('package_name')}
    for package in packages:
        label = package.get('package_name', package.get('zip'))
        if not label:
            continue
        source = credential_source(label)
        identities = package.get('identities', {})
        for remote in package['remotes']:
            identity = identities.get(remote)
            descriptor = (source, identity, label)
            known = accounts.setdefault(remote, {})
            known[source] = descriptor
            if identity:
                by_identity[identity] = descriptor
    for job in jobs.values():
        remote, identity = job.get('remote'), job.get('identity')
        if remote and identity:
            descriptor = by_identity.get(identity, (('connection', identity), identity, ''))
            accounts.setdefault(remote, {})[descriptor[0]] = descriptor
            by_identity[identity] = descriptor
    descriptors = []
    for name, parts, copies in hub_entries(snapshot.private_root, jobs, remotes, crypt.items()):
        for source, (kind, value) in copies:
            title = (name if not jobs[value]['prefix'] else jobs[value]['target']) if kind == 'job' else name
            remote = jobs[value]['remote'] if kind == 'job' else name if kind in ('crypt', 'remote') else None
            identity = jobs[value].get('identity') if kind == 'job' else None
            remote_owners = list(accounts.get(remote, {}).values())
            owners = (remote_owners if kind == 'remote' else
                      [by_identity[identity]] if identity in by_identity else
                      list(accounts.get(remote, {}).values()) if remote else [])
            if not owners:
                owners = [(('connection', identity) if identity else (), identity, '')]
            for account, connection, label in owners:
                loaded = account in loaded_sources or not snapshot.source_packages and remote in snapshot.remote_names
                payload = dict(source=source, kind=kind, value=(value, '') if kind == 'remote' else value,
                               name=title, remote=remote, source_identity=account,
                               connection_identity=connection, source_label=label,
                               catalog_category=catalog_category('rclone', label) if remote and label else None if remote else 'Local')
                payload['locked'] = source == 'Remote' and bool(account) and not loaded
                copy_id = (kind, str(value), account)
                descriptors.append(FolderCopy(copy_id, title, account, source,
                                               available=source != 'Remote' or loaded,
                                               locked=payload['locked'],
                                               payload=payload))
    return descriptors


def discover_folder_choices(snapshot):
    """Read local directories and group known locations without mutating the snapshot."""
    jobs = snapshot.jobs
    # Retained ZIP metadata declares known destinations without loading secrets.
    # Transfer mappings and local folder names alone do not declare remotes.
    remotes = sorted(set(snapshot.remote_names) | {remote for package in snapshot.retained_packages
                                                  for remote in package['remotes']}, key=str.casefold)
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
    choices = {'All files': dict(source='Local', kind='shared-local', value='', name='Browse All Files', copies=[], browser_root=True)}
    descriptors = _folder_copy_descriptors(snapshot, remotes, crypt)
    # A remote name denotes the same folder across credential packages.
    groups = project_catalog(descriptors, grouping='name')
    for group in groups:
        copies = [dict(copy.payload) for copy in group.copies]
        primary = min(copies, key=lambda copy: (copy['kind'] != 'job', copy['source'] == 'Remote', copy.get('locked', False)))
        entry = dict(primary, copies=copies, catalog_identity=group.identity,
                     available=group.available, locked=group.locked)
        if primary['kind'] == 'job':
            job = jobs[primary['value']]
            entry['copies'] = [copy for copy in copies if copy['source'] != 'Remote' or copy.get('locked')]
            loaded = [record for record in snapshot.source_packages
                      if job['remote'] in record['remotes'] and (not job.get('identity')
                          or record.get('identities', {}).get(job['remote']) == job['identity'])]
            if loaded or not snapshot.source_packages and job['remote'] in snapshot.remote_names:
                entry['copies'].append(dict(primary, source='Remote', kind='job-remote', value=job['id']))
        elif (primary['kind'] == 'crypt' and primary['remote'] in snapshot.remote_names
              and not any(copy['source'] == 'Remote' for copy in copies)):
            entry['copies'].append(dict(primary, source='Remote', kind='remote', value=(primary['remote'], '')))
        choices[group.name] = entry
    from .incoming_files import inbox_path
    received = inbox_path(snapshot.private_root)
    from .local_sources import shared_files
    shared = shared_files(snapshot.private_root)
    if shared is not None:
        for row in shared.list():
            if row['directory'] and row['name'] not in ('Local', received.name):
                title = row['name']
                copy = dict(source='Local', kind='shared-local', value=title, name=title)
                if title in choices:
                    choices[title]['copies'].append(copy)
                else:
                    choices[title] = dict(copy, copies=[])
    choices[received.name] = dict(source='Local', kind='inbox', value='', name=received.name, copies=[])
    return FolderDiscoveryResult(choices, tuple(crypt.items()) if roots else snapshot.crypt_locations)


@dataclass(frozen=True)
class FolderRowPresentation:
    title: str
    icon: str
    description: str
    state: str | None


def folder_row_presentation(title, entry, source, loaded_remotes, crypt_remotes):
    """Project folder labels and lock state without constructing native controls."""
    target = folder_browse_copy(entry, source)
    storage = (folder_storage_label(entry) if source == 'Network shares'
               else target['source'])
    remote = target.get('remote') or entry.get('remote')
    encrypted = ('LocalCrypt' in storage or ('Remote' in storage and (
        remote in crypt_remotes
        or any(copy['source'] == 'LocalCrypt' for copy in entry.get('copies', ())))))
    state = ('locked' if target.get('locked') else 'unlocked' if remote in loaded_remotes else 'locked') if encrypted else None
    icon = 'folder_' + state if state else 'folder'
    description = storage + (', ' + state if state else '')
    return FolderRowPresentation(title, icon, description, state)
