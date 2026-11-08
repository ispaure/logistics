"""Ordinary mobile browse roots, excluding private control and encrypted storage."""
from commonUtils.runtime.resources.local import LocalFiles
from services.documents.locations import MobileLocalFiles, local_folder_snapshot, shared_documents_path
from services.documents.mobile_locations import enabled, phone_path, reserved_phone_name


def device_label(app):
    """Use device identity, rather than the current pane/window width."""
    backend = type(app._impl).__module__
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        return 'Tablet' if int(ObjCClass('UIDevice').currentDevice.userInterfaceIdiom) == 1 else 'Phone'
    if backend.startswith('toga_android.'):
        config = app._impl.native.getResources().getConfiguration()
        return 'Tablet' if int(config.smallestScreenWidthDp) >= 600 else 'Phone'
    return 'Phone'


def device_files_label(app):
    return f'On My {device_label(app)}'


def destination_location_labels(app, roots):
    """Keep the collection root out of the picker, while retaining named copies."""
    labels = {'Local files': 'Local', 'Shared files': 'Shared Files'}
    if isinstance(roots.get('Shared files'), PhoneFiles):
        labels['Shared files'] = device_files_label(app)
        roots = {label: provider for label, provider in roots.items() if label != 'Local files'}
    return {labels.get(label, label): provider for label, provider in roots.items()}


class PhoneFiles(MobileLocalFiles):
    """Ordinary files, including received shares, separate from managed storage."""

    def __init__(self, private_root):
        self.private_root = private_root
        root = phone_path(private_root)
        root.mkdir(parents=True, exist_ok=True)
        super().__init__(root)

    def _guard(self, path):
        if phone_path(self.private_root) != self.root:
            raise ValueError('Collection location changed. Reopen the file browser.')
        parts = path.relative_to(self.root).parts
        if parts and reserved_phone_name(parts[0]):
            raise ValueError('This folder name is reserved by Logisticks.')
        return super()._guard(path)

    def list(self, path='', *, cancelled=lambda: False):
        return local_folder_snapshot(self, path, cancelled=cancelled,
                                     root_name_visible=lambda name: not reserved_phone_name(name))

    def list_names(self, path='', *, cancelled=lambda: False):
        return local_folder_snapshot(self, path, cancelled=cancelled, names_only=True,
                                     root_name_visible=lambda name: not reserved_phone_name(name))


def synced_local_folders(store, *, visible):
    """Shortcut only mapped folders present in the ordinary Local collection."""
    result = {}
    for job in store.jobs.values():
        if job['crypt'] or not all(visible(name) for name in (job['remote'], job['target'])):
            continue
        try:
            if store.guard(store.target(job)).is_dir():
                folder = job['target']
                result[f'{folder} - Local Copy'] = folder
        except (OSError, ValueError):
            continue
    if enabled(store.root):
        from services.documents.locations import collection_path
        try:
            base = collection_path(store.root)
            if base.is_dir():
                mapped = {job['target'].split('/', 1)[0] for job in store.jobs.values() if not job['crypt']}
                for child in base.iterdir():
                    if (child.name not in mapped and not child.name.startswith('.') and visible(child.name)
                            and child.is_dir() and not child.is_symlink()):
                        result[f'{child.name} - Local Copy'] = child.name
        except OSError:
            pass  # The device drive can disappear while opening the picker.
    return dict(sorted(result.items(), key=lambda item: item[0].casefold()))


class SharedFiles(LocalFiles):
    def __init__(self, root, *, include_collections=True):
        super().__init__(root)
        self.include_collections = include_collections

    def _guard(self, path):
        relative = path.relative_to(self.root)
        if relative.parts in (('Local',), ('Received Files',)):
            raise ValueError('This folder is managed by Logistics. Open it to manage its contents.')
        return super()._guard(path)

    def list(self, path='', *, cancelled=lambda: False):
        path = self.relative(path)
        if path in ('Local', 'Received Files'):
            # Recursive search reads the collection too. Mutations still go
            # through entry/_guard, which protects the collection root.
            return LocalFiles(self.root).list(path, cancelled=cancelled)
        if path:
            return super().list(path, cancelled=cancelled)
        rows = []
        from commonUtils.runtime.operations import check_cancelled
        for child in self.root.iterdir():
            check_cancelled(cancelled)
            if child.name in ('Local', 'Received Files'):
                if not self.include_collections:
                    continue
                # Expose the collection as a folder, but keep root mutations
                # protected; normal navigation switches to CollectionFiles.
                row = LocalFiles(self.root).entry(child.name)
                rows.append(row)
            else:
                rows.append(self.entry(child.name))
        return sorted(rows, key=lambda row: (not row['directory'], row['name'].casefold()))


def shared_files(private_root, *, include_collections=True):
    root = shared_documents_path(private_root)
    return SharedFiles(root, include_collections=include_collections) if root is not None else None


class DeviceFiles(LocalFiles):
    """Android browse root admits only the two ordinary collection directories.

    Private settings, credentials and raw LocalCrypt storage must never become
    visible through this provider, including direct paths and recursive search.
    """
    def __init__(self, private_root, *, include_collections=True):
        from services.documents.locations import collection_base, collection_path
        from .incoming_files import inbox_path
        self.private_root = private_root
        self.include_collections = include_collections
        received = inbox_path(private_root)
        local = collection_path(private_root)
        local.mkdir(parents=True, exist_ok=True)
        self.folders = (local.name, received.name)
        super().__init__(collection_base(private_root))

    def _guard(self, path):
        from services.documents.locations import collection_base
        if collection_base(self.private_root) != self.root:
            raise ValueError('Collection location changed. Restart Logistics.')
        parts = path.relative_to(self.root).parts
        if parts and parts[0] not in self.folders:
            raise ValueError('This location is private app storage.')
        return super()._guard(path)

    def list(self, path='', *, cancelled=lambda: False):
        from commonUtils.runtime.operations import check_cancelled
        if self.relative(path):
            from services.documents.locations import local_folder_snapshot
            return local_folder_snapshot(self, path, cancelled=cancelled)
        rows = []
        if not self.include_collections:
            self._guard(self.root)
            return rows
        for folder in self.folders:
            check_cancelled(cancelled)
            row = self.entry(folder)
            if folder == 'LocalFiles':
                row = dict(row, name='Local')
            rows.append(row)
        return rows

    def _protect_root(self, path):
        if self.relative(path) in ('', *self.folders):
            raise ValueError('This folder is managed by Logistics. Open it to manage its contents.')

    def rename(self, source, destination):
        self._protect_root(source)
        self._protect_root(destination)
        return super().rename(source, destination)

    def remove_empty(self, path, revision):
        self._protect_root(path)
        return super().remove_empty(path, revision)


def device_files(private_root, *, include_collections=True):
    if enabled(private_root):
        return PhoneFiles(private_root)
    return (shared_files(private_root, include_collections=include_collections)
            or DeviceFiles(private_root, include_collections=include_collections))
